import pytest
from sqlalchemy import inspect
from sqlalchemy.exc import IntegrityError

from app.db.session import engine
from tests.factories import API, error_code, make_customer, make_plan, make_sim, make_subscription, uniq


# ----------------------------------------------------------- error envelope + validation
def test_every_error_class_uses_the_same_envelope(client, admin_headers):
    client.post(f"{API}/sims", headers=admin_headers, json={"sim_number": "dup"})
    cases = {
        401: client.get(f"{API}/customers"),
        404: client.get(f"{API}/customers/nope", headers=admin_headers),
        422: client.post(f"{API}/plans", headers=admin_headers, json={}),
        409: client.post(f"{API}/sims", headers=admin_headers, json={"sim_number": "dup"}),  # duplicate of the one above
    }
    for status, resp in cases.items():
        assert resp.status_code == status
        err = resp.json()["error"]
        assert set(err) == {"code", "message", "details"} and err["message"]
    assert client.get(f"{API}/nothing-here").status_code == 404


def test_validation_details_name_the_offending_fields(client, admin_headers):
    r = client.post(f"{API}/plans", headers=admin_headers, json={"name": "x", "code": "c", "plan_type": "nope", "category": "data", "price": -1, "validity_days": 1})
    assert r.status_code == 422
    fields = {tuple(d["loc"])[-1] for d in r.json()["error"]["details"]}
    assert {"plan_type", "price"} <= fields


def test_malformed_and_wrongly_typed_bodies_are_422_not_500(client, admin_headers):
    r = client.post(f"{API}/customers", headers={**admin_headers, "Content-Type": "application/json"}, content="{not json")
    assert r.status_code == 422
    r = client.post(f"{API}/plans", headers=admin_headers, json={"name": ["a"], "code": 1, "plan_type": {}, "category": None, "price": "abc", "validity_days": "x"})
    assert r.status_code == 422
    assert client.post(f"{API}/auth/login", data={}).status_code == 422


@pytest.mark.parametrize("params", [
    {"page": 0}, {"page": -1}, {"page_size": 0}, {"page_size": 101}, {"sort_order": "sideways"}, {"page": "abc"},
])
def test_pagination_parameters_are_bounded(client, admin_headers, params):
    assert client.get(f"{API}/customers", headers=admin_headers, params=params).status_code == 422


def test_sorting_by_unknown_column_is_ignored_safely(client, admin_headers):
    make_customer(client, admin_headers)
    r = client.get(f"{API}/customers", headers=admin_headers, params={"sort_by": "hashed_password; DROP TABLE customers"})
    assert r.status_code == 200 and r.json()["total"] == 1


def test_sql_injection_attempts_are_inert(client, admin_headers):
    make_customer(client, admin_headers, full_name="Robert Tables")
    for payload in ("'; DROP TABLE customers; --", "' OR '1'='1", "%' OR 1=1 --"):
        r = client.get(f"{API}/customers", headers=admin_headers, params={"search": payload})
        assert r.status_code == 200 and r.json()["total"] == 0
    assert client.get(f"{API}/customers", headers=admin_headers).json()["total"] == 1
    r = client.post(f"{API}/auth/login", data={"username": "admin@example.com' OR '1'='1", "password": "x"})
    assert r.status_code in (401, 422)


def test_unhandled_exceptions_return_generic_500_without_leaking_details():
    """Uses a throwaway FastAPI app with the real exception handlers wired in, rather than
    mutating the shared `app.main.app` singleton (which would leak an untagged, unsummarized
    debug route into every other test's OpenAPI schema for the rest of the process)."""
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    from app.core.exceptions import register_exception_handlers

    probe_app = FastAPI()
    register_exception_handlers(probe_app)

    @probe_app.get("/__boom")
    def boom():
        raise RuntimeError("secret internal detail: db password is hunter2")

    with TestClient(probe_app, raise_server_exceptions=False) as c:
        r = c.get("/__boom")
    assert r.status_code == 500
    assert error_code(r) == "INTERNAL_ERROR" and "hunter2" not in r.text and "Traceback" not in r.text


def test_generic_sqlalchemy_errors_are_caught_with_a_clean_500():
    """Distinct from IntegrityError (409): any other SQLAlchemyError must still be a safe,
    generic 500 rather than a leaked traceback."""
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from sqlalchemy.exc import OperationalError

    from app.core.exceptions import register_exception_handlers

    probe_app = FastAPI()
    register_exception_handlers(probe_app)

    @probe_app.get("/__db_down")
    def db_down():
        raise OperationalError("SELECT 1", {}, Exception("connection to server was lost"))

    with TestClient(probe_app, raise_server_exceptions=False) as c:
        r = c.get("/__db_down")
    assert r.status_code == 500 and error_code(r) == "DATABASE_ERROR"
    assert "connection to server" not in r.text


