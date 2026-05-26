"""
Decision layer.
Chooses exactly ONE next action per goal: either a final answer or a single tool call.
Never emits both. Never calls LLM for tool dispatch (that's action.py).
"""
from __future__ import annotations

from pathlib import Path
from typing import Optional

from schemas import DecisionOutput, Goal, MemoryItem, ToolCall
import gateway
from utils.logging_utils import get_logger

log = get_logger("decision")

_PROMPT_PATH = Path(__file__).parent / "prompts" / "decision.txt"


def next_step(
    goal: Goal,
    hits: list[MemoryItem],
    attached: Optional[bytes],
    history: list[dict],
    mcp_tools: list[dict],
) -> DecisionOutput:
    """
    Decide the next action for the given goal.
    Returns DecisionOutput with exactly one of: answer or tool_call.
    """
    system_parts = [_PROMPT_PATH.read_text(encoding="utf-8")]

    if mcp_tools:
        tool_lines = "\n".join(f"  • {t['name']}: {t.get('description', '')}" for t in mcp_tools)
        system_parts.append(f"AVAILABLE TOOLS:\n{tool_lines}")

    system = "\n\n".join(system_parts)

    # Memory context
    mem_section = ""
    if hits:
        lines = []
        for h in hits:
            line = f"  [{h.kind}] {h.descriptor}"
            if h.artifact_id:
                line += f" (artifact_id={h.artifact_id})"
            lines.append(line)
        mem_section = "MEMORY CONTEXT:\n" + "\n".join(lines) + "\n"

    # Attached artifact bytes
    artifact_section = ""
    if attached:
        text = attached.decode("utf-8", errors="replace")
        if len(text) > 10000:
            text = text[:5000] + "\n\n...[content truncated]...\n\n" + text[-5000:]
        artifact_section = f"ATTACHED ARTIFACT CONTENT:\n{text}\n"

    user_content = f"""CURRENT GOAL: {goal.text}

{mem_section}{artifact_section}
Respond with JSON in EXACTLY ONE of these two forms:
  {{"action": "answer", "content": "your complete answer here"}}
  {{"action": "tool", "tool_name": "name", "tool_args": {{...}}}}"""

    messages = list(history[-8:])  # recent context
    messages.append({"role": "user", "content": user_content})

    _kwargs = dict(
        messages=messages,
        system=system,
        response_format={"type": "json_object"},
        temperature=0.2,
    )
    parsed: dict = {}
    # Use direct provider calls to avoid the slow router classification overhead.
    # groq is fastest; github is reliable fallback; then full failover chain.
    _direct_providers = ["groq", "github", "nvidia", "openrouter", "gemini"]
    try:
        last_exc: Exception | None = None
        for provider in _direct_providers:
            try:
                resp = gateway.chat(**_kwargs, provider=provider)
                parsed = gateway.parse_json(resp, fallback={})
                log.info("Decision: used provider %s", provider)
                break
            except Exception as exc:
                last_exc = exc
                log.debug("Decision provider %s failed: %s", provider, exc)
                continue
        else:
            raise RuntimeError(f"All direct providers failed. Last: {last_exc}")
    except Exception as exc2:
        log.error("Decision all providers failed: %s", exc2)
        return DecisionOutput(answer=f"Error in decision layer: {exc2}")

    if not parsed:
        parsed = {"action": "answer", "content": "I was unable to determine the next step."}

    action = parsed.get("action", "")

    if action == "tool":
        tool_name = parsed.get("tool_name", "")
        tool_args = parsed.get("tool_args", {})
        if not isinstance(tool_args, dict):
            tool_args = {}
        if tool_name:
            log.info("Decision → tool_call: %s(%s)", tool_name, _arg_summary(tool_args))
            return DecisionOutput(tool_call=ToolCall(name=tool_name, arguments=tool_args))

    # Default: answer path
    content = parsed.get("content", "") or parsed.get("answer", "")
    if not content and action not in ("answer", "tool"):
        # Model returned unexpected structure — extract any text
        content = str(parsed)[:500]

    log.info("Decision → answer (%d chars)", len(content))
    return DecisionOutput(answer=content or "No answer produced.")


def _arg_summary(args: dict) -> str:
    parts = [f"{k}={str(v)[:25]}" for k, v in list(args.items())[:3]]
    return ", ".join(parts)
