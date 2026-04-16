"""
Django integration for watchdock-errors.

Option A — INSTALLED_APPS (auto-registers middleware via AppConfig signal):
    INSTALLED_APPS = [
        ...
        "watchdock_errors.integrations.django",
    ]

Option B — MIDDLEWARE (explicit):
    MIDDLEWARE = [
        ...
        "watchdock_errors.integrations.django.DjangoErrorMiddleware",
    ]
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import watchdock_errors

if TYPE_CHECKING:
    from django.http import HttpRequest, HttpResponse


class DjangoErrorMiddleware:
    """
    Django middleware that captures unhandled exceptions and forwards them
    to Watchdock without interfering with normal Django error handling.
    """

    def __init__(self, get_response) -> None:
        self.get_response = get_response

    def __call__(self, request: "HttpRequest") -> "HttpResponse":
        return self.get_response(request)

    def process_exception(self, request: "HttpRequest", exception: Exception) -> None:
        watchdock_errors.capture_exception(exception, request_context=_build_request_context(request))
        return None


def _build_request_context(request: "HttpRequest") -> dict:
    ctx: dict = {
        "request": {
            "method": request.method,
            "url": request.build_absolute_uri(),
            "headers": dict(request.headers),
            "query_params": dict(request.GET),
        }
    }

    if hasattr(request, "user") and request.user and request.user.is_authenticated:
        ctx["user"] = {
            "id": str(request.user.pk),
            "email": getattr(request.user, "email", ""),
        }

    return ctx


# AppConfig for INSTALLED_APPS auto-discovery
try:
    from django.apps import AppConfig

    class WatchdockErrorsDjangoConfig(AppConfig):
        name = "watchdock_errors.integrations.django"
        label = "watchdock_errors_django"
        verbose_name = "Watchdock Errors"

        def ready(self) -> None:
            # Auto-inject middleware when added to INSTALLED_APPS.
            # We patch the middleware list rather than using signals so it works
            # with both sync and async Django.
            from django.conf import settings

            middleware_path = "watchdock_errors.integrations.django.DjangoErrorMiddleware"
            if middleware_path not in settings.MIDDLEWARE:
                settings.MIDDLEWARE = list(settings.MIDDLEWARE) + [middleware_path]

    default_app_config = "watchdock_errors.integrations.django.WatchdockErrorsDjangoConfig"

except ImportError:
    pass
