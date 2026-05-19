"""
Phase 2 tests.

Tests cover:
- Job store operations (sync)
- DLQ push/read (mocked Redis)
- Celery task routing logic
- Job status lifecycle
"""
import json
import pytest
from unittest.mock import MagicMock, patch
from uuid import uuid4

from app.queue.job_store import JobStatus


# ── Job status enum ───────────────────────────────────────────────────────────

def test_job_status_values():
    assert JobStatus.QUEUED.value == "queued"
    assert JobStatus.PROCESSING.value == "processing"
    assert JobStatus.SUCCESS.value == "success"
    assert JobStatus.FAILED.value == "failed"
    assert JobStatus.TIMEOUT.value == "timeout"


# ── Job store sync ops (mocked Redis) ────────────────────────────────────────

def test_create_job_sync_sets_queued_status():
    mock_redis = MagicMock()
    job_id = str(uuid4())

    with patch("app.queue.job_store.get_sync_redis", return_value=mock_redis):
        from app.queue.job_store import create_job_sync
        create_job_sync(job_id, {"messages": []})

    mock_redis.hset.assert_called_once()
    call_kwargs = mock_redis.hset.call_args[1]["mapping"]
    assert call_kwargs["status"] == JobStatus.QUEUED.value
    assert call_kwargs["job_id"] == job_id


def test_complete_job_sync_sets_success():
    mock_redis = MagicMock()
    job_id = str(uuid4())

    with patch("app.queue.job_store.get_sync_redis", return_value=mock_redis):
        from app.queue.job_store import complete_job_sync
        complete_job_sync(
            job_id=job_id,
            content="Four",
            model="mistral:latest",
            tier="fast",
            latency={"routing_ms": 1.0, "model_ms": 500.0, "total_ms": 501.0},
            usage={"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15},
        )

    call_kwargs = mock_redis.hset.call_args[1]["mapping"]
    assert call_kwargs["status"] == JobStatus.SUCCESS.value
    assert call_kwargs["content"] == "Four"
    assert call_kwargs["model"] == "mistral:latest"


def test_fail_job_sync_sets_failed():
    mock_redis = MagicMock()
    job_id = str(uuid4())

    with patch("app.queue.job_store.get_sync_redis", return_value=mock_redis):
        from app.queue.job_store import fail_job_sync
        fail_job_sync(job_id, "Connection refused")

    call_kwargs = mock_redis.hset.call_args[1]["mapping"]
    assert call_kwargs["status"] == JobStatus.FAILED.value
    assert "Connection refused" in call_kwargs["error"]


def test_fail_job_sync_timeout_status():
    mock_redis = MagicMock()
    job_id = str(uuid4())

    with patch("app.queue.job_store.get_sync_redis", return_value=mock_redis):
        from app.queue.job_store import fail_job_sync
        fail_job_sync(job_id, "SLA exceeded", JobStatus.TIMEOUT)

    call_kwargs = mock_redis.hset.call_args[1]["mapping"]
    assert call_kwargs["status"] == JobStatus.TIMEOUT.value


# ── DLQ push (mocked Redis) ───────────────────────────────────────────────────

def test_push_to_dlq_sync_calls_xadd():
    mock_redis = MagicMock()
    mock_redis.xadd.return_value = "1234567890-0"
    job_id = str(uuid4())

    with patch("app.queue.dlq.get_sync_redis", return_value=mock_redis):
        from app.queue.dlq import push_to_dlq_sync
        entry_id = push_to_dlq_sync(
            job_id=job_id,
            request_id=str(uuid4()),
            model="mistral:latest",
            error="timeout",
            error_type="SoftTimeLimitExceeded",
            payload={"messages": []},
        )

    assert entry_id == "1234567890-0"
    mock_redis.xadd.assert_called_once()
    call_args = mock_redis.xadd.call_args
    entry = call_args[0][1]  # second positional arg is the entry dict
    assert entry["job_id"] == job_id
    assert entry["error_type"] == "SoftTimeLimitExceeded"


def test_push_to_dlq_truncates_long_error():
    mock_redis = MagicMock()
    mock_redis.xadd.return_value = "1234-0"
    job_id = str(uuid4())

    with patch("app.queue.dlq.get_sync_redis", return_value=mock_redis):
        from app.queue.dlq import push_to_dlq_sync
        push_to_dlq_sync(
            job_id=job_id,
            request_id=str(uuid4()),
            model="mistral:latest",
            error="x" * 1000,  # very long error
            error_type="Exception",
            payload={},
        )

    entry = mock_redis.xadd.call_args[0][1]
    assert len(entry["error"]) <= 500


# ── Celery task imports ────────────────────────────────────────────────────────

def test_celery_app_importable():
    from app.worker.celery_app import celery_app
    assert celery_app.main == "inference_gateway"


def test_inference_task_registered():
    from app.worker.celery_app import celery_app
    from app.worker import tasks  # trigger registration
    assert "app.worker.tasks.run_inference_task" in celery_app.tasks


# ── Router enqueue schema ─────────────────────────────────────────────────────

def test_inference_request_serialises_for_celery():
    """Request must be fully JSON-serialisable to pass through Celery."""
    from app.models.schemas import InferenceRequest, Message
    req = InferenceRequest(
        messages=[Message(role="user", content="hello")],
    )
    payload = req.model_dump(mode="json")
    payload["request_id"] = str(req.request_id)
    # Must not raise
    serialised = json.dumps(payload)
    deserialised = json.loads(serialised)
    assert deserialised["messages"][0]["content"] == "hello"
