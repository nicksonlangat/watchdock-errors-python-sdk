from datetime import timedelta
from types import SimpleNamespace

from watchdock_errors.integrations.celery import _serialize_schedule


def test_number_is_an_interval():
    assert _serialize_schedule({"schedule": 300}) == {"type": "interval", "every_seconds": 300.0}


def test_timedelta_uses_total_seconds():
    assert _serialize_schedule({"schedule": timedelta(minutes=5)})["every_seconds"] == 300.0
    assert _serialize_schedule({"schedule": timedelta(days=1)})["every_seconds"] == 86400.0
    assert _serialize_schedule({"schedule": timedelta(days=1, hours=2)})["every_seconds"] == 93600.0


def test_celery_schedule_object_uses_its_seconds():
    assert _serialize_schedule({"schedule": SimpleNamespace(seconds=86400.0)})["every_seconds"] == 86400.0


def test_crontab_is_not_an_interval():
    cron = SimpleNamespace(_orig_minute="0", _orig_hour="3", _orig_day_of_week="*", _orig_day_of_month="*", _orig_month_of_year="*")
    assert _serialize_schedule({"schedule": cron})["type"] == "crontab"


def test_missing_schedule():
    assert _serialize_schedule({}) is None
