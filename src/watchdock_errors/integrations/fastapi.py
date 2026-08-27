"""
FastAPI / Starlette integration for watchdock-errors.

Usage:
    from watchdock_errors.integrations.fastapi import setup_watchdock

    setup_watchdock(app)
"""

from __future__ import annotations

from typing import TYPE_CHECKING
from urllib.parse import parse_qs

import watchdock_errors

if TYPE_CHECKING:
    from fastapi import FastAPI
    from starlette.types import ASGIApp, Receive, Scope, Send


class WatchdockASGIMiddleware:
    """ASGI middleware that captures unhandled exceptions."""

    def __init__(self, app: "ASGIApp") -> None:
        self.app = app

    async def __call__(self, scope: "Scope", receive: "Receive", send: "Send") -> None:
        if scope["type"] not in ("http", "websocket"):
            await self.app(scope, receive, send)
            return

        try:
            await self.app(scope, receive, send)
        except Exception as exc:
            watchdock_errors.capture_exception(exc, request_context=_build_request_context(scope))
            raise


def _build_request_context(scope: dict) -> dict:
    # ASGI header names are always lowercase bytes per spec (unlike Django's Title-Case
    # request.headers) -- header scrubbing is case-insensitive, so this doesn't need to
    # match Django's casing, just be a dict of decoded strings.
    headers = {k.decode(): v.decode() for k, v in scope.get("headers", [])}
    query_string = scope.get("query_string", b"").decode()
    # dict, not the raw query string -- matches the shape every other integration produces
    # (and what sanitize_url_and_query_params/the frontend expect). Single-value params
    # come through as a plain string rather than a 1-item list, matching Django's shape.
    query_params = {key: values[0] if len(values) == 1 else values for key, values in parse_qs(query_string).items()}

    return {
        "request": {
            "method": scope.get("method", ""),
            "url": _build_url(scope),
            "headers": headers,
            "query_params": query_params,
        }
    }


def _build_url(scope: dict) -> str:
    scheme = scope.get("scheme", "http")
    server = scope.get("server")
    host = f"{server[0]}:{server[1]}" if server else "localhost"
    path = scope.get("path", "/")
    query = scope.get("query_string", b"").decode()
    return f"{scheme}://{host}{path}{'?' + query if query else ''}"


def setup_watchdock(app: "FastAPI") -> None:
    """
    Install the Watchdock ASGI error-capture middleware on a FastAPI app.

    Call this after ``watchdock_errors.init()`` and before adding other middleware.
    """
    app.add_middleware(WatchdockASGIMiddleware)
