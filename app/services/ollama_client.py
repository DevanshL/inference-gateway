"""
Async Ollama client.

Responsibilities:
- Send inference requests to Ollama's HTTP API
- Handle retries with exponential backoff (tenacity)
- Stream responses token-by-token via async generator
- Measure first-token latency separately from total latency
- Expose health check (list models)
"""
from __future__ import annotations

import json
import time
from collections.abc import AsyncGenerator
from typing import Any

import httpx
from tenacity import (
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

from app.core.config import get_settings
from app.core.logging import get_logger
from app.core.metrics import (
    OLLAMA_ERRORS_TOTAL,
    MODEL_FIRST_TOKEN_LATENCY_SECONDS,
    INFERENCE_LATENCY_SECONDS,
)
from app.core.tracing import get_tracer
from app.models.schemas import InferenceRequest, Message, ModelTier

logger = get_logger(__name__)

# Tracer initialised lazily — safe when imported in Celery worker context
def _get_tracer():
    return get_tracer(__name__)

# Ollama /api/chat payload format
_OLLAMA_CHAT_PATH = "/api/chat"
_OLLAMA_TAGS_PATH = "/api/tags"
_OLLAMA_GENERATE_PATH = "/api/generate"


def _build_ollama_messages(
    messages: list[Message],
    image_b64: str | None = None,
) -> list[dict]:
    """Build Ollama chat messages. Attaches image to last user message for vision models."""
    result = [{"role": m.role, "content": m.content} for m in messages]
    if image_b64:
        # Ollama vision: images must be in the last user message as a list of base64 strings
        for msg in reversed(result):
            if msg["role"] == "user":
                msg["images"] = [image_b64]
                break
    return result


class OllamaClient:
    """
    Async HTTP client for Ollama.
    One instance per process — reuses connection pool.
    """

    def __init__(self) -> None:
        settings = get_settings()
        self._base_url = settings.ollama_base_url
        self._timeout = settings.ollama_timeout
        self._max_retries = settings.ollama_max_retries
        self._client: httpx.AsyncClient | None = None

    async def _get_client(self) -> httpx.AsyncClient:
        if self._client is None or self._client.is_closed:
            self._client = httpx.AsyncClient(
                base_url=self._base_url,
                timeout=httpx.Timeout(
                    connect=10.0,
                    read=self._timeout,
                    write=30.0,
                    pool=5.0,
                ),
                limits=httpx.Limits(
                    max_connections=50,
                    max_keepalive_connections=20,
                ),
                headers={"Content-Type": "application/json"},
            )
        return self._client

    async def close(self) -> None:
        if self._client and not self._client.is_closed:
            await self._client.aclose()

    # ── Health ─────────────────────────────────────────────────────────────────

    async def list_models(self) -> list[str]:
        """Returns list of pulled model names. Used by health endpoint."""
        with _get_tracer().start_as_current_span("ollama.list_models"):
            client = await self._get_client()
            try:
                resp = await client.get(_OLLAMA_TAGS_PATH)
                resp.raise_for_status()
                data = resp.json()
                return [m["name"] for m in data.get("models", [])]
            except Exception as e:
                logger.warning("ollama_list_models_failed", error=str(e))
                return []

    async def health_check(self) -> tuple[bool, float | None]:
        """Ping Ollama. Returns (is_healthy, latency_ms)."""
        start = time.perf_counter()
        try:
            client = await self._get_client()
            resp = await client.get("/", timeout=5.0)
            latency_ms = (time.perf_counter() - start) * 1000
            return resp.status_code == 200, round(latency_ms, 2)
        except Exception:
            return False, None

    # ── Inference ──────────────────────────────────────────────────────────────

    async def infer(
        self,
        request: InferenceRequest,
        model: str,
        tier: ModelTier,
    ) -> tuple[str, dict[str, Any]]:
        """
        Non-streaming inference.
        Returns (content_text, raw_ollama_response).
        """
        with _get_tracer().start_as_current_span("ollama.infer") as span:
            span.set_attribute("model", model)
            span.set_attribute("tier", tier.value)
            span.set_attribute("request_id", str(request.request_id))

            # LLaVA requires /api/generate (images field) not /api/chat
            if request.image_b64:
                last_user_msg = next(
                    (m.content for m in reversed(request.messages) if m.role == "user"), ""
                )
                payload = {
                    "model": model,
                    "prompt": last_user_msg,
                    "images": [request.image_b64],
                    "stream": False,
                    "options": {
                        "temperature": request.temperature,
                        "num_predict": min(request.max_tokens, 512),
                        "num_ctx": 2048,   # cap context — 32K default crashes LLaVA on 32GB RAM
                    },
                }
                start_total = time.perf_counter()
                try:
                    client = await self._get_client()
                    resp = await client.post(_OLLAMA_GENERATE_PATH, json=payload)
                    resp.raise_for_status()
                    raw = resp.json()
                except Exception as e:
                    OLLAMA_ERRORS_TOTAL.labels(model=model, error_type=type(e).__name__).inc()
                    span.record_exception(e)
                    raise
                total_s = time.perf_counter() - start_total
                INFERENCE_LATENCY_SECONDS.labels(model=model, tier=tier.value).observe(total_s)
                content = raw.get("response", "")
                span.set_attribute("response_length", len(content))
                return content, raw

            # All other tiers use /api/chat
            payload = {
                "model": model,
                "messages": _build_ollama_messages(request.messages),
                "stream": False,
                "options": {
                    "temperature": request.temperature,
                    "num_predict": request.max_tokens,
                },
            }

            start_total = time.perf_counter()
            try:
                response = await self._infer_with_retry(payload, model, tier)
            except Exception as e:
                OLLAMA_ERRORS_TOTAL.labels(model=model, error_type=type(e).__name__).inc()
                span.record_exception(e)
                raise

            total_s = time.perf_counter() - start_total
            INFERENCE_LATENCY_SECONDS.labels(model=model, tier=tier.value).observe(total_s)

            content = response.get("message", {}).get("content", "")
            span.set_attribute("response_length", len(content))
            return content, response

    @retry(
        retry=retry_if_exception_type((httpx.ConnectError, httpx.TimeoutException)),
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=0.5, min=0.5, max=8),
        reraise=True,
    )
    async def _infer_with_retry(
        self, payload: dict, model: str, tier: ModelTier
    ) -> dict[str, Any]:
        client = await self._get_client()
        resp = await client.post(_OLLAMA_CHAT_PATH, json=payload)
        resp.raise_for_status()
        return resp.json()

    async def infer_stream(
        self,
        request: InferenceRequest,
        model: str,
        tier: ModelTier,
    ) -> AsyncGenerator[str, None]:
        """
        Streaming inference — yields text chunks as they arrive.
        First token latency is measured and recorded separately.
        """
        with _get_tracer().start_as_current_span("ollama.infer_stream") as span:
            span.set_attribute("model", model)
            span.set_attribute("tier", tier.value)
            span.set_attribute("request_id", str(request.request_id))

            is_vision = bool(request.image_b64)
            path = _OLLAMA_GENERATE_PATH if is_vision else _OLLAMA_CHAT_PATH

            if is_vision:
                last_user_msg = next(
                    (m.content for m in reversed(request.messages) if m.role == "user"), ""
                )
                payload = {
                    "model": model,
                    "prompt": last_user_msg,
                    "images": [request.image_b64],
                    "stream": True,
                    "options": {
                        "temperature": request.temperature,
                        "num_predict": min(request.max_tokens, 512),
                        "num_ctx": 2048,  # Cap context size to avoid vision OOM
                    },
                }
            else:
                payload = {
                    "model": model,
                    "messages": _build_ollama_messages(request.messages),
                    "stream": True,
                    "options": {
                        "temperature": request.temperature,
                        "num_predict": request.max_tokens,
                    },
                }

            client = await self._get_client()
            start = time.perf_counter()
            first_token_recorded = False

            try:
                async with client.stream("POST", path, json=payload) as resp:
                    resp.raise_for_status()
                    async for line in resp.aiter_lines():
                        if not line.strip():
                            continue
                        try:
                            chunk = json.loads(line)
                        except json.JSONDecodeError:
                            continue

                        if is_vision:
                            token = chunk.get("response", "")
                        else:
                            token = chunk.get("message", {}).get("content", "")

                        if token and not first_token_recorded:
                            first_token_s = time.perf_counter() - start
                            MODEL_FIRST_TOKEN_LATENCY_SECONDS.labels(model=model).observe(
                                first_token_s
                            )
                            first_token_recorded = True

                        if token:
                            yield token

                        if chunk.get("done"):
                            break

            except Exception as e:
                OLLAMA_ERRORS_TOTAL.labels(model=model, error_type=type(e).__name__).inc()
                span.record_exception(e)
                raise


# ── Singleton ──────────────────────────────────────────────────────────────────
# One client instance shared across the app lifecycle

_ollama_client: OllamaClient | None = None


def get_ollama_client() -> OllamaClient:
    global _ollama_client
    if _ollama_client is None:
        _ollama_client = OllamaClient()
    return _ollama_client