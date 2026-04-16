from __future__ import annotations

import logging
import queue
import threading
from typing import TYPE_CHECKING

import requests

if TYPE_CHECKING:
    from .config import SDKConfig

logger = logging.getLogger("watchdock_errors")


class WatchdockClient:
    """
    Non-blocking HTTP transport for error events.

    Events are enqueued and sent by a daemon background thread so the
    calling thread is never delayed by network I/O.
    """

    def __init__(self, config: SDKConfig) -> None:
        self._config = config
        self._queue: queue.Queue[dict | None] = queue.Queue(maxsize=100)
        self._thread = threading.Thread(target=self._worker, daemon=True, name="watchdock-errors")
        self._thread.start()
        logger.debug("watchdock_errors: background transport thread started")

    def capture(self, event: dict) -> None:
        """Enqueue an event for asynchronous delivery. Never blocks or raises."""
        try:
            self._queue.put_nowait(event)
            logger.debug("watchdock_errors: event enqueued (queue size ~%d)", self._queue.qsize())
        except queue.Full:
            logger.warning("watchdock_errors: event queue full — dropping event")

    def flush(self, timeout: float = 2.0) -> None:
        """Block until the queue is drained or timeout expires."""
        self._queue.join()

    def close(self) -> None:
        """Signal the worker thread to stop after draining the queue."""
        self._queue.put(None)
        self._thread.join(timeout=3.0)

    def _worker(self) -> None:
        while True:
            try:
                event = self._queue.get(timeout=0.5)
            except queue.Empty:
                continue

            if event is None:
                self._queue.task_done()
                break

            self._send(event)
            self._queue.task_done()

    def _send(self, event: dict) -> None:
        exc_type = event.get("exception", {}).get("type", "event")
        logger.info("watchdock_errors: sending %s to %s", exc_type, self._config.ingest_url)
        try:
            response = requests.post(
                self._config.ingest_url,
                json=event,
                headers={
                    "Authorization": f"Bearer {self._config.api_key}",
                    "Content-Type": "application/json",
                    "User-Agent": f"watchdock-errors/{self._config.sdk_version}",
                },
                timeout=self._config.timeout,
            )
            if response.status_code in (200, 201, 202):
                logger.info("watchdock_errors: event accepted (%s)", response.status_code)
            else:
                logger.warning(
                    "watchdock_errors: ingest rejected — status=%s body=%s",
                    response.status_code,
                    response.text[:500],
                )
        except requests.exceptions.ConnectionError as e:
            logger.error("watchdock_errors: connection failed — %s — is the endpoint reachable?", e)
        except requests.exceptions.Timeout:
            logger.error(
                "watchdock_errors: request timed out after %ss — endpoint=%s",
                self._config.timeout,
                self._config.ingest_url,
            )
        except Exception:
            logger.error("watchdock_errors: unexpected error sending event", exc_info=True)
