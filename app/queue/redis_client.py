"""
Redis connection manager.

Provides:
- Async redis client for the FastAPI gateway (job status reads/writes)
- Sync redis client for Celery backend
- Redis Streams client for DLQ operations

One connection pool per process — never create clients ad-hoc.
"""
from __future__ import annotations

import redis.asyncio as aioredis
import redis as syncredis

from app.core.config import get_settings
from app.core.logging import get_logger

logger = get_logger(__name__)

# ── Keys ──────────────────────────────────────────────────────────────────────
JOB_KEY_PREFIX = "job:"
DLQ_STREAM_KEY = "inference:dlq"
DLQ_GROUP_NAME = "dlq-processors"
RESULT_TTL_SECONDS = 3600  # job results expire after 1 hour

# ── Async client (FastAPI) ────────────────────────────────────────────────────
_async_client: aioredis.Redis | None = None


async def get_async_redis() -> aioredis.Redis:
    global _async_client
    if _async_client is None:
        settings = get_settings()
        _async_client = aioredis.from_url(
            settings.redis_url,
            encoding="utf-8",
            decode_responses=True,
            max_connections=20,
        )
        logger.info("redis_async_client_created", url=settings.redis_url)
    return _async_client


async def close_async_redis() -> None:
    global _async_client
    if _async_client:
        await _async_client.aclose()
        _async_client = None


# ── Sync client (Celery tasks) ────────────────────────────────────────────────
_sync_client: syncredis.Redis | None = None


def get_sync_redis() -> syncredis.Redis:
    global _sync_client
    if _sync_client is None:
        settings = get_settings()
        _sync_client = syncredis.from_url(
            settings.redis_url,
            encoding="utf-8",
            decode_responses=True,
        )
    return _sync_client


# ── Job key helpers ───────────────────────────────────────────────────────────

def job_key(job_id: str) -> str:
    return f"{JOB_KEY_PREFIX}{job_id}"