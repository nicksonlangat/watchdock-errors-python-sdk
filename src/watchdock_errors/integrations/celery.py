"""
Celery integration for watchdock-errors — task registry + failure/retry reporting.

Two things get reported automatically once wired up:

1. Task registry: the customer's registered Celery tasks (and, for periodic
   tasks, their beat schedule), reported once per worker right after Celery
   finishes autodiscovering task modules. Tells Watchdock what tasks are
   expected to exist — the prerequisite for beat-schedule health checks.

2. Failures, retries, and revocations: every `task_failure`, `task_retry`,
   and `task_revoked` is reported as it happens, with the exception,
   traceback, task id/queue/worker hostname, and retry count vs.
   max_retries. Successful runs are not reported — only what a dev
   actually needs to see.

3. Heartbeats for periodic (beat-scheduled) tasks only: a lightweight ping
   on every `task_prerun` for a task name present in app.conf.beat_schedule,
   so Watchdock can tell when a periodic task has gone silent. Non-periodic
   tasks are never pinged — this stays cheap regardless of task volume.

Usage — call once from your Celery app module, after autodiscover_tasks():

    from celery import Celery
    from watchdock_errors.integrations.celery import register

    app = Celery("myproject")
    app.config_from_object("django.conf:settings", namespace="CELERY")
    app.autodiscover_tasks()

    register(app)

watchdock_errors.init() must have been called before these signals fire
(e.g. in a `worker_process_init` handler, or at import time) — if not,
the report is skipped.
"""

from __future__ import annotations

import logging
import threading
from typing import TYPE_CHECKING

import requests

if TYPE_CHECKING:
    from celery import Celery

logger = logging.getLogger("watchdock_errors")


def register(app: "Celery") -> None:
    """Wire up the Watchdock Celery integration on the given Celery app."""
    try:
        from celery.signals import task_failure, task_prerun, task_retry, task_revoked, worker_ready
    except ImportError:
        logger.warning("watchdock_errors: celery is not installed — Celery integration disabled")
        return

    periodic_task_names = set(_periodic_schedules_by_task_name(app).keys())

    @worker_ready.connect(weak=False)
    def _on_worker_ready(sender=None, **kwargs) -> None:
        _report_task_registry(app)

    @task_prerun.connect(weak=False)
    def _on_task_prerun(sender=None, task=None, **kwargs) -> None:
        name = getattr(task, "name", None) or getattr(sender, "name", None)
        if name in periodic_task_names:
            _report_heartbeat(name)

    @task_failure.connect(weak=False)
    def _on_task_failure(sender=None, task_id=None, exception=None, einfo=None, **kwargs) -> None:
        request = getattr(sender, "request", None)
        _report_execution(
            status="failure",
            task_id=task_id,
            task_name=getattr(sender, "name", None),
            queue=getattr(sender, "queue", None),
            worker_hostname=getattr(request, "hostname", None),
            retries=getattr(request, "retries", None),
            max_retries=getattr(sender, "max_retries", None),
            exception_type=type(exception).__name__ if exception is not None else "",
            exception_message=str(exception) if exception is not None else "",
            traceback=str(einfo) if einfo is not None else "",
        )

    @task_retry.connect(weak=False)
    def _on_task_retry(sender=None, request=None, reason=None, einfo=None, **kwargs) -> None:
        _report_execution(
            status="retry",
            task_id=getattr(request, "id", None),
            task_name=getattr(sender, "name", None),
            queue=getattr(sender, "queue", None),
            worker_hostname=getattr(request, "hostname", None),
            retries=getattr(request, "retries", None),
            max_retries=getattr(sender, "max_retries", None),
            exception_type=type(reason).__name__ if reason is not None else "",
            exception_message=str(reason) if reason is not None else "",
            traceback=str(einfo) if einfo is not None else "",
        )

    @task_revoked.connect(weak=False)
    def _on_task_revoked(sender=None, request=None, terminated=None, signum=None, expired=None, **kwargs) -> None:
        if expired:
            message = "Task expired before it could run"
        elif terminated:
            message = f"Task terminated mid-execution (signal {signum})"
        else:
            message = "Task revoked before it started running"

        _report_execution(
            status="revoked",
            task_id=getattr(request, "id", None),
            task_name=getattr(sender, "name", None),
            queue=getattr(sender, "queue", None),
            worker_hostname=getattr(request, "hostname", None),
            retries=getattr(request, "retries", None),
            max_retries=getattr(sender, "max_retries", None),
            exception_type="TaskRevoked",
            exception_message=message,
            traceback="",
        )


def _report_task_registry(app: "Celery") -> None:
    config = _get_config_or_warn()
    if config is None:
        return

    tasks = _collect_tasks(app)
    threading.Thread(
        target=_send_registry, args=(config, tasks), daemon=True, name="watchdock-celery-registry"
    ).start()


