"""
Persistent memory layer.
Stores facts, preferences, tool outcomes, and scratchpad notes in state/memory.json.

read()           — keyword overlap retrieval, NO LLM
remember()       — LLM-based classification (auto_route="memory", any available provider)
record_outcome() — persist MCP tool results, NO LLM
"""
from __future__ import annotations

import json
import os
import re as _re
import uuid
from pathlib import Path
from typing import Optional

from schemas import MemoryItem
import gateway
from utils.logging_utils import get_logger

log = get_logger("memory")

_MEMORY_PATH = Path(__file__).parent / "state" / "memory.json"
_MEMORY_PATH.parent.mkdir(parents=True, exist_ok=True)

_CLASSIFIER_PROMPT = Path(__file__).parent / "prompts" / "memory_classifier.txt"

# Memory classification uses a small/fast model via auto_route.
# Optionally pin a specific model with MEMORY_MODEL env var.
_MEMORY_MODEL = os.getenv("MEMORY_MODEL")  # None → gateway router chooses


# ── Tokenization ─────────────────────────────────────────────────────────────

def _tokenize(text: str) -> set[str]:
    """
    Tokenize text for keyword overlap scoring.
    - Strips punctuation from each token
    - Adds a de-possessivised/de-pluralised form when the token ends in 's'
      so that "mom's" (→ "moms") matches the stored keyword "mom".
    """
    tokens: set[str] = set()
    for tok in text.lower().split():
        clean = _re.sub(r"[^a-z0-9]", "", tok)
        if not clean:
            continue
        tokens.add(clean)
        if clean.endswith("s") and len(clean) > 3:
            tokens.add(clean[:-1])  # "moms" → "mom", "contributions" → "contribution"
    return tokens


# ── Persistence helpers ───────────────────────────────────────────────────────

def _load() -> list[MemoryItem]:
    if not _MEMORY_PATH.exists():
        return []
    try:
        raw = json.loads(_MEMORY_PATH.read_text(encoding="utf-8"))
        return [MemoryItem.model_validate(d) for d in raw]
    except Exception as exc:
        log.warning("Failed to load memory (resetting): %s", exc)
        return []


def _save(items: list[MemoryItem]) -> None:
    _MEMORY_PATH.write_text(
        json.dumps([i.model_dump(mode="json") for i in items], indent=2),
        encoding="utf-8",
    )


# ── Public API ────────────────────────────────────────────────────────────────

def read(
    query: str,
    history: list[dict],
    kinds: Optional[list[str]] = None,
    top_k: int = 8,
) -> list[MemoryItem]:
    """
    Keyword-overlap retrieval. NO LLM call.
    Scores items by overlap between query tokens and item keyword tokens.
    """
    items = _load()
    if kinds:
        items = [i for i in items if i.kind in kinds]

    # Build query token set from current query + recent history
    query_tokens: set[str] = _tokenize(query)
    for msg in history[-6:]:
        content = msg.get("content", "")
        if isinstance(content, str):
            query_tokens.update(_tokenize(content))

    scored: list[tuple[int, MemoryItem]] = []
    for item in items:
        # Tokenize multi-word keywords: "vegetarian restaurants" → {"vegetarian","restaurant"}
        kw_tokens: set[str] = set()
        for kw in item.keywords:
            kw_tokens.update(_tokenize(kw))
        overlap = len(query_tokens & kw_tokens)
        if overlap > 0:
            scored.append((overlap, item))

    scored.sort(key=lambda x: x[0], reverse=True)
    result = [item for _, item in scored[:top_k]]
    log.debug("Memory read: %d/%d items matched", len(result), len(items))
    return result


def remember(raw_text: str, run_id: str, source: str = "user") -> MemoryItem:
    """
    Classify raw text into a structured MemoryItem using LLM.
    Uses auto_route="memory" so the gateway picks the best available provider.
    Falls back to a simple keyword extraction if the LLM call fails entirely.
    """
    system = _CLASSIFIER_PROMPT.read_text(encoding="utf-8")
    parsed: dict = {}

    _msg = [{"role": "user", "content": raw_text}]
    _fmt = {"type": "json_object"}
    try:
        resp = gateway.chat(
            messages=_msg,
            system=system,
            model=_MEMORY_MODEL,
            response_format=_fmt,
            temperature=0.1,
            auto_route="memory",
        )
        parsed = gateway.parse_json(resp, fallback={})
        log.info("remember(): used %s/%s", resp.get("provider", "?"), resp.get("model", "?"))
    except Exception as exc:
        log.warning("remember() auto_route failed (%s) — trying provider chain", exc)
        try:
            resp = gateway.chat_with_fallback(
                messages=_msg,
                system=system,
                response_format=_fmt,
                temperature=0.1,
            )
            parsed = gateway.parse_json(resp, fallback={})
            log.info("remember() fallback: used %s", resp.get("provider", "?"))
        except Exception as exc2:
            log.warning("remember() all providers failed (%s) — using keyword extraction", exc2)
            words = [w.lower() for w in raw_text.split() if len(w) > 3][:6]
            parsed = {
                "kind": "scratchpad",
                "keywords": words,
                "descriptor": raw_text[:80],
                "value": {"text": raw_text},
                "confidence": 0.5,
            }

    kind = parsed.get("kind", "scratchpad")
    if kind not in ("fact", "preference", "tool_outcome", "scratchpad"):
        kind = "scratchpad"

    item = MemoryItem(
        id=str(uuid.uuid4()),
        kind=kind,  # type: ignore[arg-type]
        keywords=parsed.get("keywords", [w.lower() for w in raw_text.split()[:6]]),
        descriptor=parsed.get("descriptor", raw_text[:80]),
        value=parsed.get("value", {"text": raw_text}),
        source=source,
        run_id=run_id,
        confidence=float(parsed.get("confidence", 1.0)),
    )

    items = _load()
    items.append(item)
    _save(items)
    log.info("Stored memory [%s]: %s", item.kind, item.descriptor[:60])
    return item


def record_outcome(
    *,
    tool_name: str,
    arguments: dict,
    descriptor: str,
    artifact_id: Optional[str],
    run_id: str,
    goal_id: Optional[str] = None,
) -> MemoryItem:
    """Persist a MCP tool result without LLM usage."""
    keywords = [tool_name] + [
        str(v)[:20].lower()
        for v in list(arguments.values())[:4]
        if v and isinstance(v, (str, int, float))
    ]

    item = MemoryItem(
        id=str(uuid.uuid4()),
        kind="tool_outcome",
        keywords=keywords,
        descriptor=descriptor,
        value={"tool": tool_name, "arguments": arguments, "descriptor": descriptor},
        artifact_id=artifact_id,
        source=f"tool:{tool_name}",
        run_id=run_id,
        goal_id=goal_id,
        confidence=1.0,
    )

    items = _load()
    items.append(item)
    _save(items)
    log.info("Recorded outcome [%s]: %s", tool_name, descriptor[:60])
    return item


def get_all() -> list[MemoryItem]:
    return _load()


def clear() -> None:
    _save([])
    log.info("Memory cleared")
