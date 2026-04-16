from __future__ import annotations

import datetime
import logging

from .config import SDKConfig
from .utils import extract_stacktrace, get_server_info

logger = logging.getLogger("watchdock_errors")


def build_event(
    exc: BaseException | None,
    config: SDKConfig,
    message: str | None = None,
    request_context: dict | None = None,
) -> dict | None:
    """
    Build a Watchdock error event payload.

    Returns None if the event should be dropped (e.g., before_send returned None).
    """
    now = datetime.datetime.now(datetime.timezone.utc).isoformat()

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

    if request_context:
        if config.send_pii:
            event["request"] = request_context.get("request", {})
            event["user"] = request_context.get("user", {})
        else:
            req = dict(request_context.get("request", {}))
            req.pop("body", None)
            headers = dict(req.get("headers", {}))
            for sensitive in ("Authorization", "Cookie", "X-Api-Key"):
                headers.pop(sensitive, None)
            req["headers"] = headers
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
