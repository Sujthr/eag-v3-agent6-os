"""
End-to-end agent loop test with mocked LLM gateway and MCP session.
Tests the full Memory → Perception → Decision → Action flow without
requiring live API keys or an MCP server process.
"""
from __future__ import annotations

import asyncio
import sys
import uuid
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

import memory
import artifacts as artifact_store
from schemas import AgentUpdate


@pytest.fixture(autouse=True)
def _clean_state():
    """Reset memory and artifacts between tests."""
    memory.clear()
    yield


class MockMCPSession:
    """Minimal MCP session that returns canned responses."""
    async def call_tool(self, name: str, arguments: dict):
        result = MagicMock()
        result.content = [MagicMock(text=f"Mock result from {name}({arguments})")]
        return result


class MockMCPClient:
    session = MockMCPSession()
    _tools_cache = None

    async def __aenter__(self):
        return self

    async def __aexit__(self, *a):
        pass

    async def list_tools(self):
        return [
            {"name": "web_search", "description": "Search the web", "input_schema": {}},
            {"name": "get_time", "description": "Get current time", "input_schema": {}},
        ]


def _gateway_chat_side_effect(**call_tracker):
    """Returns a gateway.chat mock that logs calls."""
    call_count = {"n": 0}

    def _mock(messages, *, system=None, provider=None, response_format=None, **kwargs):
        call_count["n"] += 1
        n = call_count["n"]

        # First call: perception → decompose into one goal
        if n == 1 or (provider == "gemini"):
            return {
                "text": '{"goals": [{"id": "goal-1", "text": "Answer the user query directly", "done": false, "attach_artifact_id": ""}]}',
                "parsed": {"goals": [{"id": "goal-1", "text": "Answer the user query directly", "done": False, "attach_artifact_id": ""}]},
            }

        # Subsequent calls: decision → answer
        return {
            "text": '{"action": "answer", "content": "This is the mock answer."}',
            "parsed": {"action": "answer", "content": "This is the mock answer."},
        }

    return _mock


def test_simple_run():
    """Single-iteration run that produces an answer."""

    with (
        patch("agent6.MCPClient", return_value=MockMCPClient()),
        patch("perception.gateway.chat") as perc_mock,
        patch("decision.gateway.chat") as dec_mock,
    ):
        perc_mock.return_value = {
            "text": "",
            "parsed": {"goals": [{"id": "g1", "text": "Say hello", "done": False, "attach_artifact_id": ""}]},
        }
        dec_mock.return_value = {
            "text": "",
            "parsed": {"action": "answer", "content": "Hello, world!"},
        }

        import agent6
        updates = []
        answer, history = asyncio.run(
            agent6.run("Say hello", [], on_update=lambda u: updates.append(u))
        )

    assert "Hello, world!" in answer
    kinds = [u.kind for u in updates]
    assert "iteration" in kinds
    assert "final_answer" in kinds


def test_memory_persistence():
    """Verify that record_outcome persists and is retrieved on next run."""
    memory.record_outcome(
        tool_name="web_search",
        arguments={"query": "vegetarian restaurants"},
        descriptor="Found 5 vegetarian restaurants",
        artifact_id=None,
        run_id="test-run",
    )

    hits = memory.read("vegetarian restaurants", [], top_k=5)
    assert len(hits) > 0
    assert hits[0].kind == "tool_outcome"


def test_artifact_store_and_retrieval():
    """Large tool output is stored as artifact, not in memory."""
    large_text = "A" * 5000  # > 4KB threshold

    meta = artifact_store.put(
        large_text.encode("utf-8"),
        content_type="text/plain",
        source="test",
        descriptor="large test artifact",
    )

    assert artifact_store.exists(meta.id)
    retrieved = artifact_store.get_bytes(meta.id)
    assert len(retrieved) == 5000


def test_preference_memory():
    """Preference text triggers memory storage."""
    import agent6
    assert agent6._is_preference("I prefer vegetarian restaurants")
    assert agent6._is_preference("I love dark mode")
    assert not agent6._is_preference("What time is it in Tokyo?")
