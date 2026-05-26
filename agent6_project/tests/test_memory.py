"""Tests for the memory layer."""
from __future__ import annotations

import sys
import uuid
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from schemas import MemoryItem
import memory


def _make_item(kind="fact", keywords=("python", "test"), descriptor="Test item") -> MemoryItem:
    return MemoryItem(
        id=str(uuid.uuid4()),
        kind=kind,
        keywords=list(keywords),
        descriptor=descriptor,
        value={"test": True},
        source="test",
        run_id="test-run",
    )


def test_read_keyword_overlap():
    memory.clear()
    item = _make_item(keywords=["vegetarian", "restaurant", "food"])
    items = memory._load()
    items.append(item)
    memory._save(items)

    hits = memory.read("vegetarian food options", [], top_k=5)
    assert any(h.id == item.id for h in hits), "Expected keyword match"


def test_read_no_match():
    memory.clear()
    item = _make_item(keywords=["quantum", "physics", "entanglement"])
    items = memory._load()
    items.append(item)
    memory._save(items)

    hits = memory.read("cooking recipes pasta", [], top_k=5)
    assert not any(h.id == item.id for h in hits)


def test_read_kind_filter():
    memory.clear()
    fact = _make_item(kind="fact", keywords=["python", "language"])
    pref = _make_item(kind="preference", keywords=["python", "preferred"])
    items_list = [fact, pref]
    memory._save(items_list)

    hits = memory.read("python", [], kinds=["preference"], top_k=5)
    assert all(h.kind == "preference" for h in hits)


def test_record_outcome_no_llm():
    memory.clear()
    item = memory.record_outcome(
        tool_name="web_search",
        arguments={"query": "test query"},
        descriptor="Search results for test",
        artifact_id=None,
        run_id="test-run",
    )
    assert item.kind == "tool_outcome"
    assert "web_search" in item.keywords
    assert item.artifact_id is None

    loaded = memory._load()
    assert any(i.id == item.id for i in loaded)


def test_persistence():
    memory.clear()
    item = _make_item(keywords=["persistent", "data"])
    items = memory._load()
    items.append(item)
    memory._save(items)

    # Reload fresh
    reloaded = memory._load()
    assert any(i.id == item.id for i in reloaded)


def test_read_top_k():
    memory.clear()
    for i in range(15):
        memory._save(memory._load() + [_make_item(keywords=["common", f"item{i}"])])

    hits = memory.read("common", [], top_k=5)
    assert len(hits) <= 5
