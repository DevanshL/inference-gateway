"""
/metrics endpoint — Prometheus scrape target.
"""
from fastapi import APIRouter
from fastapi.responses import Response

from app.core.metrics import get_metrics_output

router = APIRouter(tags=["observability"])


@router.get("/metrics", summary="Prometheus metrics scrape endpoint")
async def metrics() -> Response:
    body, content_type = get_metrics_output()
    return Response(content=body, media_type=content_type)