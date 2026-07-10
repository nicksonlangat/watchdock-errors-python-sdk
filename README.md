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
