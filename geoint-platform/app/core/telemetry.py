from prometheus_client import Counter, Histogram

INGESTION_TOTAL = Counter(
    "geoint_ingestion_total",
    "Total ingestion attempts",
    ["source", "status"],
)

INGESTION_DURATION = Histogram(
    "geoint_ingestion_duration_seconds",
    "Ingestion duration",
    ["source"],
)

OBSERVATIONS_TOTAL = Counter(
    "geoint_observations_total",
    "Normalized observations",
    ["source", "entity_type"],
)

HTTP_REQUESTS = Counter(
    "geoint_http_requests_total",
    "HTTP requests",
    ["method", "path", "status"],
)


def setup_opentelemetry(settings) -> None:
    if not settings.otel_enabled:
        return

    from opentelemetry import trace
    from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import (
        OTLPSpanExporter,
    )
    from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
    from opentelemetry.sdk.resources import Resource
    from opentelemetry.sdk.trace import TracerProvider
    from opentelemetry.sdk.trace.export import BatchSpanProcessor

    resource = Resource.create(
        {
            "service.name": settings.otel_service_name,
            "deployment.environment": settings.app_env,
        }
    )

    provider = TracerProvider(resource=resource)
    exporter = OTLPSpanExporter(
        endpoint=settings.otel_exporter_otlp_endpoint,
        insecure=True,
    )

    provider.add_span_processor(BatchSpanProcessor(exporter))
    trace.set_tracer_provider(provider)

    FastAPIInstrumentor.instrument()

