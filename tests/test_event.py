import pytest
from watchdock_errors.config import SDKConfig
from watchdock_errors.event import build_event


@pytest.fixture()
def config():
    return SDKConfig(api_key="wdk_test")


def test_build_event_from_exception(config):
    try:
        raise ValueError("bad price")
    except ValueError as exc:
        event = build_event(exc, config)

    assert event is not None
    assert event["exception"]["type"] == "ValueError"
    assert event["exception"]["message"] == "bad price"
    assert isinstance(event["exception"]["stacktrace"], list)
    assert len(event["exception"]["stacktrace"]) > 0
    assert event["project_key"] == "wdk_test"
    assert "timestamp" in event
    assert event["sdk"]["name"] == "watchdock-errors"


def test_build_event_from_message(config):
    event = build_event(None, config, message="Stripe webhook failed")

    assert event is not None
    assert event["exception"]["message"] == "Stripe webhook failed"
    assert event["exception"]["type"] == "Message"


def test_before_send_can_drop_event(config):
    config.before_send = lambda e: None

    try:
        raise RuntimeError("oops")
    except RuntimeError as exc:
        event = build_event(exc, config)

    assert event is None


def test_before_send_can_mutate_event(config):
    def add_tag(event):
        event["tags"] = {"team": "backend"}
        return event

    config.before_send = add_tag

    try:
        raise RuntimeError("oops")
    except RuntimeError as exc:
        event = build_event(exc, config)

    assert event is not None
    assert event["tags"] == {"team": "backend"}


def test_pii_headers_scrubbed_by_default(config):
    req_ctx = {
        "request": {
            "method": "POST",
            "url": "/checkout/",
            "headers": {"Authorization": "Bearer secret", "Content-Type": "application/json"},
            "query_params": {},
        }
    }

    try:
        raise ValueError("x")
    except ValueError as exc:
        event = build_event(exc, config, request_context=req_ctx)

    assert "Authorization" not in event["request"]["headers"]
    assert event["request"]["headers"]["Content-Type"] == "application/json"
