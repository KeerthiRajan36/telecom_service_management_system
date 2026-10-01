import re
from datetime import datetime, timezone, timedelta

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from datetime import datetime

from app.db.types import UTCDateTime
from app.main import _parse_rate_limit
from app.middleware.rate_limit import RateLimitMiddleware
from app.services.usage_service import _percent
from app.utils import codes


@pytest.mark.parametrize("used,limit,expected", [
    (0, 1000, 0.0), (250, 1000, 25.0), (1000, 1000, 100.0), (1500, 1000, 150.0), (10, 3, 333.33),
])
def test_usage_percent(used, limit, expected):
    assert _percent(used, limit) == expected


@pytest.mark.parametrize("limit", [None, 0])
def test_usage_percent_unlimited_or_zero_limit_is_none(limit):
    assert _percent(500, limit) is None


def test_usage_percent_is_capped_to_avoid_absurd_values():
    assert _percent(10**9, 1) == 99990.0  # ratio is clamped at 999.9x


@pytest.mark.parametrize("value,expected", [
    ("100/minute", (100, 60)), ("5/second", (5, 1)), ("10/hour", (10, 3600)), ("7/weird", (7, 60)),
])
def test_parse_rate_limit(value, expected):
    assert _parse_rate_limit(value) == expected


def test_code_generators_have_expected_prefixes():
    assert re.fullmatch(r"CUST-[A-Z0-9]{8}", codes.gen_customer_code())
    assert re.fullmatch(r"TCK-[A-Z0-9]{8}", codes.gen_ticket_code())
    assert re.fullmatch(r"SRQ-[A-Z0-9]{8}", codes.gen_request_code())
    assert codes.gen_ticket_code() != codes.gen_ticket_code()


def test_utc_datetime_type_normalises_naive_and_offset_values():
    t = UTCDateTime()
    naive = datetime(2026, 1, 1, 12, 0)
    ist = datetime(2026, 1, 1, 17, 30, tzinfo=timezone(timedelta(hours=5, minutes=30)))

    assert t.process_bind_param(naive, None).tzinfo == timezone.utc
    assert t.process_bind_param(ist, None) == datetime(2026, 1, 1, 12, 0, tzinfo=timezone.utc)
    loaded = t.process_result_value(naive, None)
    assert loaded.tzinfo is not None and loaded == naive.replace(tzinfo=timezone.utc)
    assert t.process_bind_param(None, None) is None and t.process_result_value(None, None) is None


def _limited_app(max_requests: int) -> TestClient:
    app = FastAPI()
    app.add_middleware(RateLimitMiddleware, max_requests=max_requests, window_seconds=60)

    @app.get("/ping")
    def ping():
        return {"ok": True}

    @app.get("/health")
    def health():
        return {"ok": True}

    return TestClient(app)


def test_rate_limiter_blocks_after_threshold_with_429_envelope():
    client = _limited_app(3)
    assert [client.get("/ping").status_code for _ in range(3)] == [200, 200, 200]
    blocked = client.get("/ping")
    assert blocked.status_code == 429
    assert blocked.json()["error"]["code"] == "RATE_LIMITED"


def test_rate_limiter_never_blocks_health_endpoint():
    client = _limited_app(1)
    client.get("/ping")
    assert all(client.get("/health").status_code == 200 for _ in range(5))


def test_utc_datetime_type_normalises_tz_aware_values_on_read():
    from datetime import timezone, timedelta
    ist = datetime(2026, 1, 1, 17, 30, tzinfo=timezone(timedelta(hours=5, minutes=30)))
    assert UTCDateTime().process_result_value(ist, None) == datetime(2026, 1, 1, 12, 0, tzinfo=timezone.utc)


def test_audit_json_serialization_falls_back_to_str_for_unserializable_values():
    """json.dumps(..., default=str) handles almost any *value* via str(), but dict *keys* skip
    `default` entirely: a non-primitive key still raises TypeError, which is the one real way
    to hit the except-branch fallback."""
    from app.utils.audit_logger import _safe_json

    class WeirdKey:
        def __str__(self):
            return "weird"

    assert _safe_json({"a": 1}) == '{"a": 1}'
    assert _safe_json(None) is None
    bad = {WeirdKey(): "value"}
    assert _safe_json(bad) == str(bad)
