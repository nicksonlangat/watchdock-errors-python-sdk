"""
watchdock-errors — Application error tracking SDK for the Watchdock platform.

Quickstart:
    import watchdock_errors

    watchdock_errors.init(api_key="wdk_xxx", environment="production")

    # Automatic capture via middleware (Django / FastAPI integrations).
    # Manual capture:
    try:
        risky_operation()
    except Exception as exc:
        watchdock_errors.capture_exception(exc)
"""

from __future__ import annotations

import sys
import logging
from typing import TYPE_CHECKING

try:
    from ._version import version as __version__
except ImportError:
    __version__ = "0.0.0"

if TYPE_CHECKING:
    from .config import SDKConfig
    from .client import WatchdockClient

__all__ = ["init", "capture_exception", "capture_message", "flush", "close", "__version__"]

_client: "WatchdockClient | None" = None
_config: "SDKConfig | None" = None

logger = logging.getLogger("watchdock_errors")


def init(
    api_key: str,
    endpoint: str = "https://api.watchdock.cc",
    environment: str = "production",
    release: str | None = None,
    server_name: str | None = None,
    send_pii: bool = False,
    before_send=None,
    timeout: float = 1.0,
) -> None:
    """
    Initialise the Watchdock Errors SDK.

    Must be called once at application startup before any errors are captured.
    """
    global _client, _config

    from .config import SDKConfig
    from .client import WatchdockClient

    _config = SDKConfig(
        api_key=api_key,
        endpoint=endpoint,
        environment=environment,
        release=release,
        server_name=server_name,
        send_pii=send_pii,
        before_send=before_send,
        timeout=timeout,
    )
    _client = WatchdockClient(_config)
    logger.info(
        "watchdock_errors: initialised — endpoint=%s environment=%s release=%s",
        _config.ingest_url,
        environment,
        release or "unset",
    )


def capture_exception(exc: BaseException | None = None, request_context: dict | None = None) -> None:
    """
    Capture an exception and send it to Watchdock.

    If ``exc`` is None the current exception from ``sys.exc_info()`` is used.
    Safe to call outside of an except block — does nothing if there is no
    active exception and ``exc`` is not provided.
    """
    if _client is None or _config is None:
        return

    if exc is None:
        exc_info = sys.exc_info()
        exc = exc_info[1]

    if exc is None:
        return

    from .event import build_event

    event = build_event(exc, _config, request_context=request_context)
    if event is not None:
        logger.info("watchdock_errors: capturing exception — %s: %s", type(exc).__name__, exc)
        _client.capture(event)
    else:
        logger.debug("watchdock_errors: event dropped by before_send hook")


def capture_message(message: str, request_context: dict | None = None) -> None:
    """Capture an arbitrary message string and send it to Watchdock."""
    if _client is None or _config is None:
        return

    from .event import build_event

    event = build_event(None, _config, message=message, request_context=request_context)
    if event is not None:
        logger.info("watchdock_errors: capturing message — %s", message)
        _client.capture(event)


def flush(timeout: float = 2.0) -> None:
    """Block until all queued events have been sent or timeout expires."""
    if _client is not None:
        _client.flush(timeout=timeout)


def close() -> None:
    """Gracefully shut down the SDK and drain the event queue."""
    global _client, _config
    if _client is not None:
        _client.close()
    _client = None
    _config = None
