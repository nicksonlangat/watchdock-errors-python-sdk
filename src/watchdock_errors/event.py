from __future__ import annotations

import datetime
import logging

from .config import SDKConfig
from .utils import extract_stacktrace, extract_trace_id, get_server_info, sanitize_url_and_query_params

logger = logging.getLogger("watchdock_errors")

#: Lowercased for comparison -- header casing isn't consistent across integrations (e.g.
#: Django's request.headers is Title-Case, but raw ASGI scope headers used by the FastAPI
#: integration are always lowercase per spec), so matching by exact Title-Case key silently
#: let Authorization/Cookie/X-Api-Key through unscrubbed for any integration that doesn't
#: happen to produce Django's casing.
_SENSITIVE_HEADER_NAMES = {"authorization", "cookie", "set-cookie", "x-api-key"}


def build_event(
    exc: BaseException | None,
    config: SDKConfig,
    message: str | None = None,
    level: str | None = None,
    request_context: dict | None = None,
    trace_id: str | None = None,
) -> dict | None:
    """
    Build a Watchdock error event payload.

    Returns None if the event should be dropped (e.g., before_send returned None).
    """
    now = datetime.datetime.now(datetime.timezone.utc).isoformat()

    if level is None:
        level = "error" if exc is not None else "info"

    if exc is not None:
        exception_data = {
            "type": type(exc).__name__,
            "message": str(exc),
            "stacktrace": extract_stacktrace(exc),
        }
        title = message or f"{type(exc).__name__}: {str(exc)}"
    else:
        exception_data = {
            "type": "Message",
            "message": message or "",
            "stacktrace": [],
        }
        title = message or ""

    event: dict = {
        "project_key": config.api_key,
        "timestamp": now,
        "environment": config.environment,
        "level": level,
        "title": title,
        "sdk": {
            "name": config.sdk_name,
            "version": config.sdk_version,
        },
        "exception": exception_data,
        "server": get_server_info(),
    }

    if config.release:
        event["release"] = config.release

    if config.server_name:
        event["server"]["server_name"] = config.server_name

    resolved_trace_id = trace_id or (
        extract_trace_id(request_context.get("request", {}).get("headers", {})) if request_context else None
    )
    if resolved_trace_id:
        event["trace_id"] = resolved_trace_id

    if request_context:
        if config.send_pii:
            event["request"] = request_context.get("request", {})
            event["user"] = request_context.get("user", {})
        else:
            req = dict(request_context.get("request", {}))
            req.pop("body", None)
            req["headers"] = {
                key: value
                for key, value in req.get("headers", {}).items()
                if key.lower() not in _SENSITIVE_HEADER_NAMES
            }
            if "url" in req or "query_params" in req:
                sanitized_url, sanitized_params = sanitize_url_and_query_params(
                    req.get("url", ""), req.get("query_params")
                )
                if "url" in req:
                    req["url"] = sanitized_url
                if "query_params" in req:
                    req["query_params"] = sanitized_params
            event["request"] = req

    if config.before_send is not None:
        try:
            event = config.before_send(event)
        except Exception:
            logger.exception("watchdock_errors: before_send hook raised an exception")
            return None
        if event is None:
            return None

    return event
