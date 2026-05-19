"""
Async jobs endpoints.

POST /infer/async           — enqueue inference job, return job_id immediately
GET  /jobs/{job_id}         — poll job status + result
GET  /jobs/{job_id}/dlq     — check if job is in DLQ
GET  /jobs/dlq              — list recent DLQ entries
DELETE /jobs/dlq/{stream_id} — remove entry from DLQ
"""
from __future__ import annotations

import time
import uuid
from typing import Any

from fastapi import APIRouter, HTTPException, status

from app.core.logging import get_logger
from app.core.metrics import INFERENCE_REQUESTS_TOTAL
from app.models.schemas import InferenceRequest
from app.queue.dlq import (
    delete_dlq_entry,
    get_dlq_entries,
    get_dlq_entry_by_job_id,
    get_dlq_length,
)
from app.queue.job_store import JobStatus, create_job_async, get_job
from app.worker.tasks import run_inference_task

router = APIRouter(tags=["jobs"])
logger = get_logger(__name__)


# ── Enqueue ───────────────────────────────────────────────────────────────────

@router.post(
    "/infer/async",
    status_code=status.HTTP_202_ACCEPTED,
    summary="Enqueue async inference job",
    response_description="Job accepted — poll /jobs/{job_id} for result",
)
async def enqueue_inference(request: InferenceRequest) -> dict[str, Any]:
    """
    Enqueues an inference request and returns immediately with a job_id.
    The job is processed by a Celery worker in the background.

    Poll GET /jobs/{job_id} until status is 'success' or 'failed'.
    """
    job_id = str(uuid.uuid4())
    enqueued_at = time.time()

    # Serialise request — Celery tasks must receive JSON-serialisable args
    payload = request.model_dump(mode="json")
    payload["request_id"] = str(request.request_id)

    # Write initial job record to Redis
    await create_job_async(job_id, payload)

    # Dispatch to Celery
    run_inference_task.apply_async(
        args=[job_id, payload],
        task_id=job_id,
        queue="inference",
    )

    INFERENCE_REQUESTS_TOTAL.labels(
        model="pending", tier="pending", status="queued"
    ).inc()

    logger.info(
        "job_enqueued",
        job_id=job_id,
        request_id=str(request.request_id),
        task_type=request.task_type.value,
    )

    return {
        "job_id": job_id,
        "status": JobStatus.QUEUED.value,
        "enqueued_at": enqueued_at,
        "poll_url": f"/jobs/{job_id}",
    }


# ── Poll ──────────────────────────────────────────────────────────────────────

@router.get(
    "/jobs/{job_id}",
    summary="Poll job status and result",
)
async def get_job_status(job_id: str) -> dict[str, Any]:
    """
    Returns current job status.

    Possible statuses:
    - queued: waiting for a worker
    - processing: worker is running inference
    - success: result available in 'content' field
    - failed: error in 'error' field, may be in DLQ
    - timeout: exceeded SLA, written to DLQ
    """
    job = await get_job(job_id)
    if job is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Job {job_id} not found. It may have expired (TTL: 1 hour).",
        )
    return job


# ── DLQ ───────────────────────────────────────────────────────────────────────

@router.get(
    "/jobs/dlq/entries",
    summary="List recent DLQ entries",
)
async def list_dlq(limit: int = 50) -> dict[str, Any]:
    """
    Returns the most recent dead-letter queue entries (newest first).
    These are jobs that failed after all retries or exceeded SLA timeout.
    """
    entries = await get_dlq_entries(limit=min(limit, 200))
    length = await get_dlq_length()
    return {
        "total": length,
        "returned": len(entries),
        "entries": entries,
    }


@router.get(
    "/jobs/{job_id}/dlq",
    summary="Check if a specific job is in the DLQ",
)
async def get_job_dlq_entry(job_id: str) -> dict[str, Any]:
    """
    Looks up a specific job in the DLQ by job_id.
    Returns the DLQ entry if found, 404 if not in DLQ.
    """
    entry = await get_dlq_entry_by_job_id(job_id)
    if entry is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Job {job_id} not found in DLQ.",
        )
    return entry


@router.delete(
    "/jobs/dlq/{stream_id}",
    summary="Remove a DLQ entry",
    status_code=status.HTTP_200_OK,
)
async def remove_dlq_entry(stream_id: str) -> dict[str, str]:
    """
    Removes a specific entry from the DLQ by Redis stream ID.
    Use after manually resolving a failed job.
    """
    deleted = await delete_dlq_entry(stream_id)
    if not deleted:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Stream entry {stream_id} not found in DLQ.",
        )
    return {"deleted": stream_id, "status": "removed"}