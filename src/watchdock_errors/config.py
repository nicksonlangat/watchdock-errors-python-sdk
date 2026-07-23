from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable


def _get_version() -> str:
    try:
        from importlib.metadata import version
        return version("watchdock-errors")
    except Exception:
        pass
    try:
        from ._version import version as _v
        return _v
    except ImportError:
        return "0.0.0"


@dataclass
class SDKConfig:
    api_key: str
    endpoint: str = "https://api.watchdock.cc"
    environment: str = "production"
    release: str | None = None
    server_name: str | None = None
    send_pii: bool = False
    before_send: Callable[[dict], dict | None] | None = None
    timeout: float = 1.0

    # Internal — appended to every event payload
    sdk_name: str = field(default="watchdock-errors", init=False, repr=False)
    sdk_version: str = field(default_factory=_get_version, init=False, repr=False)

    @property
    def ingest_url(self) -> str:
        base = self.endpoint.rstrip("/")
        return f"{base}/api/v1/error-events/"
