"""
OpenTelemetry tracing initialisation.
Exports to Jaeger via OTLP gRPC.
Every inference request gets a root span; sub-operations are child spans.
"""
from opentelemetry import trace
from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor, ConsoleSpanExporter
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor

from app.core.config import get_settings
from app.core.logging import get_logger

logger = get_logger(__name__)
_tracer_provider: TracerProvider | None = None


def setup_tracing(app=None) -> None:
    global _tracer_provider
    settings = get_settings()

    resource = Resource.create({
        "service.name": settings.otel_service_name,
        "service.version": "1.0.0",
        "deployment.environment": settings.gateway_env,
    })

    _tracer_provider = TracerProvider(resource=resource)

    try:
        otlp_exporter = OTLPSpanExporter(
            endpoint=settings.otel_exporter_otlp_endpoint,
            insecure=True,
        )
        _tracer_provider.add_span_processor(BatchSpanProcessor(otlp_exporter))
        logger.info("otel_otlp_exporter_connected", endpoint=settings.otel_exporter_otlp_endpoint)
    except Exception as e:
        # Jaeger not running in dev — fall back to console exporter
        logger.warning("otel_otlp_unavailable_using_console", error=str(e))
        _tracer_provider.add_span_processor(BatchSpanProcessor(ConsoleSpanExporter()))

    trace.set_tracer_provider(_tracer_provider)

    if app is not None:
        FastAPIInstrumentor.instrument_app(app)

    logger.info("otel_tracing_initialised", service=settings.otel_service_name)


def get_tracer(name: str) -> trace.Tracer:
    return trace.get_tracer(name)


def shutdown_tracing() -> None:
    if _tracer_provider:
        _tracer_provider.shutdown()