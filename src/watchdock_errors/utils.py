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
