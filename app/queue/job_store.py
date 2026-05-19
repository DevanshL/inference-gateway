"""
Job store — persists async job state in Redis.

Job lifecycle:
  queued → processing → success | failed | timeout

Each job stored as a Redis hash at key job:<job_id>
TTL: 1 hour after completion (configurable)
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from enum import Enum
from typing import Any

import redis.asyncio as aioredis
import redis as syncredis

from app.queue.redis_client import (
    RESULT_TTL_SECONDS,
    get_async_redis,
    get_sync_redis,
    job_key,
)


class JobStatus(str, Enum):
    QUEUED = "queued"
    PROCESSING = "processing"
    SUCCESS = "success"
    FAILED = "failed"
    TIMEOUT = "timeout"


# ── Sync operations (Celery worker) ──────────────────────────────────────────

def create_job_sync(job_id: str, request_payload: dict[str, Any]) -> None:
    """Called when job is first enqueued — before Celery picks it up."""
    r = get_sync_redis()
    now = datetime.now(timezone.utc).isoformat()
    r.hset(job_key(job_id), mapping={
        "job_id": job_id,
        "status": JobStatus.QUEUED.value,
        "created_at": now,
        "updated_at": now,
        "payload": json.dumps(request_payload),
    })
    r.expire(job_key(job_id), RESULT_TTL_SECONDS)


def update_job_processing_sync(job_id: str, model: str, tier: str) -> None:
    r = get_sync_redis()
    r.hset(job_key(job_id), mapping={
        "status": JobStatus.PROCESSING.value,
        "model": model,
        "tier": tier,
        "updated_at": datetime.now(timezone.utc).isoformat(),
    })


def complete_job_sync(
    job_id: str,
    content: str,
    model: str,
    tier: str,
    latency: dict[str, Any],
    usage: dict[str, Any] | None,
) -> None:
    r = get_sync_redis()
    r.hset(job_key(job_id), mapping={
        "status": JobStatus.SUCCESS.value,
        "content": content,
        "model": model,
        "tier": tier,
        "latency": json.dumps(latency),
        "usage": json.dumps(usage) if usage else "",
        "updated_at": datetime.now(timezone.utc).isoformat(),
    })
    r.expire(job_key(job_id), RESULT_TTL_SECONDS)


def fail_job_sync(job_id: str, error: str, status: JobStatus = JobStatus.FAILED) -> None:
    r = get_sync_redis()
    r.hset(job_key(job_id), mapping={
        "status": status.value,
        "error": error[:500],
        "updated_at": datetime.now(timezone.utc).isoformat(),
    })
    r.expire(job_key(job_id), RESULT_TTL_SECONDS)


# ── Async operations (FastAPI) ────────────────────────────────────────────────

async def get_job(job_id: str) -> dict[str, Any] | None:
    r = await get_async_redis()
    data = await r.hgetall(job_key(job_id))
    if not data:
        return None
    # Deserialise nested JSON fields
    for field in ("latency", "usage", "payload"):
        if data.get(field):
            try:
                data[field] = json.loads(data[field])
            except (json.JSONDecodeError, TypeError):
                pass
    return data


async def create_job_async(job_id: str, request_payload: dict[str, Any]) -> None:
    """Used when gateway enqueues job before Celery picks it up."""
    r = await get_async_redis()
    now = datetime.now(timezone.utc).isoformat()
    await r.hset(job_key(job_id), mapping={
        "job_id": job_id,
        "status": JobStatus.QUEUED.value,
        "created_at": now,
        "updated_at": now,
        "payload": json.dumps(request_payload),
    })
    await r.expire(job_key(job_id), RESULT_TTL_SECONDS)