def test_health_reports_degraded_when_the_database_is_unreachable(client, monkeypatch):
    import app.main as main_module

    class ExplodingSession:
        def __enter__(self):
            raise Exception("simulated connection failure")

        def __exit__(self, *a):
            return False

    monkeypatch.setattr(main_module, "SessionLocal", lambda: ExplodingSession())
    r = client.get("/health")
    assert r.status_code == 200 and r.json() == {"status": "degraded", "database": "down"}


def test_health_and_openapi_are_public(client):
    h = client.get("/health").json()
    assert h == {"status": "ok", "database": "up"}
    spec = client.get("/openapi.json").json()
    assert len(spec["paths"]) >= 90
    tags = {t for p in spec["paths"].values() for op in p.values() for t in op.get("tags", [])}
    assert {"Authentication", "Customers", "Service Plans", "SIM Cards", "Devices", "Subscriptions", "Usage Tracking",
            "Network Towers", "Network Equipment", "Network Outages", "Field Technicians", "Support Tickets",
            "SLA Management", "Service Requests", "Notifications", "Operations Dashboard", "Advanced Reports",
            "Audit Logs"} <= tags
    assert client.get("/docs").status_code == 200


def test_error_on_write_does_not_poison_later_requests(client, admin_headers):
    c = make_customer(client, admin_headers)
    other = make_customer(client, admin_headers)
    assert client.patch(f"{API}/customers/{c['id']}", headers=admin_headers, json={"email": other["email"]}).status_code == 409
    assert client.get(f"{API}/customers/{c['id']}", headers=admin_headers).status_code == 200   # fresh session, clean state


# ------------------------------------------------------------------ database layer
def _idx_cols(table):
    insp = inspect(engine)
    cols = set()
    for ix in insp.get_indexes(table):
        cols.update(ix["column_names"])
    for uc in insp.get_unique_constraints(table):
        cols.update(uc["column_names"])
    pk = insp.get_pk_constraint(table)["constrained_columns"]
    return cols | set(pk)


@pytest.mark.parametrize("table,columns", [
    ("users", {"email"}), ("customers", {"email", "phone", "customer_code"}),
    ("sim_cards", {"sim_number", "status", "customer_id", "serving_tower_id"}),
    ("devices", {"imei", "customer_id"}), ("subscriptions", {"customer_id", "sim_id", "plan_id", "status"}),
    ("usage_records", {"subscription_id", "sim_id", "usage_date"}),
    ("tickets", {"ticket_code", "customer_id", "status", "priority"}),
    ("sla_tracking", {"ticket_id", "breached"}), ("outages", {"status", "severity"}),
    ("technician_assignments", {"technician_id", "target_id", "status"}),
    ("audit_logs", {"user_id", "action", "entity", "entity_id"}),
    ("notifications", {"recipient_customer_id", "recipient_user_id", "notification_type", "is_read"}),
    ("refresh_tokens", {"jti", "user_id"}),
])
def test_hot_query_columns_are_indexed(client, table, columns):
    assert columns <= _idx_cols(table), f"{table} is missing indexes on {columns - _idx_cols(table)}"


def test_database_enforces_uniqueness_independently_of_the_api(client, db):
    from app.models.sim import SimCard
    from app.models.device import Device
    db.add(SimCard(sim_number="UNIQ-1")); db.commit()
    db.add(SimCard(sim_number="UNIQ-1"))
    with pytest.raises(IntegrityError):
        db.commit()
    db.rollback()

    s = SimCard(sim_number="UNIQ-2"); db.add(s); db.commit()
    db.add(Device(imei="111111111111111", model="a", manufacturer="b", sim_id=s.id)); db.commit()
    db.add(Device(imei="222222222222222", model="a", manufacturer="b", sim_id=s.id))
    with pytest.raises(IntegrityError):
        db.commit()                       # a SIM can be mapped to at most one device, even if the service layer is bypassed
    db.rollback()


def test_usage_has_one_row_per_subscription_per_day(client, admin_headers, db):
    from datetime import date
    from app.models.usage import UsageRecord
    cust = make_customer(client, admin_headers)
    sim = make_sim(client, admin_headers, cust["id"])
    sub = make_subscription(client, admin_headers, cust["id"], sim["id"], make_plan(client, admin_headers)["id"])
    db.add(UsageRecord(subscription_id=sub["id"], sim_id=sim["id"], usage_date=date(2026, 1, 1))); db.commit()
    db.add(UsageRecord(subscription_id=sub["id"], sim_id=sim["id"], usage_date=date(2026, 1, 1)))
    with pytest.raises(IntegrityError):
        db.commit()
    db.rollback()


