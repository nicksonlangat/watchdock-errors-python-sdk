# watchdock-errors

Python SDK for application-level error tracking on the [Watchdock](https://watchdock.cc) platform.

## Installation

```bash
pip install watchdock-errors
```

With framework extras:

```bash
pip install "watchdock-errors[django]"
pip install "watchdock-errors[fastapi]"
pip install "watchdock-errors[celery]"
```

## Quickstart

```python
import watchdock_errors

watchdock_errors.init(
    api_key="wdk_xxx",
    environment="production",
    release="1.0.0",
)
```

### Django

```python
# settings.py
MIDDLEWARE = [
    ...
    "watchdock_errors.integrations.django.DjangoErrorMiddleware",
]
```

Or via `INSTALLED_APPS` for automatic registration:

```python
INSTALLED_APPS = [
    ...
    "watchdock_errors.integrations.django",
]
```

### FastAPI

```python
from watchdock_errors.integrations.fastapi import setup_watchdock

setup_watchdock(app)
```

### Celery

```python
from celery import Celery
from watchdock_errors.integrations.celery import register

app = Celery("myproject")
app.config_from_object("django.conf:settings", namespace="CELERY")
app.autodiscover_tasks()

register(app)
```

Call `register(app)` once, after `autodiscover_tasks()`. It reports, automatically:

- **Task registry** — every registered task (and, for periodic tasks, their beat schedule), once per worker on startup.
- **Failures, retries, and revocations** — via `task_failure`, `task_retry`, and `task_revoked`. Successful runs are not reported.
- **Heartbeats for periodic tasks** — a lightweight ping on every run of a beat-scheduled task, so Watchdock can flag one that's gone silent. Non-periodic tasks are never pinged.

`watchdock_errors.init()` must be called before these signals fire — if you're on Django, a `worker_process_init` handler that calls `init()` covers every forked worker process.

## Manual capture

```python
# Capture the current exception
try:
    process_payment()
except Exception:
    watchdock_errors.capture_exception()

# Capture a specific exception
watchdock_errors.capture_exception(exc)

# Capture a message
watchdock_errors.capture_message("Stripe webhook signature invalid")

# Capture a message with a custom level
watchdock_errors.capture_message("Queue depth high", level="warning")
```

### Event levels

Every event carries a `level`. Exceptions default to `"error"`; messages default to `"info"` unless you pass `level` explicitly to `capture_message`.

## Correlating with nginx requests

If your app is behind nginx and you've added `$request_id` to your access log format (see the [nginx log collection docs](https://watchdock.cc/docs/nginx-log-collection)) and forwarded it to your app via `proxy_set_header X-Request-Id $request_id;`, this SDK automatically reads that header off every captured request and attaches it as `trace_id` — no code changes needed. This lets WatchDock link a failed request in your nginx access logs directly to the exception it produced.

You can also pass `trace_id` explicitly, which takes priority over the auto-extracted value:

```python
watchdock_errors.capture_exception(exc, trace_id=my_trace_id)
watchdock_errors.capture_message("Queue depth high", level="warning", trace_id=my_trace_id)
```

## SDK initialization

When `init()` is called, the SDK sends a one-time, fire-and-forget ping to the platform (with the SDK version and environment) to register that it started up. This never blocks application startup and any failure is silently ignored.

## PII scrubbing

By default, `Authorization`, `Cookie`, and `X-Api-Key` headers are stripped and the request body is not sent. Set `send_pii=True` to disable scrubbing.

Use the `before_send` hook for custom scrubbing:

```python
def scrub(event):
    event["request"]["headers"].pop("X-Internal-Token", None)
    return event  # return None to drop the event entirely

watchdock_errors.init(api_key="wdk_xxx", before_send=scrub)
```
