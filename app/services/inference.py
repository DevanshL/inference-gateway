"""
Inference orchestrator.

Flow per request:
  1. Route → get model + tier
  2. Call Ollama (non-streaming or streaming)
  3. Measure latency at every phase
  4. Emit metrics + structured log
  5. Return InferenceResponse
"""
from __future__ import annotations

import json
import time
from collections.abc import AsyncGenerator
from typing import Any
from uuid import UUID

import structlog

from app.core.logging import get_logger
from app.core.metrics import (
    ACTIVE_INFERENCE_REQUESTS,
    INFERENCE_REQUESTS_TOTAL,
)
from app.core.tracing import get_tracer
from app.models.schemas import (
    InferenceRequest,
    InferenceResponse,
    InferenceStatus,
    LatencyBreakdown,
    UsageStats,
)
from app.services import router as model_router
from app.services.ollama_client import get_ollama_client

logger = get_logger(__name__)

def _get_tracer():
    return get_tracer(__name__)


async def run_inference(request: InferenceRequest) -> InferenceResponse:
    """
    Full non-streaming inference pipeline.
    Never raises — errors captured in InferenceResponse.
    """
    with _get_tracer().start_as_current_span("inference.run") as span:
        span.set_attribute("request_id", str(request.request_id))
        span.set_attribute("task_type", request.task_type.value)

        ACTIVE_INFERENCE_REQUESTS.inc()
        total_start = time.perf_counter()

        # ── Phase 1: Route ─────────────────────────────────────────────────
        routing_start = time.perf_counter()
        decision = model_router.route(request)
        routing_ms = (time.perf_counter() - routing_start) * 1000

        span.set_attribute("model", decision.model)
        span.set_attribute("tier", decision.tier.value)

        # ── Phase 2: Infer ─────────────────────────────────────────────────
        model_start = time.perf_counter()
        status = InferenceStatus.SUCCESS
        content: str | None = None
        error: str | None = None
        usage: UsageStats | None = None
        raw: dict[str, Any] = {}

        try:
            client = get_ollama_client()
            content, raw = await client.infer(request, decision.model, decision.tier)

            # Extract usage from Ollama response if present
            if "prompt_eval_count" in raw:
                usage = UsageStats(
                    prompt_tokens=raw.get("prompt_eval_count", 0),
                    completion_tokens=raw.get("eval_count", 0),
                    total_tokens=raw.get("prompt_eval_count", 0) + raw.get("eval_count", 0),
                )

        except Exception as e:
            status = InferenceStatus.ERROR
            error = str(e)
            logger.error(
                "inference_failed",
                request_id=str(request.request_id),
                model=decision.model,
                error=error,
            )
            span.record_exception(e)

        model_ms = (time.perf_counter() - model_start) * 1000
        total_ms = (time.perf_counter() - total_start) * 1000

        ACTIVE_INFERENCE_REQUESTS.dec()
        INFERENCE_REQUESTS_TOTAL.labels(
            model=decision.model,
            tier=decision.tier.value,
            status=status.value,
        ).inc()

        logger.info(
            "inference_complete",
            request_id=str(request.request_id),
            status=status.value,
            model=decision.model,
            tier=decision.tier.value,
            total_ms=round(total_ms, 2),
            routing_ms=round(routing_ms, 2),
            model_ms=round(model_ms, 2),
            tokens=usage.total_tokens if usage else None,
        )

        return InferenceResponse(
            request_id=request.request_id,
            status=status,
            model=decision.model,
            tier=decision.tier,
            content=content,
            error=error,
            usage=usage,
            latency=LatencyBreakdown(
                routing_ms=round(routing_ms, 2),
                model_ms=round(model_ms, 2),
                total_ms=round(total_ms, 2),
            ),
            routing=decision,
        )


async def run_inference_stream(
    request: InferenceRequest,
) -> AsyncGenerator[str, None]:
    """
    Streaming inference pipeline.
    Yields SSE-formatted chunks: 'data: <token>\n\n'
    Final chunk: 'data: [DONE]\n\n'
    """
    with _get_tracer().start_as_current_span("inference.stream") as span:
        span.set_attribute("request_id", str(request.request_id))

        ACTIVE_INFERENCE_REQUESTS.inc()
        routing_start = time.perf_counter()
        decision = model_router.route(request)
        routing_ms = (time.perf_counter() - routing_start) * 1000

        span.set_attribute("model", decision.model)

        logger.info(
            "inference_stream_start",
            request_id=str(request.request_id),
            model=decision.model,
            routing_ms=round(routing_ms, 2),
        )

        try:
            client = get_ollama_client()
            async for token in client.infer_stream(request, decision.model, decision.tier):
                yield f"data: {json.dumps(token)}\n\n"

            INFERENCE_REQUESTS_TOTAL.labels(
                model=decision.model,
                tier=decision.tier.value,
                status=InferenceStatus.SUCCESS.value,
            ).inc()

        except Exception as e:
            logger.error(
                "inference_stream_failed",
                request_id=str(request.request_id),
                error=str(e),
            )
            INFERENCE_REQUESTS_TOTAL.labels(
                model=decision.model,
                tier=decision.tier.value,
                status=InferenceStatus.ERROR.value,
            ).inc()
            yield f"data: [ERROR] {e}\n\n"
        finally:
            ACTIVE_INFERENCE_REQUESTS.dec()
            yield "data: [DONE]\n\n"