"""
Agent6 — Agentic Architecture Main Loop.

Four cognitive roles, typed boundaries:
  Memory → Perception → Decision → Action

Each run creates a dedicated log file in logs/<timestamp>_<run_id>.log
Run from CLI: python agent6.py "your query here"
"""
from __future__ import annotations

import asyncio
import os
import subprocess
import sys
import time
import uuid
from pathlib import Path
from typing import Callable, Optional

from schemas import AgentUpdate, Goal
import memory
import perception
import decision
import action
import artifacts as artifact_store
from mcp_client import MCPClient
from utils.logging_utils import (
    add_run_file_handler,
    get_logger,
    remove_run_file_handler,
    setup_logging,
)

log = get_logger("loop")

_PROJECT_DIR = Path(__file__).parent
_LOGS_DIR = _PROJECT_DIR / "logs"
_GATEWAY_DIR = _PROJECT_DIR.parent / "5e4a8833-292d-4ce5-be97-749c7656bdbf" / "llm_gatewayV3"
_GATEWAY_URL = os.getenv("LLM_GATEWAY_V3_URL", "http://localhost:8101")
_gateway_process: Optional[subprocess.Popen] = None

MAX_ITERATIONS = 20


# ── Gateway management ────────────────────────────────────────────────────────

def _gateway_alive() -> bool:
    import httpx
    try:
        r = httpx.get(f"{_GATEWAY_URL}/v1/providers", timeout=3.0)
        return r.status_code < 500
    except Exception:
        return False


