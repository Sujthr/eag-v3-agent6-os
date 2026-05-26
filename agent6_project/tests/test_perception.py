"""Tests for the perception layer (goal merging logic — no LLM)."""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from schemas import Goal
from perception import _merge_goals


def _goal(text: str, done: bool = False, gid: str | None = None) -> Goal:
    return Goal(id=gid or f"id-{text[:8]}", text=text, done=done)


def test_sticky_done():
    prior = [_goal("Fetch page", done=True, gid="g1"), _goal("Extract data", done=False, gid="g2")]
    incoming = [{"id": "g1", "text": "Fetch page", "done": False}, {"id": "g2", "text": "Extract data", "done": True}]
    result = _merge_goals(prior, incoming)
    # g1 was done=True — must stay True even though incoming says False
    assert result[0].done is True
    assert result[1].done is True


def test_order_preservation():
    prior = [_goal("A", gid="a"), _goal("B", gid="b"), _goal("C", gid="c")]
    # Incoming reverses order
    incoming = [{"id": "c", "text": "C", "done": False}, {"id": "a", "text": "A", "done": False}, {"id": "b", "text": "B", "done": False}]
    result = _merge_goals(prior, incoming)
    ids = [g.id for g in result]
    # Should follow incoming order (which is c, a, b from incoming)
    assert ids[0] == "c"
    assert ids[1] == "a"
    assert ids[2] == "b"


def test_new_goal_appended():
    prior = [_goal("Existing", gid="e1")]
    incoming = [{"id": "e1", "text": "Existing", "done": True}, {"id": "new1", "text": "New goal", "done": False}]
    result = _merge_goals(prior, incoming)
    assert len(result) == 2
    assert result[1].text == "New goal"


def test_missing_goals_preserved():
    prior = [_goal("A", gid="a"), _goal("B", gid="b")]
    # Incoming only mentions A
    incoming = [{"id": "a", "text": "A", "done": True}]
    result = _merge_goals(prior, incoming)
    ids = [g.id for g in result]
    assert "b" in ids  # B must be preserved


def test_text_immutable():
    prior = [_goal("Original text", gid="g1")]
    incoming = [{"id": "g1", "text": "Mutated text", "done": False}]
    result = _merge_goals(prior, incoming)
    assert result[0].text == "Original text"


def test_empty_artifact_id_normalized():
    prior = []
    incoming = [{"id": "g1", "text": "Goal", "done": False, "attach_artifact_id": ""}]
    result = _merge_goals(prior, incoming)
    assert result[0].attach_artifact_id is None
