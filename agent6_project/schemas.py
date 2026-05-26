"""
Typed contracts for all cognitive layers of Agent6.
Every role boundary uses these schemas — never raw dicts.
"""
from __future__ import annotations

import uuid
from datetime import datetime
from typing import Literal, Optional

from pydantic import BaseModel, Field


# ── Memory ───────────────────────────────────────────────────────────────────

class MemoryItem(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    kind: Literal["fact", "preference", "tool_outcome", "scratchpad"]
    keywords: list[str]
    descriptor: str
    value: dict
    artifact_id: Optional[str] = None
    source: str
    run_id: str
    goal_id: Optional[str] = None
    confidence: float = 1.0
    created_at: datetime = Field(default_factory=datetime.utcnow)


# ── Artifacts ────────────────────────────────────────────────────────────────

class Artifact(BaseModel):
    id: str  # SHA-256 hex digest
    content_type: str
    size_bytes: int
    source: str
    descriptor: str
    created_at: datetime = Field(default_factory=datetime.utcnow)


# ── Perception ───────────────────────────────────────────────────────────────

class Goal(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    text: str
    done: bool = False
    attach_artifact_id: Optional[str] = None


class Observation(BaseModel):
    goals: list[Goal]

    def next_unfinished(self) -> Optional[Goal]:
        return next((g for g in self.goals if not g.done), None)

    def all_done(self) -> bool:
        return bool(self.goals) and all(g.done for g in self.goals)


# ── Decision ─────────────────────────────────────────────────────────────────

class ToolCall(BaseModel):
    name: str
    arguments: dict = Field(default_factory=dict)


class DecisionOutput(BaseModel):
    answer: Optional[str] = None
    tool_call: Optional[ToolCall] = None


# ── Agent update events (for UI) ─────────────────────────────────────────────

class AgentUpdate(BaseModel):
    kind: str
    data: dict = Field(default_factory=dict)
    ts: datetime = Field(default_factory=datetime.utcnow)
