from __future__ import annotations

import logging
import os
import re
import secrets
from contextlib import contextmanager
from contextvars import ContextVar
from typing import Any, Iterator

from .config import settings

logger = logging.getLogger(__name__)

TRACEPARENT_RE = re.compile(r"^00-([0-9a-f]{32})-([0-9a-f]{16})-[0-9a-f]{2}$")
SENSITIVE_ATTR_PARTS = (
    "authorization",
    "body",
    "cookie",
    "customer",
    "filename",
    "filepath",
    "file_name",
    "file_path",
    "key",
    "order",
    "password",
    "path",
    "prompt",
    "request",
    "response",
    "secret",
    "text",
    "token",
    "url",
)

_fallback_trace_id: ContextVar[str | None] = ContextVar("flow_trace_id", default=None)
_logging_factory_installed = False
_otel_configured = False

try:  # pragma: no cover - exercised when optional OTel packages are installed.
    from opentelemetry import trace
    from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
    from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
    from opentelemetry.instrumentation.httpx import HTTPXClientInstrumentor
    from opentelemetry.instrumentation.requests import RequestsInstrumentor
    from opentelemetry.instrumentation.sqlalchemy import SQLAlchemyInstrumentor
    from opentelemetry.sdk.resources import Resource
    from opentelemetry.sdk.trace import TracerProvider
    from opentelemetry.sdk.trace.export import BatchSpanProcessor, ConsoleSpanExporter
    from opentelemetry.sdk.trace.sampling import ParentBased, TraceIdRatioBased
    from opentelemetry.trace import Status, StatusCode
except Exception:  # pragma: no cover - default local/dev path until deps are installed.
    trace = None  # type: ignore[assignment]
    OTLPSpanExporter = None  # type: ignore[assignment]
    FastAPIInstrumentor = None  # type: ignore[assignment]
    HTTPXClientInstrumentor = None  # type: ignore[assignment]
    RequestsInstrumentor = None  # type: ignore[assignment]
    SQLAlchemyInstrumentor = None  # type: ignore[assignment]
    Resource = None  # type: ignore[assignment]
    TracerProvider = None  # type: ignore[assignment]
    BatchSpanProcessor = None  # type: ignore[assignment]
    ConsoleSpanExporter = None  # type: ignore[assignment]
    ParentBased = None  # type: ignore[assignment]
    TraceIdRatioBased = None  # type: ignore[assignment]
    Status = None  # type: ignore[assignment]
    StatusCode = None  # type: ignore[assignment]


def _valid_trace_id(value: str | None) -> str | None:
    text = str(value or "").strip().lower()
    if len(text) == 32 and re.fullmatch(r"[0-9a-f]{32}", text) and text != "0" * 32:
        return text
    return None


def normalize_trace_id(value: str | None) -> str | None:
    return _valid_trace_id(value)


def trace_id_from_traceparent(value: str | None) -> str | None:
    match = TRACEPARENT_RE.match(str(value or "").strip().lower())
    if not match:
        return None
    return _valid_trace_id(match.group(1))


def new_trace_id() -> str:
    return secrets.token_hex(16)


def begin_request_trace(headers: Any) -> Any:
    incoming = None
    try:
        incoming = trace_id_from_traceparent(headers.get("traceparent")) or _valid_trace_id(headers.get("x-flow-trace-id"))
    except Exception:
        incoming = None
    return _fallback_trace_id.set(incoming or new_trace_id())


def end_request_trace(token: Any) -> None:
    _fallback_trace_id.reset(token)


def current_trace_id() -> str | None:
    if trace is not None:
        try:
            context = trace.get_current_span().get_span_context()
            if getattr(context, "is_valid", False):
                return f"{int(context.trace_id):032x}"
        except Exception:
            pass
    return _fallback_trace_id.get()


def current_span_id() -> str | None:
    if trace is None:
        return None
    try:
        context = trace.get_current_span().get_span_context()
        if getattr(context, "is_valid", False):
            return f"{int(context.span_id):016x}"
    except Exception:
        return None
    return None


def attach_trace_context(payload: dict[str, Any] | None) -> dict[str, Any] | None:
    if payload is None:
        return None
    trace_id = current_trace_id()
    if not trace_id:
        return payload
    enriched = dict(payload)
    enriched.setdefault("trace_id", trace_id)
    span_id = current_span_id()
    if span_id:
        enriched.setdefault("span_id", span_id)
    return enriched


def safe_span_attributes(attributes: dict[str, Any] | None) -> dict[str, Any]:
    cleaned: dict[str, Any] = {}
    for raw_key, raw_value in (attributes or {}).items():
        key = str(raw_key or "").strip().lower().replace(" ", "_")[:120]
        if not key or any(part in key for part in SENSITIVE_ATTR_PARTS):
            continue
        if raw_value is None:
            continue
        if isinstance(raw_value, bool):
            cleaned[key] = raw_value
        elif isinstance(raw_value, (int, float)):
            cleaned[key] = raw_value
        else:
            cleaned[key] = str(raw_value)[:240]
    return cleaned


