"""Tests for decision layer logic — no LLM calls."""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from schemas import DecisionOutput, Goal, ToolCall


def _make_decision(answer=None, tool_call=None) -> DecisionOutput:
    return DecisionOutput(answer=answer, tool_call=tool_call)


def test_answer_only():
    d = _make_decision(answer="The answer is 42.")
    assert d.answer == "The answer is 42."
    assert d.tool_call is None


def test_tool_call_only():
    tc = ToolCall(name="web_search", arguments={"query": "test"})
    d = _make_decision(tool_call=tc)
    assert d.answer is None
    assert d.tool_call.name == "web_search"


def test_both_answer_takes_priority():
    tc = ToolCall(name="web_search", arguments={})
    d = _make_decision(answer="Some answer", tool_call=tc)
    # In practice, agent6.py prefers answer when both present
    # Decision schema allows both — enforcement is in agent loop
    assert d.answer is not None


def test_artifact_arg_safety(monkeypatch):
    """Action layer must reject art: handles as tool arguments."""
    import action

    class FakeSession:
        async def call_tool(self, name, args):
            return "result"

    import asyncio
    tc = ToolCall(name="read_file", arguments={"path": "art:abc123"})
    with __import__("pytest").raises(ValueError, match="art:"):
        asyncio.run(action.execute(FakeSession(), tc))


def test_tool_call_schema():
    tc = ToolCall(name="get_time", arguments={"timezone": "Asia/Kolkata"})
    d = DecisionOutput(tool_call=tc)
    dumped = d.model_dump()
    assert dumped["tool_call"]["name"] == "get_time"
    assert dumped["tool_call"]["arguments"]["timezone"] == "Asia/Kolkata"
