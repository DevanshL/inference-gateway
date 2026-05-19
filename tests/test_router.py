"""
Router tests — covers all 4 tiers (fast / quality / code / vision).

Tests cover:
- Schema validation (InferenceRequest)
- Router logic: fast, quality, code, vision tier decisions
- Force-tier client overrides
- Complexity scoring and token estimation
"""
import pytest
from uuid import uuid4

from app.models.schemas import (
    InferenceRequest,
    Message,
    ModelTier,
    TaskType,
)
from app.services.router import (
    _estimate_tokens,
    _score_complexity,
    route,
)
from app.core.config import get_settings


# ── Fixtures ──────────────────────────────────────────────────────────────────

def make_request(content: str, task_type: TaskType = TaskType.GENERAL, force_tier=None) -> InferenceRequest:
    return InferenceRequest(
        messages=[Message(role="user", content=content)],
        task_type=task_type,
        force_tier=force_tier,
    )


# ── Schema tests ──────────────────────────────────────────────────────────────

def test_request_requires_user_last_message():
    with pytest.raises(Exception):
        InferenceRequest(
            messages=[
                Message(role="user", content="hello"),
                Message(role="assistant", content="hi"),
            ]
        )


def test_request_valid():
    req = make_request("What is 2+2?")
    assert req.messages[-1].role == "user"


def test_request_default_task_type():
    req = make_request("hello")
    assert req.task_type == TaskType.GENERAL


# ── Token estimation tests ────────────────────────────────────────────────────

def test_token_estimate_short():
    req = make_request("hi")
    tokens = _estimate_tokens(req)
    assert tokens >= 1


def test_token_estimate_scales_with_length():
    short = make_request("hi")
    long = make_request("x" * 1000)
    assert _estimate_tokens(long) > _estimate_tokens(short)


# ── Complexity scoring tests ──────────────────────────────────────────────────

def test_simple_chat_low_complexity():
    req = make_request("What is the capital of France?")
    score = _score_complexity(req)
    assert score < 0.4


def test_code_task_high_complexity():
    req = make_request(
        "Implement a binary search tree with insert, delete and search operations",
        task_type=TaskType.CODE,
    )
    score = _score_complexity(req)
    assert score >= 0.4


def test_reasoning_task_high_complexity():
    req = make_request(
        "Analyse and compare the trade-offs between microservices and monolithic architectures",
        task_type=TaskType.REASONING,
    )
    score = _score_complexity(req)
    assert score >= 0.4


def test_complexity_capped_at_one():
    req = make_request(
        "analyse explain why compare contrast evaluate critique implement algorithm "
        "calculate prove derive equation formula step by step comprehensive detailed "
        "therefore however although nevertheless because",
        task_type=TaskType.REASONING,
    )
    score = _score_complexity(req)
    assert score <= 1.0


# ── Routing decision tests ────────────────────────────────────────────────────

def test_simple_request_routes_to_fast():
    req = make_request("What is the capital of France?")
    decision = route(req)
    assert decision.tier == ModelTier.FAST


def test_complex_request_routes_to_quality():
    # Pure reasoning prompt — no code keywords, so should stay on quality tier
    req = make_request(
        "Analyse the geopolitical and economic trade-offs between globalisation "
        "and protectionism. Evaluate how different nations have responded and "
        "what the long-term consequences might be.",
        task_type=TaskType.REASONING,
    )
    decision = route(req)
    assert decision.tier == ModelTier.QUALITY


def test_code_request_routes_to_code_tier():
    req = make_request(
        "Implement a binary search tree in python with insert, delete, and search.",
        task_type=TaskType.CODE,
    )
    decision = route(req)
    assert decision.tier == ModelTier.CODE


def test_vision_task_type_routes_to_vision_tier():
    req = make_request("Describe what you see.", task_type=TaskType.VISION)
    decision = route(req)
    assert decision.tier == ModelTier.VISION


def test_image_b64_routes_to_vision_tier():
    req = InferenceRequest(
        messages=[Message(role="user", content="What is in this image?")],
        image_b64="base64encodeddata",
    )
    decision = route(req)
    assert decision.tier == ModelTier.VISION


def test_force_fast_tier_override():
    req = make_request(
        "Write a comprehensive algorithm implementation",
        task_type=TaskType.CODE,
        force_tier=ModelTier.FAST,
    )
    decision = route(req)
    assert decision.tier == ModelTier.FAST
    assert decision.reason == "client_override"


def test_force_quality_tier_override():
    req = make_request("hi", force_tier=ModelTier.QUALITY)
    decision = route(req)
    assert decision.tier == ModelTier.QUALITY
    assert decision.reason == "client_override"


def test_routing_decision_has_model():
    settings = get_settings()
    req = make_request("simple question")
    decision = route(req)
    all_models = [
        settings.routing_fast_model,
        settings.routing_quality_model,
        settings.routing_code_model,
        settings.routing_vision_model,
    ]
    assert decision.model in all_models


def test_routing_decision_has_reason():
    req = make_request("explain why the sky is blue in detail with a comprehensive analysis")
    decision = route(req)
    assert len(decision.reason) > 0
