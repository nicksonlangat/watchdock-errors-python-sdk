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
    assert event["level"] == "info"


def test_build_event_level_override(config):
    event = build_event(None, config, message="disk almost full", level="warning")

    assert event is not None
    assert event["level"] == "warning"


def test_build_event_exception_default_level(config):
    try:
        raise ValueError("bad")
    except ValueError as exc:
        event = build_event(exc, config)

    assert event is not None
    assert event["level"] == "error"


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


def test_trace_id_extracted_from_x_request_id_header(config):
    req_ctx = {
        "request": {
            "method": "GET",
            "url": "/checkout/",
            "headers": {"X-Request-Id": "abc123"},
        }
    }

    try:
        raise ValueError("x")
    except ValueError as exc:
        event = build_event(exc, config, request_context=req_ctx)

    assert event["trace_id"] == "abc123"


def test_trace_id_falls_back_to_traceparent_header(config):
    req_ctx = {
        "request": {
            "headers": {"traceparent": "00-4bf92f3577b34da6a3ce929d0e0e4736-00f067aa0ba902b7-01"},
        }
    }

    event = build_event(None, config, message="hi", request_context=req_ctx)

    assert event["trace_id"] == "4bf92f3577b34da6a3ce929d0e0e4736"


def test_trace_id_absent_when_no_matching_header(config):
    req_ctx = {"request": {"headers": {"Content-Type": "application/json"}}}

    event = build_event(None, config, message="hi", request_context=req_ctx)

    assert "trace_id" not in event


def test_explicit_trace_id_wins_over_header_extraction(config):
    req_ctx = {"request": {"headers": {"X-Request-Id": "from-header"}}}

    event = build_event(None, config, message="hi", request_context=req_ctx, trace_id="explicit-id")

    assert event["trace_id"] == "explicit-id"


def test_explicit_trace_id_works_without_request_context(config):
    event = build_event(None, config, message="hi", trace_id="explicit-id")

    assert event["trace_id"] == "explicit-id"
