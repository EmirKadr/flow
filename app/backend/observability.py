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
OPERATION_ID_RE = re.compile(r"^[a-zA-Z0-9][a-zA-Z0-9_.:-]{5,79}$")
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
EVENT_ALLOWED_PATH_KEYS = {"api_route", "http_route", "page_path", "path", "route"}
EVENT_SENSITIVE_ATTR_PARTS = tuple(part for part in SENSITIVE_ATTR_PARTS if part != "path")

_fallback_trace_id: ContextVar[str | None] = ContextVar("flow_trace_id", default=None)
_operation_id: ContextVar[str | None] = ContextVar("flow_operation_id", default=None)
_logging_factory_installed = False
_otel_log_handler_installed = False
_otel_configured = False

try:  # pragma: no cover - exercised when optional OTel packages are installed.
    from opentelemetry import trace
    from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
    from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
    from opentelemetry.instrumentation.httpx import HTTPXClientInstrumentor
    from opentelemetry.instrumentation.requests import RequestsInstrumentor
    from opentelemetry.instrumentation.sqlalchemy import SQLAlchemyInstrumentor
    from opentelemetry.exporter.otlp.proto.http._log_exporter import OTLPLogExporter
    from opentelemetry.sdk._logs import LoggerProvider, LoggingHandler
    from opentelemetry.sdk._logs.export import BatchLogRecordProcessor
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
    OTLPLogExporter = None  # type: ignore[assignment]
    LoggerProvider = None  # type: ignore[assignment]
    LoggingHandler = None  # type: ignore[assignment]
    BatchLogRecordProcessor = None  # type: ignore[assignment]
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


def normalize_operation_id(value: str | None) -> str | None:
    text = str(value or "").strip()[:80]
    if OPERATION_ID_RE.fullmatch(text):
        return text
    return None


def trace_id_from_traceparent(value: str | None) -> str | None:
    match = TRACEPARENT_RE.match(str(value or "").strip().lower())
    if not match:
        return None
    return _valid_trace_id(match.group(1))


def new_trace_id() -> str:
    return secrets.token_hex(16)


def new_operation_id(prefix: str = "op") -> str:
    safe_prefix = re.sub(r"[^a-zA-Z0-9_.:-]+", "-", str(prefix or "op")).strip("-_.:")[:24] or "op"
    return f"{safe_prefix}-{secrets.token_hex(8)}"


def begin_request_trace(headers: Any) -> Any:
    incoming = None
    operation = None
    try:
        incoming = trace_id_from_traceparent(headers.get("traceparent")) or _valid_trace_id(headers.get("x-flow-trace-id"))
        operation = normalize_operation_id(headers.get("x-flow-operation-id")) or incoming
    except Exception:
        incoming = None
        operation = None
    trace_token = _fallback_trace_id.set(incoming or new_trace_id())
    operation_token = _operation_id.set(operation or new_operation_id("request"))
    return trace_token, operation_token


def end_request_trace(token: Any) -> None:
    if isinstance(token, tuple) and len(token) == 2:
        trace_token, operation_token = token
        _fallback_trace_id.reset(trace_token)
        _operation_id.reset(operation_token)
        return
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


def current_operation_id() -> str | None:
    return _operation_id.get()


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
    operation_id = current_operation_id()
    if operation_id:
        enriched.setdefault("operation_id", operation_id)
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


def _safe_event_path(value: Any) -> str:
    text = str(value or "").strip()[:300]
    if not text:
        return ""
    return text.split("?", 1)[0].split("#", 1)[0][:300]


def safe_event_attributes(attributes: dict[str, Any] | None) -> dict[str, Any]:
    cleaned: dict[str, Any] = {}
    for raw_key, raw_value in (attributes or {}).items():
        key = str(raw_key or "").strip().lower().replace(" ", "_")[:120]
        if not key:
            continue
        if key not in EVENT_ALLOWED_PATH_KEYS and any(part in key for part in EVENT_SENSITIVE_ATTR_PARTS):
            continue
        if raw_value is None:
            continue
        if key in EVENT_ALLOWED_PATH_KEYS:
            value = _safe_event_path(raw_value)
            if value:
                cleaned[key] = value
        elif isinstance(raw_value, bool):
            cleaned[key] = raw_value
        elif isinstance(raw_value, (int, float)):
            cleaned[key] = raw_value
        else:
            value = str(raw_value).replace("\r", " ").replace("\n", " ").strip()[:240]
            if value:
                cleaned[key] = value
    return cleaned


