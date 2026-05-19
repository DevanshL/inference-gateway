"""
/health endpoints.

GET /health         — liveness probe (always 200 if process alive)
GET /health/ready   — readiness probe (checks Ollama connectivity)
GET /health/models  — lists available Ollama models
"""
from __future__ import annotations

import time

from fastapi import APIRouter, status
from fastapi.responses import JSONResponse

from app.core.config import get_settings
from app.core.logging import get_logger
from app.models.schemas import BackendHealth, HealthResponse
from app.services.ollama_client import get_ollama_client

router = APIRouter(prefix="/health", tags=["health"])
logger = get_logger(__name__)

_start_time = time.time()


@router.get(
    "",
    summary="Liveness probe",
    status_code=status.HTTP_200_OK,
)
async def liveness() -> dict:
    """Kubernetes liveness probe — returns 200 if the process is alive."""
    return {"status": "alive", "uptime_seconds": round(time.time() - _start_time, 1)}


@router.get(
    "/ready",
    response_model=HealthResponse,
    summary="Readiness probe",
)
async def readiness() -> JSONResponse:
    """
    Kubernetes readiness probe.
    Returns 200 if all backends healthy, 503 if any backend is down.
    """
    settings = get_settings()
    client = get_ollama_client()

    is_healthy, latency_ms = await client.health_check()
    models = await client.list_models() if is_healthy else []

    ollama_health = BackendHealth(
        name="ollama",
        available=is_healthy,
        models=models,
        latency_ms=latency_ms,
        error=None if is_healthy else "Ollama not reachable",
    )

    all_healthy = is_healthy
    http_status = status.HTTP_200_OK if all_healthy else status.HTTP_503_SERVICE_UNAVAILABLE

    body = HealthResponse(
        status="ready" if all_healthy else "degraded",
        env=settings.gateway_env,
        backends=[ollama_health],
        uptime_seconds=round(time.time() - _start_time, 1),
    )

    logger.info(
        "health_check",
        status=body.status,
        ollama_available=is_healthy,
        ollama_latency_ms=latency_ms,
        models=models,
    )

    return JSONResponse(content=body.model_dump(), status_code=http_status)


@router.get(
    "/models",
    summary="List available models",
)
async def list_models() -> dict:
    """Returns all models currently pulled in Ollama."""
    client = get_ollama_client()
    models = await client.list_models()
    settings = get_settings()
    return {
        "models": models,
        "fast_tier_model": settings.routing_fast_model,
        "quality_tier_model": settings.routing_quality_model,
    }