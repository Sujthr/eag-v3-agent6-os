"""
SHA-256 content-addressed artifact store.
Memory stores only artifact IDs — never raw bytes.
Decision receives bytes only when Perception explicitly attaches them.
"""
from __future__ import annotations

import hashlib
import json
from datetime import datetime
from pathlib import Path
from typing import Optional

from schemas import Artifact

_STORE = Path(__file__).parent / "state" / "artifacts"
_STORE.mkdir(parents=True, exist_ok=True)


def _meta(artifact_id: str) -> Path:
    return _STORE / f"{artifact_id}.meta.json"


def _data(artifact_id: str) -> Path:
    return _STORE / f"{artifact_id}.bin"


def put(
    blob: bytes,
    *,
    content_type: str = "text/plain",
    source: str = "",
    descriptor: str = "",
) -> Artifact:
    """
    Store blob; return Artifact metadata.
    Deduplicates by SHA-256 — identical content is stored once.
    """
    artifact_id = hashlib.sha256(blob).hexdigest()

    if not _data(artifact_id).exists():
        _data(artifact_id).write_bytes(blob)
        meta = Artifact(
            id=artifact_id,
            content_type=content_type,
            size_bytes=len(blob),
            source=source,
            descriptor=descriptor,
        )
        _meta(artifact_id).write_text(meta.model_dump_json(indent=2), encoding="utf-8")
    else:
        meta = get_meta(artifact_id)

    return meta


def get_bytes(artifact_id: str) -> bytes:
    p = _data(artifact_id)
    if not p.exists():
        raise FileNotFoundError(f"Artifact not found: {artifact_id!r}")
    return p.read_bytes()


def get_meta(artifact_id: str) -> Artifact:
    p = _meta(artifact_id)
    if not p.exists():
        raise FileNotFoundError(f"Artifact metadata not found: {artifact_id!r}")
    return Artifact.model_validate_json(p.read_text(encoding="utf-8"))


def exists(artifact_id: str) -> bool:
    return _data(artifact_id).exists()


def list_all() -> list[Artifact]:
    metas: list[Artifact] = []
    for p in sorted(_STORE.glob("*.meta.json")):
        try:
            metas.append(Artifact.model_validate_json(p.read_text(encoding="utf-8")))
        except Exception:
            pass
    return sorted(metas, key=lambda a: a.created_at, reverse=True)
