"""Tests for the artifact store."""
from __future__ import annotations

import hashlib
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))
import artifacts


def test_put_and_get():
    blob = b"Hello artifact world"
    meta = artifacts.put(blob, source="test", descriptor="test blob")
    assert meta.id == hashlib.sha256(blob).hexdigest()
    assert meta.size_bytes == len(blob)
    assert artifacts.exists(meta.id)
    assert artifacts.get_bytes(meta.id) == blob


def test_deduplication():
    blob = b"Deduplicated content"
    meta1 = artifacts.put(blob, source="run1", descriptor="first")
    meta2 = artifacts.put(blob, source="run2", descriptor="second")
    assert meta1.id == meta2.id  # same content → same ID


def test_get_meta():
    blob = b"Metadata test"
    meta = artifacts.put(blob, content_type="text/plain", source="test", descriptor="meta test")
    retrieved = artifacts.get_meta(meta.id)
    assert retrieved.id == meta.id
    assert retrieved.content_type == "text/plain"
    assert retrieved.size_bytes == len(blob)


def test_exists_false():
    assert not artifacts.exists("nonexistent" * 4)


def test_missing_bytes_raises():
    with pytest.raises(FileNotFoundError):
        artifacts.get_bytes("a" * 64)


def test_list_all():
    blob = b"Listing test artifact"
    meta = artifacts.put(blob, source="test_list", descriptor="listing test")
    all_arts = artifacts.list_all()
    ids = [a.id for a in all_arts]
    assert meta.id in ids
