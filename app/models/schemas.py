"""
Request and response models for the inference gateway.
All inputs validated by Pydantic before they touch business logic.
"""
from __future__ import annotations

from enum import Enum
from typing import Any
from uuid import UUID, uuid4

from pydantic import BaseModel, Field, field_validator


# ── Enums ─────────────────────────────────────────────────────────────────────

class ModelTier(str, Enum):
    FAST    = "fast"
    QUALITY = "quality"
    CODE    = "code"
    VISION  = "vision"


class InferenceStatus(str, Enum):
    SUCCESS = "success"
    ERROR   = "error"
    TIMEOUT = "timeout"
    QUEUED  = "queued"


class TaskType(str, Enum):
    CHAT      = "chat"
    SUMMARISE = "summarise"
    CODE      = "code"
    REASONING = "reasoning"
    GENERAL   = "general"
    VISION    = "vision"


# ── Request Models ─────────────────────────────────────────────────────────────

class Message(BaseModel):
    role:    str = Field(..., pattern="^(system|user|assistant)$")
    content: str = Field(..., min_length=1, max_length=32_000)


class InferenceRequest(BaseModel):
    request_id: UUID      = Field(default_factory=uuid4)
    messages:   list[Message] = Field(..., min_length=1)
    task_type:  TaskType  = TaskType.GENERAL
    force_tier: ModelTier | None = None
    max_tokens: int   = Field(default=1024, ge=1, le=8192)
    temperature: float = Field(default=0.7, ge=0.0, le=2.0)
    stream:     bool  = False
    # Base64-encoded image for vision requests
    image_b64:  str | None = None

    @field_validator("messages")
    @classmethod
    def last_message_must_be_user(cls, v: list[Message]) -> list[Message]:
        if v and v[-1].role != "user":
            raise ValueError("Last message must have role='user'")
        return v


# ── Routing Models ─────────────────────────────────────────────────────────────

class RoutingDecision(BaseModel):
    tier:             ModelTier
    model:            str
    reason:           str
    estimated_tokens: int
    complexity_score: float = Field(ge=0.0, le=1.0)


# ── Response Models ────────────────────────────────────────────────────────────

class UsageStats(BaseModel):
    prompt_tokens:     int
    completion_tokens: int
    total_tokens:      int


class LatencyBreakdown(BaseModel):
    routing_ms:      float
    queue_ms:        float | None = None
    model_ms:        float
    total_ms:        float
    first_token_ms:  float | None = None


class InferenceResponse(BaseModel):
    request_id: UUID
    status:     InferenceStatus
    model:      str
    tier:       ModelTier
    content:    str | None = None
    error:      str | None = None
    usage:      UsageStats | None = None
    latency:    LatencyBreakdown
    routing:    RoutingDecision


# ── Health Models ──────────────────────────────────────────────────────────────

class BackendHealth(BaseModel):
    name:       str
    available:  bool
    models:     list[str] = []
    latency_ms: float | None = None
    error:      str | None = None


class HealthResponse(BaseModel):
    status:         str
    env:            str
    backends:       list[BackendHealth]
    uptime_seconds: float