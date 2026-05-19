"""
Model Router — 4-tier routing with specialised models.

Routing priority (checked in order):
  1. Vision   → any request with image_b64 attached
  2. Code     → task_type=code OR strong code signals
  3. Fast     → low token count AND low complexity
  4. Quality  → everything else
  5. Override → client-forced tier always wins
"""
from __future__ import annotations

import time
from typing import Final

from app.core.config import get_settings
from app.core.logging import get_logger
from app.core.metrics import ROUTING_DECISIONS_TOTAL, TOKENS_ESTIMATED_TOTAL
from app.models.schemas import (
    InferenceRequest,
    ModelTier,
    RoutingDecision,
    TaskType,
)

logger = get_logger(__name__)

# ── Complexity signal weights ──────────────────────────────────────────────────

_COMPLEXITY_SIGNALS: Final[list[tuple[list[str], float]]] = [
    (["explain", "why", "analyse", "analyze", "compare", "contrast",
      "evaluate", "critique", "pros and cons", "trade-off", "tradeoff"], 0.25),
    (["write code", "implement", "function", "algorithm", "debug",
      "refactor", "architecture", "design pattern"], 0.30),
    (["essay", "report", "detailed", "comprehensive", "step by step",
      "in depth", "thoroughly", "exhaustive"], 0.20),
    (["because", "therefore", "however", "although", "nevertheless",
      "on the other hand", "it follows that"], 0.15),
    (["calculate", "prove", "derive", "equation", "formula",
      "mathematically", "formally"], 0.25),
]

# Strong code signals — route to code tier regardless of complexity score
_CODE_SIGNALS: Final[list[str]] = [
    "def ", "class ", "import ", "function", "implement", "debug",
    "fix this code", "write a", "refactor", "unit test", "api endpoint",
    "sql query", "regex", "dockerfile", "bash script", "shell script",
    "typescript", "javascript", "python", "rust", "golang", "java",
]

_TASK_TYPE_BASE: Final[dict[TaskType, float]] = {
    TaskType.GENERAL:   0.0,
    TaskType.CHAT:      0.0,
    TaskType.SUMMARISE: 0.10,
    TaskType.CODE:      0.30,
    TaskType.REASONING: 0.35,
    TaskType.VISION:    0.0,
}

_CHARS_PER_TOKEN: Final[float] = 3.8


def _estimate_tokens(request: InferenceRequest) -> int:
    total_chars = sum(len(m.content) for m in request.messages)
    return max(1, int(total_chars / _CHARS_PER_TOKEN))


def _score_complexity(request: InferenceRequest) -> float:
    combined = " ".join(m.content.lower() for m in request.messages)
    score = _TASK_TYPE_BASE.get(request.task_type, 0.0)
    for keywords, weight in _COMPLEXITY_SIGNALS:
        if any(kw in combined for kw in keywords):
            score += weight
    turn_count = len(request.messages)
    if turn_count > 4:
        score += 0.10
    elif turn_count > 2:
        score += 0.05
    return min(score, 1.0)


def _is_code_request(request: InferenceRequest) -> bool:
    """True if request is clearly code-focused."""
    if request.task_type == TaskType.CODE:
        return True
    combined = " ".join(m.content.lower() for m in request.messages)
    return any(sig in combined for sig in _CODE_SIGNALS)


def route(request: InferenceRequest) -> RoutingDecision:
    """
    4-tier routing entry point.
    Priority: vision → code → fast → quality
    Client force_tier always overrides.
    """
    settings = get_settings()
    start = time.perf_counter()

    # ── Client override ────────────────────────────────────────────────────────
    if request.force_tier is not None:
        tier_model_map = {
            ModelTier.FAST:    settings.routing_fast_model,
            ModelTier.QUALITY: settings.routing_quality_model,
            ModelTier.CODE:    settings.routing_code_model,
            ModelTier.VISION:  settings.routing_vision_model,
        }
        model = tier_model_map.get(request.force_tier, settings.routing_fast_model)
        decision = RoutingDecision(
            tier=request.force_tier,
            model=model,
            reason="client_override",
            estimated_tokens=_estimate_tokens(request),
            complexity_score=0.0,
        )
        _record(decision)
        return decision

    estimated_tokens = _estimate_tokens(request)
    complexity_score = _score_complexity(request)

    # ── Tier 1: Vision ────────────────────────────────────────────────────────
    if request.image_b64 or request.task_type == TaskType.VISION:
        tier   = ModelTier.VISION
        model  = settings.routing_vision_model
        reason = "image_attached" if request.image_b64 else "task_type=vision"

    # ── Tier 2: Code ──────────────────────────────────────────────────────────
    elif _is_code_request(request):
        tier   = ModelTier.CODE
        model  = settings.routing_code_model
        reason = f"code_task task_type={request.task_type.value}"

    # ── Tier 3: Fast ──────────────────────────────────────────────────────────
    elif (
        estimated_tokens <= settings.routing_fast_tier_token_threshold
        and complexity_score < settings.routing_fast_tier_complexity_threshold
    ):
        tier   = ModelTier.FAST
        model  = settings.routing_fast_model
        reason = (
            f"tokens={estimated_tokens}<={settings.routing_fast_tier_token_threshold}, "
            f"complexity={complexity_score:.2f}<{settings.routing_fast_tier_complexity_threshold}"
        )

    # ── Tier 4: Quality ───────────────────────────────────────────────────────
    else:
        tier   = ModelTier.QUALITY
        model  = settings.routing_quality_model
        reasons = []
        if estimated_tokens > settings.routing_fast_tier_token_threshold:
            reasons.append(f"tokens={estimated_tokens}>{settings.routing_fast_tier_token_threshold}")
        if complexity_score >= settings.routing_fast_tier_complexity_threshold:
            reasons.append(f"complexity={complexity_score:.2f}>={settings.routing_fast_tier_complexity_threshold}")
        reason = ", ".join(reasons)

    decision = RoutingDecision(
        tier=tier,
        model=model,
        reason=reason,
        estimated_tokens=estimated_tokens,
        complexity_score=complexity_score,
    )

    routing_ms = (time.perf_counter() - start) * 1000
    _record(decision)

    logger.info(
        "routing_decision",
        request_id=str(request.request_id),
        tier=tier.value,
        model=model,
        reason=reason,
        estimated_tokens=estimated_tokens,
        complexity_score=round(complexity_score, 3),
        routing_ms=round(routing_ms, 2),
    )

    return decision


def _record(decision: RoutingDecision) -> None:
    ROUTING_DECISIONS_TOTAL.labels(
        decision=decision.tier.value,
        reason=decision.reason[:64],
    ).inc()
    TOKENS_ESTIMATED_TOTAL.labels(model=decision.model).inc(decision.estimated_tokens)