def _report_execution(
    status: str,
    task_id: str | None,
    task_name: str | None,
    queue: str | None,
    worker_hostname: str | None,
    retries: int | None,
    max_retries: int | None,
    exception_type: str,
    exception_message: str,
    traceback: str,
) -> None:
    config = _get_config_or_warn()
    if config is None:
        return

    event = {
        "task_id": task_id or "",
        "task_name": task_name or "unknown",
        "status": status,
        "queue": queue or "",
        "worker_hostname": worker_hostname or "",
        "retries": retries,
        "max_retries": max_retries,
        "exception_type": exception_type,
        "exception_message": exception_message,
        "traceback": traceback,
    }
    threading.Thread(
        target=_send_execution, args=(config, event), daemon=True, name="watchdock-celery-execution"
    ).start()


def _report_heartbeat(task_name: str) -> None:
    config = _get_config_or_warn()
    if config is None:
        return
    threading.Thread(
        target=_send_heartbeat, args=(config, task_name), daemon=True, name="watchdock-celery-heartbeat"
    ).start()


def _get_config_or_warn():
    import watchdock_errors

    config = watchdock_errors.get_config()
    if config is None:
        logger.warning("watchdock_errors: celery integration fired before init() — skipping report")
    return config


def _periodic_schedules_by_task_name(app: "Celery") -> dict:
    beat_schedule = app.conf.beat_schedule or {}
    schedules_by_task_name = {}
    for entry in beat_schedule.values():
        task_name = entry.get("task") if isinstance(entry, dict) else getattr(entry, "task", None)
        if task_name:
            schedules_by_task_name[task_name] = _serialize_schedule(entry)
    return schedules_by_task_name


def _collect_tasks(app: "Celery") -> list[dict]:
    schedules_by_task_name = _periodic_schedules_by_task_name(app)

    tasks = []
    for name, task in app.tasks.items():
        if name.startswith("celery."):
            continue
        tasks.append(
            {
                "name": name,
                "module": getattr(task, "__module__", "") or "",
                "queue": getattr(task, "queue", "") or "",
                "max_retries": getattr(task, "max_retries", None),
                "is_periodic": name in schedules_by_task_name,
                "schedule": schedules_by_task_name.get(name),
            }
        )
    return tasks


def _serialize_schedule(entry) -> dict | None:
    schedule = entry.get("schedule") if isinstance(entry, dict) else getattr(entry, "schedule", None)
    if schedule is None:
        return None

    if hasattr(schedule, "_orig_minute"):  # celery.schedules.crontab
        return {
            "type": "crontab",
            "minute": schedule._orig_minute,
            "hour": schedule._orig_hour,
            "day_of_week": schedule._orig_day_of_week,
            "day_of_month": schedule._orig_day_of_month,
            "month_of_year": schedule._orig_month_of_year,
        }

    seconds = getattr(schedule, "seconds", schedule)  # celery.schedules.schedule or plain number
    try:
        return {"type": "interval", "every_seconds": float(seconds)}
    except (TypeError, ValueError):
        return {"type": "unknown"}


def _send_registry(config, tasks: list[dict]) -> None:
    if not tasks:
        return
    _post(config, "/api/v1/celery/registry/", {"environment": config.environment, "tasks": tasks}, "task", len(tasks))


def _send_execution(config, event: dict) -> None:
    payload = {**event, "environment": config.environment}
    _post(config, "/api/v1/celery/executions/", payload, "execution", 1)


def _send_heartbeat(config, task_name: str) -> None:
    payload = {"task_name": task_name, "environment": config.environment}
    _post(config, "/api/v1/celery/heartbeat/", payload, "heartbeat", 1)


def _post(config, path: str, payload: dict, noun: str, count: int) -> None:
    url = f"{config.endpoint.rstrip('/')}{path}"
    try:
        response = requests.post(
            url,
            json=payload,
            headers={
                "Authorization": f"Bearer {config.api_key}",
                "Content-Type": "application/json",
                "User-Agent": f"watchdock-errors/{config.sdk_version}",
            },
            timeout=config.timeout * 3,
        )
        if response.status_code in (200, 201, 202):
            logger.info("watchdock_errors: reported %d celery %s(s) to %s", count, noun, path)
        else:
            logger.warning(
                "watchdock_errors: celery %s rejected — status=%s body=%s", noun, response.status_code, response.text[:500]
            )
    except requests.exceptions.ConnectionError as e:
        logger.error("watchdock_errors: connection failed reporting celery %s — %s", noun, e)
    except requests.exceptions.Timeout:
        logger.error("watchdock_errors: timed out reporting celery %s after %ss", noun, config.timeout * 3)
    except Exception:
        logger.error("watchdock_errors: unexpected error reporting celery %s", noun, exc_info=True)
