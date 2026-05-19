import asyncio
from typing import Any
from celery.exceptions import SoftTimeLimitExceeded

from app.core.logging import get_logger
from app.models.schemas import InferenceRequest
from app.queue.job_store import (
    update_job_processing_sync,
    complete_job_sync,
    fail_job_sync,
    JobStatus,
)
from app.queue.dlq import push_to_dlq_sync
from app.worker.celery_app import celery_app
from app.services.inference import run_inference
from app.services import router

logger = get_logger(__name__)

@celery_app.task(bind=True, max_retries=3, acks_late=True)
def run_inference_task(self, job_id: str, payload: dict[str, Any]):
    request = InferenceRequest(**payload)
    
    # Get routing decision upfront to update job processing state
    decision = router.route(request)
    
    update_job_processing_sync(
        job_id=job_id, 
        model=decision.model, 
        tier=decision.tier.value
    )
    
    try:
        response = asyncio.run(run_inference(request))
        
        if response.status == "success":
            complete_job_sync(
                job_id=job_id,
                content=response.content,
                model=response.model,
                tier=response.tier.value,
                latency=response.latency.model_dump(),
                usage=response.usage.model_dump() if response.usage else None,
            )
        else:
            raise Exception(response.error)
            
    except SoftTimeLimitExceeded as e:
        logger.error("job_timeout", job_id=job_id, error=str(e))
        fail_job_sync(job_id, "SLA exceeded", JobStatus.TIMEOUT)
        push_to_dlq_sync(
            job_id=job_id,
            request_id=payload.get("request_id", ""),
            model=decision.model,
            error=str(e),
            error_type="SoftTimeLimitExceeded",
            payload=payload,
        )
    except Exception as exc:
        try:
            # Exponential backoff retry
            self.retry(exc=exc, countdown=2 ** self.request.retries)
        except self.MaxRetriesExceededError:
            logger.error("job_failed_max_retries", job_id=job_id, error=str(exc))
            fail_job_sync(job_id, str(exc), JobStatus.FAILED)
            push_to_dlq_sync(
                job_id=job_id,
                request_id=payload.get("request_id", ""),
                model=decision.model,
                error=str(exc),
                error_type=type(exc).__name__,
                payload=payload,
            )
