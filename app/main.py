"""
FastAPI application factory.

create_app() wires together:
  - Middleware stack
  - Routers
  - Lifespan (startup / shutdown hooks)
  - OTel instrumentation
  - Exception handlers
"""
from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.core.config import get_settings
from app.core.logging import get_logger, setup_logging
from app.core.tracing import setup_tracing, shutdown_tracing
from app.middleware.request_context import RequestContextMiddleware
from app.queue.redis_client import close_async_redis, get_async_redis
from app.core.rate_limit import limiter, rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from slowapi.middleware import SlowAPIMiddleware
from app.routers import health, infer, jobs, metrics
from app.services.ollama_client import get_ollama_client

logger = get_logger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = get_settings()
    logger.info(
        "gateway_starting",
        env=settings.gateway_env,
        fast_model=settings.routing_fast_model,
        quality_model=settings.routing_quality_model,
    )

    # Warm up Ollama
    client = get_ollama_client()
    is_healthy, latency = await client.health_check()
    if is_healthy:
        models = await client.list_models()
        logger.info("ollama_connected", latency_ms=latency, models=models)
    else:
        logger.warning("ollama_not_reachable_on_startup")

    # Warm up Redis
    try:
        redis = await get_async_redis()
        await redis.ping()
        logger.info("redis_connected", url=settings.redis_url)
    except Exception as e:
        logger.warning("redis_not_reachable_on_startup", error=str(e))

    yield

    logger.info("gateway_shutting_down")
    await client.close()
    await close_async_redis()
    shutdown_tracing()


def create_app() -> FastAPI:
    setup_logging()

    app = FastAPI(
        title="Async Inference Gateway",
        description=(
            "Smart LLM traffic controller. Routes requests to the optimal model "
            "based on complexity and token estimate. Full observability built-in."
        ),
        version="2.0.0",
        docs_url="/docs",
        redoc_url="/redoc",
        lifespan=lifespan,
    )

    setup_tracing(app)

    # Rate limiter
    app.state.limiter = limiter
    app.add_exception_handler(RateLimitExceeded, rate_limit_exceeded_handler)
    app.add_middleware(SlowAPIMiddleware)

    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.add_middleware(RequestContextMiddleware)

    app.include_router(health.router)
    app.include_router(infer.router)
    app.include_router(jobs.router)
    app.include_router(metrics.router)

    @app.exception_handler(Exception)
    async def unhandled_exception_handler(request: Request, exc: Exception) -> JSONResponse:
        logger.error(
            "unhandled_exception",
            path=request.url.path,
            method=request.method,
            error=str(exc),
            exc_info=True,
        )
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content={"detail": "Internal server error", "type": type(exc).__name__},
        )

    @app.get("/", include_in_schema=False)
    async def root():
        return {
            "service": "inference-gateway",
            "version": "2.0.0",
            "docs": "/docs",
            "health": "/health/ready",
            "metrics": "/metrics",
            "async_inference": "/infer/async",
            "jobs": "/jobs/{job_id}",
            "dlq": "/jobs/dlq/entries",
        }

    return app