def emit_flow_event(
    name: str,
    *,
    feature: str,
    outcome: str = "ok",
    level: int = logging.INFO,
    message: str | None = None,
    attributes: dict[str, Any] | None = None,
    event_alias: str | None = None,
    logger_: logging.Logger | None = None,
    exc_info: Any = None,
) -> None:
    event_name = str(name or "").strip().lower()[:120]
    if not event_name:
        return
    cleaned = safe_event_attributes(attributes)
    operation_id = current_operation_id()
    trace_id = current_trace_id()
    extra = {
        "event.name": event_name,
        "event_name": event_name,
        "flow_event": event_alias or event_name,
        "feature": str(feature or "system")[:80],
        "outcome": str(outcome or "ok")[:40],
        "flow_trace_id": trace_id or "-",
        "operation.id": operation_id or "-",
        **cleaned,
    }
    target = logger_ or logger
    if message:
        target.log(level, message, extra=extra, exc_info=exc_info)
    else:
        target.log(
            level,
            "Flow event %s %s",
            event_name,
            str(outcome or "ok")[:40],
            extra=extra,
            exc_info=exc_info,
        )


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


def _log_level() -> int:
    configured = str(settings.OTEL_LOG_LEVEL or "WARNING").strip().upper()
    level = logging.getLevelName(configured)
    return level if isinstance(level, int) else logging.WARNING


def _resource() -> Any:
    if Resource is None:
        return None
    return Resource.create({  # type: ignore[union-attr]
        "service.name": settings.OTEL_SERVICE_NAME or "flow-web",
        "service.version": "0.1.5",
        "deployment.environment": settings.ENVIRONMENT,
        "flow.app": "flow",
    })


def _logs_endpoint(trace_endpoint: str) -> str:
    explicit = settings.OTEL_EXPORTER_OTLP_LOGS_ENDPOINT or os.getenv("OTEL_EXPORTER_OTLP_LOGS_ENDPOINT", "")
    if explicit:
        return explicit
    endpoint = trace_endpoint or settings.OTEL_EXPORTER_OTLP_ENDPOINT or os.getenv("OTEL_EXPORTER_OTLP_ENDPOINT", "")
    endpoint = endpoint.strip()
    if endpoint.endswith("/v1/traces"):
        return f"{endpoint[:-len('/v1/traces')]}/v1/logs"
    if endpoint and not endpoint.endswith("/v1/logs"):
        return f"{endpoint.rstrip('/')}/v1/logs"
    return endpoint


class _OtelLogFilter(logging.Filter):
    noisy_prefixes = (
        "opentelemetry.",
        "sqlalchemy.engine",
        "uvicorn.access",
    )

    def filter(self, record: logging.LogRecord) -> bool:
        return not record.name.startswith(self.noisy_prefixes)


def _install_otel_log_exporter(resource: Any, trace_endpoint: str) -> bool:
    global _otel_log_handler_installed
    if _otel_log_handler_installed or not settings.OTEL_LOGS_ENABLED:
        return False
    if LoggerProvider is None or LoggingHandler is None or BatchLogRecordProcessor is None or OTLPLogExporter is None:
        logger.warning("OTel log export is enabled but OpenTelemetry log packages are not installed.")
        return False
    endpoint = _logs_endpoint(trace_endpoint)
    if not endpoint:
        logger.warning("OTel log export is enabled but no OTLP logs endpoint is configured.")
        return False

    log_provider = LoggerProvider(resource=resource)
    log_provider.add_log_record_processor(
        BatchLogRecordProcessor(
            OTLPLogExporter(endpoint=endpoint, headers=_parse_headers(settings.OTEL_EXPORTER_OTLP_HEADERS))
        )
    )
    handler = LoggingHandler(level=_log_level(), logger_provider=log_provider)
    handler.set_name("flow-otel-log-exporter")
    handler.addFilter(_OtelLogFilter())
    logging.getLogger().addHandler(handler)
    logging.getLogger("app").setLevel(_log_level())
    logging.getLogger("app.backend").setLevel(_log_level())
    _otel_log_handler_installed = True
    return True


def _install_logging_record_factory() -> None:
    global _logging_factory_installed
    if _logging_factory_installed:
        return
    original_factory = logging.getLogRecordFactory()

    def factory(*args: Any, **kwargs: Any) -> logging.LogRecord:
        record = original_factory(*args, **kwargs)
        record.trace_id = current_trace_id() or "-"
        record.span_id = current_span_id() or "-"
        record.operation_id = current_operation_id() or "-"
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

    resource = _resource()
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
        if settings.OTEL_SQLALCHEMY_ENABLED and SQLAlchemyInstrumentor is not None and engine is not None:
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

    _install_otel_log_exporter(resource, endpoint)
    _otel_configured = True
    logger.info("OTel observability enabled for flow.")
    return True
