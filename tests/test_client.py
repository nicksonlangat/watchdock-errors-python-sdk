import time

import pytest
import responses as rsps_lib

from watchdock_errors.client import WatchdockClient
from watchdock_errors.config import SDKConfig


@pytest.fixture()
def config():
    return SDKConfig(api_key="wdk_test", endpoint="https://api.watchdock.cc", timeout=1.0)


@rsps_lib.activate
def test_client_sends_event(config):
    rsps_lib.add(rsps_lib.POST, config.ingest_url, status=202)

    client = WatchdockClient(config)
    client.capture({"exception": {"type": "ValueError", "message": "test"}})
    client.flush()
    client.close()

    assert len(rsps_lib.calls) == 1
    assert rsps_lib.calls[0].request.headers["Authorization"] == "Bearer wdk_test"


@rsps_lib.activate
def test_client_does_not_raise_on_network_error(config):
    rsps_lib.add(rsps_lib.POST, config.ingest_url, body=ConnectionError("timeout"))

    client = WatchdockClient(config)
    client.capture({"exception": {"type": "ValueError", "message": "test"}})
    client.flush()
    client.close()
    # No exception raised — SDK is silent on transport failures


def test_client_drops_events_when_queue_full(config):
    client = WatchdockClient(config)
    # Fill the queue beyond maxsize
    for _ in range(200):
        client.capture({"exception": {"type": "X"}})
    # Should not raise
    client.close()
