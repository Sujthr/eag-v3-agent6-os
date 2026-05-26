"""
Perception layer — the orchestrator.
Uses Gemini 2.5 Flash-Lite explicitly (stable goal identity across iterations).
Falls back to auto_route="perception" if Gemini is unavailable or quota-exhausted.
"""
from __future__ import annotations

import os
import uuid
from pathlib import Path
from typing import Optional

from schemas import Goal, MemoryItem, Observation
import gateway
from utils.logging_utils import get_logger

log = get_logger("perception")

_PROMPT_PATH = Path(__file__).parent / "prompts" / "perception.txt"

# Gemini 2.0 Flash — fast, long-context, stable for goal management.
# Override via env var GEMINI_PERCEPTION_MODEL if the model ID changes.
_GEMINI_MODEL = os.getenv("GEMINI_PERCEPTION_MODEL", "gemini-2.5-flash")


def observe(
    query: str,
    hits: list[MemoryItem],
    history: list[dict],
    prior_goals: list[Goal],
    run_id: str,
) -> Observation:
    """
    Decompose query into goals and track completion.

    Provider strategy:
      1. Gemini 2.5 Flash-Lite (explicit) — best at stable goal identity.
      2. auto_route="perception" fallback if Gemini fails (quota / unavailable).
    """
    system = _PROMPT_PATH.read_text(encoding="utf-8")
    user_content = _build_context(query, hits, history, prior_goals, run_id)

    # ── Attempt 1: Gemini 2.5 Flash-Lite ─────────────────────────────────────
    parsed: dict = {}
    try:
        resp = gateway.chat(
            messages=[{"role": "user", "content": user_content}],
            system=system,
            provider="gemini",
            model=_GEMINI_MODEL,
            response_format={"type": "json_object"},
            temperature=0.1,
            max_tokens=1500,
        )
        parsed = gateway.parse_json(resp, fallback={})
        log.info("Perception: used Gemini %s (provider: %s)", _GEMINI_MODEL, resp.get("model", "?"))
    except Exception as exc:
        log.warning(
            "Gemini perception failed (%s) — falling back to auto_route='perception'", exc
        )

        # ── Attempt 2: auto_route fallback (any available provider) ───────────
        try:
            resp = gateway.chat(
                messages=[{"role": "user", "content": user_content}],
                system=system,
                auto_route="perception",
                response_format={"type": "json_object"},
                temperature=0.1,
                max_tokens=1500,
            )
            parsed = gateway.parse_json(resp, fallback={})
            log.info("Perception fallback: used %s/%s", resp.get("provider", "?"), resp.get("model", "?"))
        except Exception as exc2:
            log.error("Perception fallback also failed: %s", exc2)
            parsed = {}

    raw_goals: list[dict] = parsed.get("goals", [])
    if not raw_goals and not prior_goals:
        # Last-resort: single goal wrapping the entire query
        raw_goals = [{"id": str(uuid.uuid4()), "text": query, "done": False, "attach_artifact_id": ""}]
        log.warning("Perception: both attempts failed — using single fallback goal")

    merged = _merge_goals(prior_goals, raw_goals)
    obs = Observation(goals=merged)
    log.info(
        "Observation: %d goals (%d done, %d pending)",
        len(obs.goals), sum(g.done for g in obs.goals), sum(not g.done for g in obs.goals),
    )
    return obs


# ── Context builder ───────────────────────────────────────────────────────────

def _build_context(
    query: str,
    hits: list[MemoryItem],
    history: list[dict],
    prior_goals: list[Goal],
    run_id: str,
) -> str:
    import json as _json

    parts: list[str] = [f"USER QUERY: {query}\n"]

    if hits:
        mem_lines = "\n".join(
            f"  • [{h.kind}] {h.descriptor}" + (f" (artifact_id={h.artifact_id})" if h.artifact_id else "")
            for h in hits
        )
        parts.append(f"RELEVANT MEMORY:\n{mem_lines}\n")

    if prior_goals:
        goals_json = _json.dumps(
            [{"id": g.id, "text": g.text, "done": g.done, "attach_artifact_id": g.attach_artifact_id or ""}
             for g in prior_goals],
            indent=2,
        )
        parts.append(f"CURRENT GOALS (preserve IDs exactly):\n{goals_json}\n")

    if history:
        hist_lines = "\n".join(
            f"  {m['role'].upper()}: {str(m.get('content', ''))[:200]}" for m in history[-6:]
        )
        parts.append(f"RECENT HISTORY:\n{hist_lines}\n")

    parts.append(f"RUN_ID: {run_id}")
    return "\n".join(parts)


# ── Goal merging ──────────────────────────────────────────────────────────────

def _merge_goals(prior: list[Goal], incoming: list[dict]) -> list[Goal]:
    """
    Merge incoming goals with prior, enforcing:
      - Sticky done: once True, stays True
      - Order: follow incoming order, append orphaned priors at end
      - ID stability: existing goal text is never overwritten

    Match priority per incoming goal:
      1. Exact UUID match
      2. Case-insensitive text match (handles LLM UUID regeneration)
      3. Position match (same index, same goal count — safe last resort)
    """
    prior_by_id = {g.id: g for g in prior}
    prior_by_text = {g.text.strip().lower(): g for g in prior}
    result: list[Goal] = []
    matched_prior_ids: set[str] = set()

    for i, raw in enumerate(incoming):
        gid = raw.get("id") or str(uuid.uuid4())
        attach = raw.get("attach_artifact_id") or None
        if attach == "":
            attach = None

        # Find the best prior match
        prior_goal: Optional[Goal] = None
        if gid in prior_by_id:
            prior_goal = prior_by_id[gid]
        elif (raw.get("text", "").strip().lower()) in prior_by_text:
            prior_goal = prior_by_text[raw["text"].strip().lower()]
            log.debug("Merge: text-matched prior goal '%s' (UUID changed)", prior_goal.text[:40])
        elif i < len(prior) and len(incoming) == len(prior):
            # Same goal count, same position — safe to assume it's the same goal
            prior_goal = prior[i]
            log.debug("Merge: position-matched prior goal[%d] '%s'", i, prior_goal.text[:40])

        if prior_goal:
            matched_prior_ids.add(prior_goal.id)
            result.append(Goal(
                id=prior_goal.id,
                text=prior_goal.text,
                done=prior_goal.done or bool(raw.get("done", False)),
                attach_artifact_id=attach,
            ))
        else:
            result.append(Goal(
                id=gid,
                text=raw.get("text", ""),
                done=bool(raw.get("done", False)),
                attach_artifact_id=attach,
            ))

    # Preserve any prior goals not matched in incoming
    for g in prior:
        if g.id not in matched_prior_ids:
            result.append(g)

    return result