def ensure_gateway() -> None:
    """Auto-start LLM Gateway V3 if it is not already running."""
    global _gateway_process
    if _gateway_alive():
        log.info("Gateway already running at %s", _GATEWAY_URL)
        return
    log.info("Gateway not running — starting it from %s ...", _GATEWAY_DIR)
    _gateway_process = subprocess.Popen(
        ["python", "main.py"],
        cwd=str(_GATEWAY_DIR),
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    for i in range(25):
        time.sleep(1)
        if _gateway_alive():
            log.info("Gateway up (PID %d) after %ds", _gateway_process.pid, i + 1)
            return
    log.warning("Gateway may not be ready after 25s — proceeding anyway")

# Triggers proactive memory.remember() at the top of a run
_PREFERENCE_MARKERS = (
    "i prefer", "i like", "i don't like", "i love", "i hate",
    "my favorite", "always use", "never use", "i am a", "i'm a",
    "i want to", "i always", "i never", "my preference",
    "remember that", "remember this", "please remember", "don't forget",
    "note that", "keep in mind", "my mom", "my dad", "my wife",
    "my husband", "my partner", "birthday is", "anniversary is",
)

# Synthesis goals: force-attach most recent artifact from memory hits when Perception
# didn't set attach_artifact_id (guard against model dropping the attachment).
_SYNTHESIS_KEYWORDS = frozenset({
    "synthesise", "synthesize", "extract", "compare", "decide", "choose",
    "which", "summarize", "summarise", "analyze", "analyse", "select",
    "recommend", "based on", "common", "agree", "agreed", "consolidate",
    "compile", "combine", "review", "assess",
})


async def run(
    query: str,
    history: list[dict],
    run_id: Optional[str] = None,
    on_update: Optional[Callable[[AgentUpdate], None]] = None,
) -> tuple[str, list[dict]]:
    """
    Run one agent turn for the given query.

    Args:
        query:     User's natural language input.
        history:   Conversation history (mutated in-place, also returned).
        run_id:    Unique run identifier (generated if not supplied).
        on_update: Optional callback receiving AgentUpdate events for live UI.

    Returns:
        (final_answer, updated_history)
    """
    run_id = run_id or str(uuid.uuid4())

    # ── Per-run log file ──────────────────────────────────────────────────────
    log_path = add_run_file_handler(run_id, _LOGS_DIR)

    log.info("═══ Run %s ═══", run_id[:8])
    log.info("Query: %s", query[:120])
    log.info("Log file: %s", log_path)

    def emit(kind: str, **data: object) -> None:
        if on_update:
            try:
                on_update(AgentUpdate(kind=kind, data=dict(data)))
            except Exception as e:
                log.debug("on_update callback error: %s", e)
        # Also log key events to the run log
        if kind == "tool_call":
            log.info("TOOL_CALL  %s(%s)", data.get("name"), _arg_summary(data.get("arguments", {})))
        elif kind == "tool_result":
            log.info("TOOL_RESULT %s | artifact=%s", str(data.get("descriptor",""))[:120], data.get("artifact_id"))
        elif kind == "goal_answer":
            log.info("GOAL_DONE  %s → %s…", str(data.get("goal_text",""))[:60], str(data.get("answer",""))[:80])
        elif kind in ("error", "warning"):
            log.warning("EVENT[%s] %s: %s", kind, data.get("layer",""), data.get("message",""))

    # ── Ensure the LLM gateway is running ────────────────────────────────────
    if _gateway_alive():
        emit("log", message="✅ LLM Gateway already running.")
    else:
        emit("log", message="⏳ LLM Gateway not running — starting it (up to 25s)…")
    ensure_gateway()
    if not _gateway_alive():
        emit("warning", layer="gateway", message="Gateway may not be ready — LLM calls may fail.")

    try:
        # Proactively remember explicit preferences
        if _is_preference(query):
            log.info("Proactive memory: storing user preference")
            emit("log", message="Storing preference to memory…")
            try:
                item = memory.remember(query, run_id=run_id, source="user_input")
                emit("memory_stored", kind=item.kind, descriptor=item.descriptor)
            except Exception as exc:
                log.warning("Could not store preference: %s", exc)

        prior_goals: list[Goal] = []
        all_answers: list[str] = []

        async with MCPClient() as mcp:
            mcp_tools = await mcp.list_tools()
            log.info("MCP tools: %s", [t["name"] for t in mcp_tools])
            emit("mcp_ready", tool_count=len(mcp_tools), tools=[t["name"] for t in mcp_tools])

            for iteration in range(1, MAX_ITERATIONS + 1):
                log.info("─── Iteration %d / %d ───", iteration, MAX_ITERATIONS)
                emit("iteration", number=iteration, max=MAX_ITERATIONS)

                # ── MEMORY ──────────────────────────────────────────────────
                hits = memory.read(query, history, top_k=6)
                log.info("Memory hits: %d", len(hits))
                for h in hits:
                    log.info("  • [%s] %s", h.kind, h.descriptor[:60])
                emit("memory_hits",
                     count=len(hits),
                     items=[{"kind": h.kind, "descriptor": h.descriptor,
                              "artifact_id": h.artifact_id} for h in hits])

                # ── PERCEPTION ──────────────────────────────────────────────
                emit("log", message="🔍 Perception: decomposing goals via Gemini…")
                try:
                    obs = perception.observe(
                        query=query,
                        hits=hits,
                        history=history,
                        prior_goals=prior_goals,
                        run_id=run_id,
                    )
                except Exception as exc:
                    log.error("Perception failed: %s", exc)
                    emit("error", layer="perception", message=str(exc))
                    break

                prior_goals = obs.goals
                log.info("Goals (%d):", len(obs.goals))
                for g in obs.goals:
                    log.info("  [%s] %s", "✓" if g.done else "○", g.text[:80])
                emit("goals", goals=[
                    {"id": g.id, "text": g.text, "done": g.done, "artifact": g.attach_artifact_id}
                    for g in obs.goals
                ])

                if obs.all_done():
                    log.info("All goals complete after iteration %d", iteration)
                    break

                goal = obs.next_unfinished()
                if goal is None:
                    log.warning("No unfinished goal found (all_done check mismatch)")
                    break

                log.info("Active goal: %s", goal.text[:80])

                # ── ARTIFACT ATTACHMENT ──────────────────────────────────────
                attached: Optional[bytes] = None
                if goal.attach_artifact_id:
                    art_id = goal.attach_artifact_id
                    if artifact_store.exists(art_id):
                        try:
                            attached = artifact_store.get_bytes(art_id)
                            log.info("Attached artifact %s (%d bytes)", art_id[:8], len(attached))
                            emit("artifact_attached", id=art_id, size_bytes=len(attached))
                        except Exception as exc:
                            log.warning("Failed to load artifact %s: %s", art_id[:8], exc)
                    else:
                        log.warning("Artifact %s not in store", art_id[:8])
                        emit("warning", layer="artifacts", message=f"Artifact {art_id[:8]} referenced by Perception not found in store.")

                # ── SYNTHESIS FORCE-ATTACH ───────────────────────────────────
                # Guard: if Perception didn't attach an artifact but the goal looks
                # like a synthesis/extraction task and memory hits contain artifacts,
                # auto-attach the most recently created one.
                if attached is None:
                    goal_lower = goal.text.lower()
                    if any(kw in goal_lower for kw in _SYNTHESIS_KEYWORDS):
                        art_hits = sorted(
                            [h for h in hits
                             if h.artifact_id and artifact_store.exists(h.artifact_id)],
                            key=lambda h: h.created_at,
                            reverse=True,
                        )
                        for h in art_hits:
                            try:
                                attached = artifact_store.get_bytes(h.artifact_id)
                                goal.attach_artifact_id = h.artifact_id
                                log.info(
                                    "Synthesis force-attach: artifact %s → '%s'",
                                    h.artifact_id[:8], goal.text[:50],
                                )
                                emit("artifact_attached", id=h.artifact_id, size_bytes=len(attached))
                                break
                            except Exception as exc:
                                log.warning("Force-attach failed %s: %s", h.artifact_id[:8], exc)

                # ── DECISION ────────────────────────────────────────────────
                emit("log", message=f"🧠 Decision: choosing next action for → {goal.text[:80]}")
                try:
                    out = decision.next_step(
                        goal=goal,
                        hits=hits,
                        attached=attached,
                        history=history,
                        mcp_tools=mcp_tools,
                    )
                except Exception as exc:
                    log.error("Decision failed: %s", exc)
                    emit("error", layer="decision", message=str(exc))
                    history.append({"role": "assistant", "content": f"[Decision error] {exc}"})
                    continue

                # ── ANSWER PATH ─────────────────────────────────────────────
                if out.answer:
                    emit("goal_answer", goal_id=goal.id, goal_text=goal.text, answer=out.answer)
                    all_answers.append(f"**{goal.text}**\n\n{out.answer}")
                    history.append({"role": "assistant", "content": out.answer})
                    for g in prior_goals:
                        if g.id == goal.id:
                            g.done = True
                    continue

                # ── TOOL PATH ───────────────────────────────────────────────
                if out.tool_call:
                    tc = out.tool_call
                    emit("tool_call", name=tc.name, arguments=tc.arguments)

                    _wait_hints = {
                        "fetch_url":  "⏳ fetch_url: launching headless browser — this can take 30-90s for large pages…",
                        "web_search": "⏳ web_search: querying the web…",
                    }
                    emit("log", message=_wait_hints.get(tc.name, f"⏳ Executing {tc.name}…"))

                    try:
                        descriptor, artifact_id = await action.execute(mcp.session, tc)
                    except ValueError as exc:
                        log.error("Action safety error: %s", exc)
                        emit("error", layer="action", message=str(exc))
                        history.append({"role": "assistant", "content": f"[Action blocked] {exc}"})
                        continue
                    except Exception as exc:
                        log.error("Tool execution failed: %s", exc)
                        emit("error", layer="action", message=str(exc))
                        history.append({"role": "assistant", "content": f"[Tool error] {tc.name}: {exc}"})
                        continue

                    emit("tool_result", descriptor=descriptor, artifact_id=artifact_id)

                    try:
                        memory.record_outcome(
                            tool_name=tc.name,
                            arguments=tc.arguments,
                            descriptor=descriptor,
                            artifact_id=artifact_id,
                            run_id=run_id,
                            goal_id=goal.id,
                        )
                    except Exception as exc:
                        log.warning("Failed to record outcome: %s", exc)

                    history.append({"role": "assistant",
                                    "content": f"[Tool: {tc.name}] {descriptor}"})

                    if artifact_id:
                        found_current = False
                        for g in prior_goals:
                            if g.id == goal.id:
                                g.attach_artifact_id = artifact_id
                                found_current = True
                            elif found_current and not g.done:
                                # Proactively forward artifact to the next pending goal
                                g.attach_artifact_id = artifact_id
                                log.info(
                                    "Auto-forwarded artifact %s to next goal '%s'",
                                    artifact_id[:8], g.text[:50],
                                )
                                break
                    continue

                # Stuck — neither answer nor tool
                log.warning("Decision returned no action on iteration %d", iteration)
                emit("error", layer="decision", message="No action returned")
                break

            else:
                log.warning("Max iterations (%d) reached", MAX_ITERATIONS)
                emit("warning", message=f"Stopped after {MAX_ITERATIONS} iterations")

        final_answer = "\n\n---\n\n".join(all_answers) if all_answers else "The agent did not produce an answer."
        emit("final_answer", answer=final_answer, log_file=str(log_path))
        log.info("═══ Run %s complete — answer %d chars ═══", run_id[:8], len(final_answer))
        return final_answer, history

    finally:
        # Always flush and close the per-run log file
        remove_run_file_handler(run_id)


# ── Helpers ───────────────────────────────────────────────────────────────────

def _is_preference(text: str) -> bool:
    lower = text.lower()
    return any(m in lower for m in _PREFERENCE_MARKERS)


def _arg_summary(args: dict) -> str:
    parts = [f"{k}={str(v)[:20]}" for k, v in list(args.items())[:2]]
    return ", ".join(parts)


# ── CLI entry point ───────────────────────────────────────────────────────────

if __name__ == "__main__":
    setup_logging()
    query = " ".join(sys.argv[1:]).strip() or "What time is it in Tokyo right now?"
    print(f"\nQuery: {query}\n")

    def _print_update(u: AgentUpdate) -> None:
        kind = u.kind
        if kind == "iteration":
            print(f"\n{'-'*50}\n  Iteration {u.data['number']}")
        elif kind == "memory_hits":
            print(f"  Memory hits: {u.data['count']}")
        elif kind == "goals":
            for g in u.data.get("goals", []):
                status = "[DONE]" if g["done"] else "[OPEN]"
                print(f"  {status} {g['text'][:80]}")
        elif kind == "tool_call":
            print(f"  -> Tool: {u.data['name']}({_arg_summary(u.data.get('arguments', {}))})")
        elif kind == "tool_result":
            print(f"  <- Result: {u.data['descriptor'][:100]}")
        elif kind == "goal_answer":
            print(f"  [DONE] Answered: {u.data['goal_text'][:60]}")
        elif kind == "error":
            print(f"  [ERROR] [{u.data.get('layer','?')}]: {u.data.get('message','')[:100]}")
        elif kind == "final_answer":
            log_f = u.data.get("log_file", "")
            if log_f:
                print(f"\n  Log: {log_f}")

    answer, _ = asyncio.run(run(query, [], on_update=_print_update))
    print(f"\n{'='*60}\n{answer}\n{'='*60}")
