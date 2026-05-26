"""
Conftest: redirect state paths to a temp directory so tests never
touch the production state/memory.json or state/artifacts/.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

# Ensure project root is on sys.path before any imports
sys.path.insert(0, str(Path(__file__).parent.parent))


@pytest.fixture(autouse=True)
def _isolated_state(tmp_path, monkeypatch):
    """
    Redirect memory and artifact paths to a per-test temp directory.
    Tests are fully isolated — no production state is touched.
    """
    import memory as mem_mod
    import artifacts as art_mod

    # Patch memory path
    fake_mem = tmp_path / "memory.json"
    monkeypatch.setattr(mem_mod, "_MEMORY_PATH", fake_mem)

    # Patch artifact store directory
    fake_art_dir = tmp_path / "artifacts"
    fake_art_dir.mkdir()
    monkeypatch.setattr(art_mod, "_STORE", fake_art_dir)

    yield
