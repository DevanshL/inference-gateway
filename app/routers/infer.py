"""
/infer endpoints.

POST /infer          — non-streaming inference
POST /infer/stream   — SSE streaming inference
POST /infer/route    — dry-run routing decision (no model call)
"""
from __future__ import annotations

from fastapi import APIRouter, status
from fastapi.responses import StreamingResponse

from app.core.logging import get_logger
from app.models.schemas import InferenceRequest, InferenceResponse, RoutingDecision
from app.services import router as model_router
from app.services.inference import run_inference, run_inference_stream

router = APIRouter(prefix="/infer", tags=["inference"])
logger = get_logger(__name__)


@router.post(
    "",
    response_model=InferenceResponse,
    summary="Run inference (non-streaming)",
    status_code=status.HTTP_200_OK,
)
async def infer(request: InferenceRequest) -> InferenceResponse:
    """
    Send a prompt to the gateway.
    The gateway selects the optimal model, runs inference, and returns the result
    with full latency breakdown and routing metadata.
    """
    return await run_inference(request)


@router.post(
    "/stream",
    summary="Run streaming inference (SSE)",
    status_code=status.HTTP_200_OK,
)
async def infer_stream(request: InferenceRequest) -> StreamingResponse:
    """
    Streaming inference via Server-Sent Events.
    Each chunk is: `data: <token>\n\n`
    Final chunk:   `data: [DONE]\n\n`
    """
    if request.stream is False:
        request = request.model_copy(update={"stream": True})

    return StreamingResponse(
        run_inference_stream(request),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )


@router.post(
    "/route",
    response_model=RoutingDecision,
    summary="Dry-run routing decision",
    status_code=status.HTTP_200_OK,
)
async def dry_run_route(request: InferenceRequest) -> RoutingDecision:
    """
    Returns the routing decision without calling any model.
    Useful for debugging routing logic and threshold tuning.
    """
    return model_router.route(request)