def add_span_attributes(attributes: dict[str, Any] | None) -> None:
    if trace is None:
        return
    cleaned = safe_span_attributes(attributes)
    if not cleaned:
        return
    try:
        trace.get_current_span().set_attributes(cleaned)
    except Exception:
        pass


@contextmanager
def start_span(name: str, attributes: dict[str, Any] | None = None) -> Iterator[Any]:
    if trace is None:
        yield None
        return
    tracer = trace.get_tracer("flow.backend")
    with tracer.start_as_current_span(name) as span:
        cleaned = safe_span_attributes(attributes)
        if cleaned:
            span.set_attributes(cleaned)
        try:
            yield span
        except Exception as exc:
            try:
                span.record_exception(exc)
                if Status is not None and StatusCode is not None:
                    span.set_status(Status(StatusCode.ERROR, type(exc).__name__))
            except Exception:
                pass
            raise


def _parse_headers(value: str) -> dict[str, str]:
    headers: dict[str, str] = {}
    for item in str(value or "").split(","):
        if "=" not in item:
            continue
        key, raw = item.split("=", 1)
        key = key.strip()
        if key:
            headers[key] = raw.strip()
    return headers


def _install_logging_record_factory() -> None:
    global _logging_factory_installed
    if _logging_factory_installed:
        return
    original_factory = logging.getLogRecordFactory()

    def factory(*args: Any, **kwargs: Any) -> logging.LogRecord:
        record = original_factory(*args, **kwargs)
        record.trace_id = current_trace_id() or "-"
        record.span_id = current_span_id() or "-"
        return record

    logging.setLogRecordFactory(factory)
    _logging_factory_installed = True


def _sample_rate() -> float:
    try:
        return min(1.0, max(0.0, float(settings.OTEL_TRACES_SAMPLE_RATE)))
    except (TypeError, ValueError):
        return 0.1


def configure_observability(app: Any, *, engine: Any | None = None) -> bool:
    global _otel_configured
    _install_logging_record_factory()
    if _otel_configured:
        return True
    if not settings.OTEL_ENABLED:
        return False
    if trace is None or TracerProvider is None:
        logger.warning("OTel is enabled but OpenTelemetry packages are not installed.")
        return False

    resource = Resource.create({  # type: ignore[union-attr]
        "service.name": settings.OTEL_SERVICE_NAME or "flow-web",
        "service.version": "0.1.5",
        "deployment.environment": settings.ENVIRONMENT,
    })
    provider = TracerProvider(  # type: ignore[operator]
        resource=resource,
        sampler=ParentBased(TraceIdRatioBased(_sample_rate())),  # type: ignore[operator]
    )

    endpoint = settings.OTEL_EXPORTER_OTLP_ENDPOINT or os.getenv("OTEL_EXPORTER_OTLP_ENDPOINT", "")
    if endpoint and OTLPSpanExporter is not None:
        provider.add_span_processor(
            BatchSpanProcessor(  # type: ignore[operator]
                OTLPSpanExporter(endpoint=endpoint, headers=_parse_headers(settings.OTEL_EXPORTER_OTLP_HEADERS))
            )
        )
    if settings.OTEL_CONSOLE_EXPORTER and ConsoleSpanExporter is not None:
        provider.add_span_processor(BatchSpanProcessor(ConsoleSpanExporter()))  # type: ignore[operator]
    try:
        trace.set_tracer_provider(provider)
    except Exception:
        logger.warning("Could not install OTel tracer provider.", exc_info=True)
        return False

    try:
        if FastAPIInstrumentor is not None:
            FastAPIInstrumentor.instrument_app(app, excluded_urls="/api/health")
    except Exception:
        logger.warning("Could not instrument FastAPI with OTel.", exc_info=True)
    try:
        if SQLAlchemyInstrumentor is not None and engine is not None:
            SQLAlchemyInstrumentor().instrument(engine=engine)
    except Exception:
        logger.warning("Could not instrument SQLAlchemy with OTel.", exc_info=True)
    try:
        if RequestsInstrumentor is not None:
            RequestsInstrumentor().instrument()
    except Exception:
        logger.warning("Could not instrument requests with OTel.", exc_info=True)
    try:
        if HTTPXClientInstrumentor is not None:
            HTTPXClientInstrumentor().instrument()
    except Exception:
        logger.warning("Could not instrument httpx with OTel.", exc_info=True)

    _otel_configured = True
    logger.info("OTel observability enabled for flow.")
    return True
