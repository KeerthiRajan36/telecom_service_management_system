from datetime import date, datetime, timedelta, timezone

import pytest

from app.models.subscription import Subscription
from app.models.network import NetworkEquipment
from app.models.enums import SubscriptionStatus
from app.workers import jobs
from tests.factories import (
    API, make_customer, make_plan, make_sim, make_subscription, make_tower, make_customer_login, uniq,
)


def _notes(client, H, customer_id, ntype=None):
    items = client.get(f"{API}/notifications/all", headers=H, params={"customer_id": customer_id, "page_size": 100}).json()["items"]
    return [n for n in items if ntype is None or n["notification_type"] == ntype]


@pytest.fixture()
def sub(client, admin_headers):
    cust = make_customer(client, admin_headers)
    plan = make_plan(client, admin_headers, validity_days=30, data_limit_mb=1000, voice_limit_minutes=100, sms_limit_count=100)
    sim = make_sim(client, admin_headers, cust["id"])
    s = make_subscription(client, admin_headers, cust["id"], sim["id"], plan["id"])
    return {"cust": cust, "plan": plan, "sim": sim, "sub": s}


def _row(db, sub_id):
    db.expire_all()
    return db.get(Subscription, sub_id)


# ------------------------------------------------------------------ usage thresholds
def _use(client, H, sub_id, **kw):
    return client.post(f"{API}/usage", headers=H, json={
        "subscription_id": sub_id, "usage_date": date.today().isoformat(), **kw})


def test_usage_threshold_alerts_fire_once_per_level(client, admin_headers, sub):
    cid, sid = sub["cust"]["id"], sub["sub"]["id"]
    _use(client, admin_headers, sid, data_used_mb=700)
    assert _notes(client, admin_headers, cid, "usage_threshold") == []                     # 70% - nothing yet

    _use(client, admin_headers, sid, data_used_mb=150)                                     # 85%
    _use(client, admin_headers, sid, data_used_mb=10)                                      # 86% - same bucket, no repeat
    alerts = _notes(client, admin_headers, cid, "usage_threshold")
    assert len(alerts) == 1 and "80%" in alerts[0]["message"] and "data" in alerts[0]["message"]

    _use(client, admin_headers, sid, data_used_mb=200)                                     # 106%
    messages = sorted(n["message"] for n in _notes(client, admin_headers, cid, "usage_threshold"))
    assert len(messages) == 2 and any("100%" in m for m in messages)


def test_usage_threshold_covers_voice_and_sms_and_ignores_unlimited(client, admin_headers, sub):
    _use(client, admin_headers, sub["sub"]["id"], voice_used_minutes=95, sms_used_count=100)
    text = " ".join(n["message"] for n in _notes(client, admin_headers, sub["cust"]["id"], "usage_threshold"))
    assert "80% of your voice" in text and "100% of your sms" in text

    unlimited = make_plan(client, admin_headers, data_limit_mb=None, voice_limit_minutes=None, sms_limit_count=None)
    other = make_customer(client, admin_headers)
    s2 = make_subscription(client, admin_headers, other["id"], make_sim(client, admin_headers, other["id"])["id"], unlimited["id"])
    _use(client, admin_headers, s2["id"], data_used_mb=10**6)
    assert _notes(client, admin_headers, other["id"], "usage_threshold") == []


# ------------------------------------------------------------ expiry / auto-renewal
def test_job_auto_renews_opted_in_and_expires_the_rest(client, admin_headers, db, sub):
    cust2 = make_customer(client, admin_headers)
    sim2 = make_sim(client, admin_headers, cust2["id"])
    manual = make_subscription(client, admin_headers, cust2["id"], sim2["id"], sub["plan"]["id"])
    row_auto, row_manual = _row(db, sub["sub"]["id"]), _row(db, manual["id"])
    row_manual.auto_renew = False
    yesterday = datetime.now(timezone.utc) - timedelta(days=1)
    old_end = yesterday
    row_auto.end_date = row_manual.end_date = old_end
    db.commit()

    result = jobs.process_subscription_expiries(db)
    assert result == {"renewed": 1, "expired": 1}
    auto, man = _row(db, sub["sub"]["id"]), _row(db, manual["id"])
    assert auto.status == SubscriptionStatus.ACTIVE and auto.end_date == old_end + timedelta(days=30)   # continuity kept
    assert man.status == SubscriptionStatus.EXPIRED

    actions = {h["action"] for h in client.get(f"{API}/subscriptions/{sub['sub']['id']}/history", headers=admin_headers).json()}
    assert "auto_renewed" in actions
    assert jobs.process_subscription_expiries(db) == {"renewed": 0, "expired": 0}                      # idempotent


def test_auto_renew_after_long_downtime_does_not_create_an_already_expired_cycle(client, admin_headers, db, sub):
    row = _row(db, sub["sub"]["id"])
    row.end_date = datetime.now(timezone.utc) - timedelta(days=200)
    db.commit()
    jobs.process_subscription_expiries(db)
    assert _row(db, sub["sub"]["id"]).end_date > datetime.now(timezone.utc) + timedelta(days=29)


