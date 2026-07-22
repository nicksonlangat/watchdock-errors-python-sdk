from __future__ import annotations

import linecache
import platform
import socket
import traceback


#: Number of source lines captured on each side of the failing line. Matches the
#: window the backend uses when it falls back to enriching frames itself, so a
#: frame looks the same whether the context came from here or from the server.
CONTEXT_LINES = 2


def _source_context(filename: str, lineno: int) -> tuple[list[str], list[str]]:
    """Read the source lines immediately before and after ``lineno``.

    Returns ``(pre_context, post_context)``. We do this in the SDK, on the box
    where the code actually runs, because the source is here — the backend can
    only guess at it from its own filesystem, which is the wrong machine for any
    real app. Out-of-range lines come back as empty strings so the two lists are
    always the same length regardless of where in the file the error landed.
    """
    if not filename or not lineno:
        return [], []

    pre = [
        linecache.getline(filename, i).rstrip("\n")
        for i in range(max(1, lineno - CONTEXT_LINES), lineno)
    ]
    post = [
        linecache.getline(filename, i).rstrip("\n")
        for i in range(lineno + 1, lineno + CONTEXT_LINES + 1)
    ]
    return pre, post


def extract_stacktrace(exc: BaseException) -> list[dict]:
    """Extract structured stack frames from an exception."""
    tb = exc.__traceback__
    if tb is None:
        return []

    frames = []
    for frame_summary in traceback.extract_tb(tb):
        context_line = linecache.getline(frame_summary.filename, frame_summary.lineno).strip()
        pre_context, post_context = _source_context(frame_summary.filename, frame_summary.lineno)
        frames.append(
            {
                "filename": frame_summary.filename,
                "function": frame_summary.name,
                "lineno": frame_summary.lineno,
                "context_line": context_line,
                "pre_context": pre_context,
                "post_context": post_context,
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
