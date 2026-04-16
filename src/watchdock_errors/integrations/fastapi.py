"""
FastAPI / Starlette integration for watchdock-errors.

Usage:
    from watchdock_errors.integrations.fastapi import setup_watchdock

    setup_watchdock(app)
"""

from __future__ import annotations

from typing import TYPE_CHECKING

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
    headers = {k.decode(): v.decode() for k, v in scope.get("headers", [])}
    query_string = scope.get("query_string", b"").decode()

    return {
        "request": {
            "method": scope.get("method", ""),
            "url": _build_url(scope),
            "headers": headers,
            "query_params": query_string,
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