# ------------------------------------------------------------------ plan expiry alerts
def test_plan_expiry_warns_only_manual_renewers_and_only_once(client, admin_headers, db, sub):
    row = _row(db, sub["sub"]["id"])
    row.auto_renew, row.end_date = False, datetime.now(timezone.utc) + timedelta(days=2, hours=1)
    db.commit()

    auto_cust = make_customer(client, admin_headers)
    auto_sub = make_subscription(client, admin_headers, auto_cust["id"], make_sim(client, admin_headers, auto_cust["id"])["id"], sub["plan"]["id"])
    _row(db, auto_sub["id"]).end_date = datetime.now(timezone.utc) + timedelta(days=1)
    db.commit()
    far_cust = make_customer(client, admin_headers)
    far = make_subscription(client, admin_headers, far_cust["id"], make_sim(client, admin_headers, far_cust["id"])["id"], sub["plan"]["id"])
    r = _row(db, far["id"]); r.auto_renew = False; db.commit()                       # expires in 30 days

    assert jobs.scan_plan_expiries(db) == 1
    assert jobs.scan_plan_expiries(db) == 0                                          # de-duplicated
    assert len(_notes(client, admin_headers, sub["cust"]["id"], "plan_expiry")) == 1
    assert "2 day(s)" in _notes(client, admin_headers, sub["cust"]["id"], "plan_expiry")[0]["message"]
    assert _notes(client, admin_headers, auto_cust["id"], "plan_expiry") == []       # auto-renew: no action needed
    assert _notes(client, admin_headers, far_cust["id"], "plan_expiry") == []        # not due yet


# ------------------------------------------------------------------ maintenance alerts
def test_maintenance_notifications_reach_only_customers_on_that_tower(client, admin_headers, db):
    tower, other_tower = make_tower(client, admin_headers), make_tower(client, admin_headers)
    def served(t):
        c = make_customer(client, admin_headers); s = make_sim(client, admin_headers, c["id"])
        client.post(f"{API}/sims/{s['id']}/assign-tower", headers=admin_headers, json={"tower_id": t["id"]})
        client.patch(f"{API}/sims/{s['id']}/status", headers=admin_headers, json={"status": "active"})
        return c
    on, off = served(tower), served(other_tower)
    soon = (date.today() + timedelta(days=1)).isoformat()
    later = (date.today() + timedelta(days=30)).isoformat()
    mk = lambda tw, when: client.post(f"{API}/equipment", headers=admin_headers, json={
        "tower_id": tw["id"], "name": f"eq-{uniq()}", "equipment_type": "base_station", "maintenance_schedule": when})
    mk(tower, soon); mk(other_tower, later)

    assert jobs.scan_maintenance_schedules(db) == 1
    assert jobs.scan_maintenance_schedules(db) == 0                                  # idempotent
    note = _notes(client, admin_headers, on["id"], "maintenance_schedule")
    assert len(note) == 1 and tower["code"] in note[0]["message"] and soon in note[0]["message"]
    assert _notes(client, admin_headers, off["id"], "maintenance_schedule") == []


# ------------------------------------------------------------------ SLA breach job
def test_sla_job_flags_late_tickets_once(client, admin_headers, db):
    from app.models.sla import SLATracking
    from tests.factories import make_ticket
    cust = make_customer(client, admin_headers)
    t = make_ticket(client, admin_headers, cust["id"])
    db.query(SLATracking).filter_by(ticket_id=t["id"]).update({"sla_deadline": datetime.now(timezone.utc) - timedelta(minutes=1)})
    db.commit()
    assert jobs.scan_sla_breaches(db) == 1 and jobs.scan_sla_breaches(db) == 0
    assert len(_notes(client, admin_headers, cust["id"], "sla_breach")) == 1


# ------------------------------------------------------------------ ops endpoint
def test_run_jobs_endpoint_is_restricted_and_returns_counts(client, admin_headers, staff):
    r = client.post(f"{API}/ops/run-jobs", headers=admin_headers)
    assert r.status_code == 200
    assert set(r.json()) == {"subscriptions", "plan_expiry_notifications", "maintenance_notifications", "sla_breaches_flagged"}
    assert client.post(f"{API}/ops/run-jobs", headers=staff("support_agent")[1]).status_code == 403
    assert client.post(f"{API}/ops/run-jobs").status_code == 401


# ------------------------------------------------------------------ notification API
def test_notification_inbox_read_state_and_pagination(client, admin_headers, sub, staff):
    login = make_customer_login(client, admin_headers, sub["cust"])
    from app.services import notification_service as ns
    for i in range(3):
        ns.notify_plan_expiry(sub["cust"]["id"], f"P{i}", i)

    inbox = client.get(f"{API}/notifications", headers=login, params={"page_size": 2}).json()
    assert inbox["total"] == 3 and len(inbox["items"]) == 2 and inbox["pages"] == 2
    nid = inbox["items"][0]["id"]
    assert client.patch(f"{API}/notifications/{nid}/read", headers=login).json()["is_read"] is True
    assert client.get(f"{API}/notifications", headers=login, params={"unread_only": True}).json()["total"] == 2
    assert client.patch(f"{API}/notifications/does-not-exist/read", headers=login).status_code == 404
    _, agent_h = staff("support_agent")
    assert client.get(f"{API}/notifications/all", headers=login).status_code == 403     # customers can't see the global feed
    assert client.get(f"{API}/notifications", headers=agent_h).json()["total"] == 0
