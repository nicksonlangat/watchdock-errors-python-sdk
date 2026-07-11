from __future__ import annotations

import linecache
import platform
import socket
import traceback


def extract_stacktrace(exc: BaseException) -> list[dict]:
    """Extract structured stack frames from an exception."""
    tb = exc.__traceback__
    if tb is None:
        return []

    frames = []
    for frame_summary in traceback.extract_tb(tb):
        context_line = linecache.getline(frame_summary.filename, frame_summary.lineno).strip()
        frames.append(
            {
                "filename": frame_summary.filename,
                "function": frame_summary.name,
                "lineno": frame_summary.lineno,
                "context_line": context_line,
            }
        )
    return frames


def get_server_info() -> dict:
    return {
        "hostname": socket.gethostname(),
        "python_version": platform.python_version(),
    }


def extract_trace_id(headers: dict | None) -> str | None:
    """
    Pull a correlation ID off incoming request headers so this event can be
    linked back to the nginx access/error log line for the same request.

    Prefers ``X-Request-Id`` (nginx's built-in ``$request_id``, zero extra
    modules required) and falls back to the trace-id segment of a W3C
    ``traceparent`` header if present.
    """
    if not headers:
        return None

    normalized = {str(k).lower(): v for k, v in headers.items()}

    request_id = normalized.get("x-request-id")
    if request_id:
        return request_id

    traceparent = normalized.get("traceparent")
    if traceparent:
        parts = traceparent.split("-")
        if len(parts) >= 2 and parts[1]:
            return parts[1]

    return None
