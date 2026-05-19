"""
Dead Letter Queue via Redis Streams.

When an inference job fails or times out, it is written to the DLQ stream
instead of being silently dropped. Jobs in the DLQ can be:
  - Inspected via the API
  - Replayed manually
  - Alerting triggered (future)

Redis Streams chosen over a simple list because:
  - Entries are persistent (survive Redis restart with AOF/RDB)
  - Consumer groups allow multiple processors
  - Each entry has a unique auto-generated ID + timestamp
  - XRANGE / XLEN give O(1) inspection

Stream key: inference:dlq
Entry fields:
  job_id, request_id, model, error, error_type, failed_at, payload (JSON)
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any

import redis as syncredis
import redis.asyncio as aioredis

from app.core.logging import get_logger
from app.queue.redis_client import (
    DLQ_STREAM_KEY,
    get_async_redis,
    get_sync_redis,
)

logger = get_logger(__name__)

# Max entries kept in DLQ stream (MAXLEN ~ trim to this)
DLQ_MAXLEN = 10_000


# ── Write (sync — called from Celery worker) ──────────────────────────────────

def push_to_dlq_sync(
    job_id: str,
    request_id: str,
    model: str,
    error: str,
    error_type: str,
    payload: dict[str, Any],
) -> str:
    """
    Write a failed job to the DLQ stream.
    Returns the Redis stream entry ID.
    Called from Celery task (sync context).
    """
    r = get_sync_redis()
    entry = {
        "job_id": job_id,
        "request_id": request_id,
        "model": model,
        "error": error[:500],  # cap error message length
        "error_type": error_type,
        "failed_at": datetime.now(timezone.utc).isoformat(),
        "payload": json.dumps(payload),
    }
    entry_id = r.xadd(DLQ_STREAM_KEY, entry, maxlen=DLQ_MAXLEN, approximate=True)
    logger.info(
        "dlq_entry_written",
        job_id=job_id,
        error_type=error_type,
        stream_entry_id=entry_id,
    )
    return entry_id


# ── Read (async — called from FastAPI) ────────────────────────────────────────

async def get_dlq_entries(limit: int = 50) -> list[dict[str, Any]]:
    """
    Returns the most recent DLQ entries (newest first).
    """
    r = await get_async_redis()
    # XREVRANGE reads newest first
    raw = await r.xrevrange(DLQ_STREAM_KEY, count=limit)
    entries = []
    for entry_id, fields in raw:
        entry = dict(fields)
        entry["stream_id"] = entry_id
        # Parse payload back to dict
        if "payload" in entry:
            try:
                entry["payload"] = json.loads(entry["payload"])
            except (json.JSONDecodeError, TypeError):
                pass
        entries.append(entry)
    return entries


async def get_dlq_length() -> int:
    r = await get_async_redis()
    return await r.xlen(DLQ_STREAM_KEY)


async def get_dlq_entry_by_job_id(job_id: str) -> dict[str, Any] | None:
    """Scan DLQ for a specific job_id. O(n) — for debugging only."""
    r = await get_async_redis()
    raw = await r.xrange(DLQ_STREAM_KEY)
    for entry_id, fields in raw:
        if fields.get("job_id") == job_id:
            entry = dict(fields)
            entry["stream_id"] = entry_id
            if "payload" in entry:
                try:
                    entry["payload"] = json.loads(entry["payload"])
                except (json.JSONDecodeError, TypeError):
                    pass
            return entry
    return None


async def delete_dlq_entry(stream_id: str) -> bool:
    """Remove a specific entry from the DLQ by stream ID."""
    r = await get_async_redis()
    deleted = await r.xdel(DLQ_STREAM_KEY, stream_id)
    return deleted > 0