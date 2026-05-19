"""
Celery application factory.

Broker:  Redis (same instance as job store)
Backend: Redis (task result backend — separate DB index)

Configuration:
- Prefetch 1 task at a time (inference tasks are long — don't hoard)
- Acks late — task re-queued if worker dies mid-execution
- Soft time limit = SLA timeout → raises SoftTimeLimitExceeded → DLQ
- Hard time limit = SLA + 30s → SIGKILL fallback
"""
from __future__ import annotations

from celery import Celery

from app.core.config import get_settings

settings = get_settings()

celery_app = Celery(
    "inference_gateway",
    broker=settings.redis_url,
    backend=settings.redis_url.replace("/0", "/1"),  # separate DB for results
    include=["app.worker.tasks"],
)

celery_app.conf.update(
    broker_connection_retry_on_startup=True,
    # Serialisation
    task_serializer="json",
    result_serializer="json",
    accept_content=["json"],

    # Reliability
    task_acks_late=True,               # re-queue if worker crashes
    worker_prefetch_multiplier=1,      # one task at a time per worker
    task_reject_on_worker_lost=True,   # re-queue if worker lost
    

    # Timeouts — SLA driven
    task_soft_time_limit=settings.routing_sla_timeout_ms // 1000,
    task_time_limit=(settings.routing_sla_timeout_ms // 1000) + 30,

    # Result expiry
    result_expires=3600,

    # Timezone
    timezone="UTC",
    enable_utc=True,

    # Task routing
    task_routes={
        "app.worker.tasks.run_inference_task": {"queue": "inference"},
    },

    # Queues
    task_default_queue="inference",
)