def test_datetimes_always_come_back_timezone_aware_utc(client, admin_headers, db):
    from datetime import timezone
    from app.models.subscription import Subscription
    from app.models.sim import SimCard
    cust = make_customer(client, admin_headers)
    sim = make_sim(client, admin_headers, cust["id"])
    sub = make_subscription(client, admin_headers, cust["id"], sim["id"], make_plan(client, admin_headers)["id"])
    row = db.get(Subscription, sub["id"])
    assert row.start_date.tzinfo is not None and row.end_date.utcoffset().total_seconds() == 0
    assert row.created_at.tzinfo is not None and db.get(SimCard, sim["id"]).activation_date.tzinfo == timezone.utc


def test_audit_records_carry_user_entity_and_before_after_values(client, admin_headers):
    plan = make_plan(client, admin_headers, price=100)
    client.patch(f"{API}/plans/{plan['id']}", headers=admin_headers, json={"price": 250})
    logs = client.get(f"{API}/audit-logs", headers=admin_headers, params={"entity": "ServicePlan", "entity_id": plan["id"], "action": "UPDATE"}).json()
    rec = logs["items"][0]
    assert rec["user_id"] and rec["entity"] == "ServicePlan" and rec["entity_id"] == plan["id"] and rec["created_at"]
    assert '"price": 100' in rec["previous_value"] and '"price": 250' in rec["new_value"]


def test_audit_log_filters_and_default_newest_first(client, admin_headers, staff):
    me = client.get(f"{API}/auth/me", headers=admin_headers).json()
    make_plan(client, admin_headers); make_customer(client, admin_headers)
    by_user = client.get(f"{API}/audit-logs", headers=admin_headers, params={"user_id": me["id"], "entity": "Customer"}).json()
    assert by_user["total"] == 1 and by_user["items"][0]["action"] == "CREATE"
    everything = client.get(f"{API}/audit-logs", headers=admin_headers, params={"page_size": 100}).json()["items"]
    stamps = [r["created_at"] for r in everything]
    assert stamps == sorted(stamps, reverse=True)


def test_dashboard_reports_live_counts(client, admin_headers):
    from tests.factories import make_tower, make_outage
    cust = make_customer(client, admin_headers)
    plan = make_plan(client, admin_headers)
    sim = make_sim(client, admin_headers, cust["id"])
    make_subscription(client, admin_headers, cust["id"], sim["id"], plan["id"])
    tower = make_tower(client, admin_headers)
    other = make_customer(client, admin_headers)
    client.patch(f"{API}/customers/{other['id']}/activation", headers=admin_headers, json={"is_active": False})
    before = client.get(f"{API}/dashboard/operations", headers=admin_headers).json()
    assert (before["total_customers"], before["active_customers"]) == (2, 1)
    assert (before["active_subscriptions"], before["active_sims"], before["towers_active"], before["towers_offline"]) == (1, 1, 1, 0)
    make_outage(client, admin_headers, [tower["id"]])
    after = client.get(f"{API}/dashboard/operations", headers=admin_headers).json()
    assert (after["open_network_outages"], after["towers_active"], after["towers_offline"]) == (1, 0, 1)
    client.post(f"{API}/service-requests", headers=admin_headers, json={"customer_id": cust["id"], "request_type": "plan_change"})
    assert client.get(f"{API}/dashboard/operations", headers=admin_headers).json()["pending_service_requests"] == 1


def test_report_endpoints_with_data_and_filters(client, admin_headers):
    from datetime import date
    cust = make_customer(client, admin_headers)
    p1, p2 = make_plan(client, admin_headers, name="Popular"), make_plan(client, admin_headers, name="Niche")
    for plan in (p1, p1, p2):
        c = make_customer(client, admin_headers)
        s = make_subscription(client, admin_headers, c["id"], make_sim(client, admin_headers, c["id"])["id"], plan["id"])
        client.post(f"{API}/usage", headers=admin_headers, json={"subscription_id": s["id"], "usage_date": date.today().isoformat(), "data_used_mb": 100})
    pop = client.get(f"{API}/reports/plan-popularity", headers=admin_headers).json()
    assert [(p["plan_name"], p["subscriber_count"]) for p in pop] == [("Popular", 2), ("Niche", 1)]
    only = client.get(f"{API}/reports/plan-popularity", headers=admin_headers, params={"plan_id": p2["id"]}).json()
    assert len(only) == 1 and only[0]["plan_name"] == "Niche"
    total = client.get(f"{API}/reports/data-consumption", headers=admin_headers).json()
    assert total[0]["total_data_used_mb"] == 300
    by_plan = client.get(f"{API}/reports/data-consumption", headers=admin_headers, params={"plan_id": p1["id"]}).json()
    assert by_plan[0]["total_data_used_mb"] == 200
    growth = client.get(f"{API}/reports/customer-growth", headers=admin_headers).json()
    assert growth[0]["new_customers"] == 4
    trends = client.get(f"{API}/reports/subscription-trends", headers=admin_headers).json()
    assert trends[0]["created"] == 3
