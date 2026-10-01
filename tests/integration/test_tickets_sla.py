from datetime import datetime, timedelta, timezone

import pytest

from tests.factories import API, error_code, make_customer, make_plan, make_sim, make_subscription, make_technician, make_ticket, uniq


@pytest.fixture()
def cust(client, admin_headers):
    return make_customer(client, admin_headers, customer_type="postpaid")


def _sla(client, H, ticket):
    return client.get(f"{API}/sla/tickets/{ticket['id']}", headers=H)


def _set_deadline(db, ticket_id, when):
    from app.models.sla import SLATracking
    row = db.query(SLATracking).filter_by(ticket_id=ticket_id).one()
    row.sla_deadline = when
    db.commit()


def _status(client, H, ticket, status, **kw):
    return client.patch(f"{API}/tickets/{ticket['id']}/status", headers=H, json={"status": status, **kw})


# ------------------------------------------------------------------- creation + SLA
def test_ticket_creation_defaults_and_history(client, admin_headers, cust):
    t = make_ticket(client, admin_headers, cust["id"], priority="medium")
    assert t["ticket_code"].startswith("TCK-") and t["status"] == "open" and t["escalated"] is False
    hist = client.get(f"{API}/tickets/{t['id']}/history", headers=admin_headers).json()
    assert [h["action"] for h in hist] == ["created"]


@pytest.mark.parametrize("ctype,expected_minutes", [("postpaid", 480), ("enterprise", 240), ("prepaid", 720)])
def test_sla_deadline_depends_on_customer_type(client, admin_headers, ctype, expected_minutes):
    c = make_customer(client, admin_headers, customer_type=ctype)
    t = make_ticket(client, admin_headers, c["id"], category="network_issue", priority="high")   # high = 8h base
    sla = _sla(client, admin_headers, t).json()
    delta = datetime.fromisoformat(sla["sla_deadline"]) - datetime.fromisoformat(sla["sla_start_time"])
    assert delta == timedelta(minutes=expected_minutes)


@pytest.mark.parametrize("priority,minutes", [("critical", 240), ("high", 480), ("medium", 1440), ("low", 4320)])
def test_sla_deadline_depends_on_priority(client, admin_headers, cust, priority, minutes):
    sla = _sla(client, admin_headers, make_ticket(client, admin_headers, cust["id"], priority=priority)).json()
    assert datetime.fromisoformat(sla["sla_deadline"]) - datetime.fromisoformat(sla["sla_start_time"]) == timedelta(minutes=minutes)


def test_ticket_without_matching_sla_rule_still_works(client, admin_headers, cust, db):
    from app.models.sla import SLARule
    db.query(SLARule).delete(); db.commit()
    t = make_ticket(client, admin_headers, cust["id"])
    r = _sla(client, admin_headers, t)
    assert r.status_code == 404 and error_code(r) == "NOT_FOUND"
    assert client.post(f"{API}/tickets/{t['id']}/escalate", headers=admin_headers, json={"reason": "x"}).json()["escalated"] is True
    for s in ("in_progress", "resolved"):
        assert _status(client, admin_headers, t, s).status_code == 200


def test_sla_rules_are_unique_per_combination(client, admin_headers):
    body = {"ticket_category": "sim_issue", "priority": "low", "customer_type": "prepaid",
            "response_time_minutes": 5, "resolution_time_minutes": 10}
    r = client.post(f"{API}/sla/rules", headers=admin_headers, json=body)
    assert r.status_code == 409 and error_code(r) == "SLA_RULE_EXISTS"      # seeded matrix already covers it
    assert len(client.get(f"{API}/sla/rules", headers=admin_headers).json()) == 84


def test_only_admin_or_ops_can_define_sla_rules(client, staff):
    body = {"ticket_category": "sim_issue", "priority": "low", "customer_type": "prepaid",
            "response_time_minutes": 5, "resolution_time_minutes": 10}
    assert client.post(f"{API}/sla/rules", headers=staff("support_agent")[1], json=body).status_code == 403


# ----------------------------------------------------------------- breach detection
def test_breached_and_soon_to_breach_detection(client, admin_headers, cust, db):
    now = datetime.now(timezone.utc)
    fine, soon, late, resolved_late = (make_ticket(client, admin_headers, cust["id"]) for _ in range(4))
    _set_deadline(db, soon["id"], now + timedelta(minutes=30))
    _set_deadline(db, late["id"], now - timedelta(minutes=5))
    _set_deadline(db, resolved_late["id"], now - timedelta(minutes=5))
    _status(client, admin_headers, resolved_late, "in_progress"); _status(client, admin_headers, resolved_late, "resolved")

    ids = lambda path, **p: {x["ticket_id"] for x in client.get(f"{API}/sla/{path}", headers=admin_headers, params=p).json()}
    assert ids("breached") == {late["id"]}                                # resolved tickets are not "currently" breached
    assert ids("soon-to-breach", within_minutes=60) == {soon["id"]}
    assert ids("soon-to-breach", within_minutes=10) == set()              # window is respected
    assert fine["id"] in ids("soon-to-breach", within_minutes=100000)
    assert late["id"] not in ids("soon-to-breach", within_minutes=100000) # already past deadline => breached, not "soon"


def test_dashboard_counts_current_sla_breaches(client, admin_headers, cust, db):
    t = make_ticket(client, admin_headers, cust["id"])
    assert client.get(f"{API}/dashboard/operations", headers=admin_headers).json()["sla_breaches"] == 0
    _set_deadline(db, t["id"], datetime.now(timezone.utc) - timedelta(hours=1))
    assert client.get(f"{API}/dashboard/operations", headers=admin_headers).json()["sla_breaches"] == 1


def test_breach_endpoint_can_flag_and_notify_exactly_once(client, admin_headers, cust, db):
    t = make_ticket(client, admin_headers, cust["id"])
    _set_deadline(db, t["id"], datetime.now(timezone.utc) - timedelta(minutes=1))
    for _ in range(2):
        client.get(f"{API}/sla/breached", headers=admin_headers, params={"notify": True})
    assert _sla(client, admin_headers, t).json()["breached"] is True
    notes = client.get(f"{API}/notifications/all", headers=admin_headers, params={"customer_id": cust["id"]}).json()["items"]
    assert [n["notification_type"] for n in notes].count("sla_breach") == 1


def test_resolving_after_the_deadline_records_a_breach_and_notifies(client, admin_headers, cust, db):
    t = make_ticket(client, admin_headers, cust["id"])
    _set_deadline(db, t["id"], datetime.now(timezone.utc) - timedelta(minutes=1))
    _status(client, admin_headers, t, "in_progress")
    _status(client, admin_headers, t, "resolved", resolution_notes="fixed late")
    sla = _sla(client, admin_headers, t).json()
    assert sla["breached"] is True and sla["resolved_time"]
    assert client.get(f"{API}/sla/breached", headers=admin_headers).json() == []
    notes = client.get(f"{API}/notifications/all", headers=admin_headers, params={"customer_id": cust["id"]}).json()["items"]
    assert "sla_breach" in {n["notification_type"] for n in notes}
    perf = client.get(f"{API}/reports/sla-performance", headers=admin_headers).json()
    assert perf["breached"] == 1 and perf["compliance_percent"] == 0.0


def test_resolving_within_the_deadline_meets_sla(client, admin_headers, cust):
    t = make_ticket(client, admin_headers, cust["id"])
    _status(client, admin_headers, t, "in_progress"); _status(client, admin_headers, t, "resolved")
    assert _sla(client, admin_headers, t).json()["breached"] is False
    assert client.get(f"{API}/reports/sla-performance", headers=admin_headers).json()["compliance_percent"] == 100.0


# ------------------------------------------------------------------ status machine
def test_ticket_status_transitions(client, admin_headers, cust):
    t = make_ticket(client, admin_headers, cust["id"])
    bad = _status(client, admin_headers, t, "resolved")                     # open -> resolved skips work
    assert bad.status_code == 409 and error_code(bad) == "INVALID_TRANSITION"
    assert _status(client, admin_headers, t, "open").status_code == 409     # same state
    assert _status(client, admin_headers, t, "in_progress").status_code == 200
    assert _status(client, admin_headers, t, "waiting_for_customer").status_code == 200
    assert _status(client, admin_headers, t, "in_progress").status_code == 200
    done = _status(client, admin_headers, t, "resolved", resolution_notes="Replaced SIM").json()
    assert done["resolved_at"] and done["resolution_notes"] == "Replaced SIM"
    assert _status(client, admin_headers, t, "in_progress").status_code == 200   # reopening a resolved ticket is allowed
    _status(client, admin_headers, t, "resolved")
    closed = _status(client, admin_headers, t, "closed").json()
    assert closed["closed_at"]
    for s in ("open", "in_progress", "resolved"):
        assert _status(client, admin_headers, t, s).status_code == 409       # closed is terminal


def test_full_history_trail(client, admin_headers, staff, cust):
    agent, _ = staff("support_agent")
    t = make_ticket(client, admin_headers, cust["id"])
    client.patch(f"{API}/tickets/{t['id']}/priority", headers=admin_headers, json={"priority": "critical"})
    client.post(f"{API}/tickets/{t['id']}/assign-agent", headers=admin_headers, json={"agent_id": agent["id"]})
    client.post(f"{API}/tickets/{t['id']}/comments", headers=admin_headers, json={"body": "looking"})
    client.post(f"{API}/tickets/{t['id']}/escalate", headers=admin_headers, json={"reason": "vip"})
    hist = client.get(f"{API}/tickets/{t['id']}/history", headers=admin_headers).json()
    assert {h["action"] for h in hist} == {"created", "priority_changed", "agent_assigned", "comment_added", "escalated"}
    prio = next(h for h in hist if h["action"] == "priority_changed")
    assert (prio["from_value"], prio["to_value"]) == ("high", "critical")
    assert all(h["actor_id"] for h in hist)


# ---------------------------------------------------------------------- assignment
def test_agent_assignment_rules_and_notification(client, admin_headers, staff, cust):
    agent, agent_h = staff("support_agent")
    engineer, _ = staff("network_engineer")
    t = make_ticket(client, admin_headers, cust["id"])

    r = client.post(f"{API}/tickets/{t['id']}/assign-agent", headers=admin_headers, json={"agent_id": engineer["id"]})
    assert r.status_code == 409 and error_code(r) == "INVALID_AGENT"
    assert client.post(f"{API}/tickets/{t['id']}/assign-agent", headers=admin_headers, json={"agent_id": "nope"}).status_code == 404

    ok = client.post(f"{API}/tickets/{t['id']}/assign-agent", headers=admin_headers, json={"agent_id": agent["id"]}).json()
    assert ok["assigned_agent_id"] == agent["id"] and ok["status"] == "assigned"
    mine = client.get(f"{API}/notifications", headers=agent_h).json()
    assert [n["notification_type"] for n in mine["items"]] == ["ticket_assignment"]
    assert client.get(f"{API}/tickets", headers=agent_h, params={"assigned_agent_id": agent["id"]}).json()["total"] == 1


def test_technician_assignment_via_ticket(client, admin_headers, cust):
    tech = make_technician(client, admin_headers)
    t = make_ticket(client, admin_headers, cust["id"])
    r = client.post(f"{API}/tickets/{t['id']}/assign-technician", headers=admin_headers, json={"technician_id": tech["id"]})
    assert r.status_code == 200 and r.json()["assigned_technician_id"] == tech["id"] and r.json()["status"] == "assigned"
    assert client.post(f"{API}/tickets/nope/assign-technician", headers=admin_headers, json={"technician_id": tech["id"]}).status_code == 404


def test_field_technician_role_cannot_dispatch(client, staff, admin_headers, cust):
    t = make_ticket(client, admin_headers, cust["id"])
    _, h = staff("field_technician")
    assert client.post(f"{API}/tickets/{t['id']}/assign-agent", headers=h, json={"agent_id": "x"}).status_code == 403
    assert client.patch(f"{API}/tickets/{t['id']}/priority", headers=h, json={"priority": "low"}).status_code == 403


def test_escalation_flags_ticket_and_sla(client, admin_headers, cust):
    t = make_ticket(client, admin_headers, cust["id"])
    assert client.post(f"{API}/tickets/{t['id']}/escalate", headers=admin_headers, json={"reason": "angry"}).json()["escalated"] is True
    assert _sla(client, admin_headers, t).json()["escalated"] is True
    t2 = make_ticket(client, admin_headers, cust["id"])
    assert client.post(f"{API}/sla/tickets/{t2['id']}/escalate", headers=admin_headers).json()["escalated"] is True


# ------------------------------------------------------------- comments + listing
def test_comments_are_ordered_and_404_for_unknown_ticket(client, admin_headers, cust):
    t = make_ticket(client, admin_headers, cust["id"])
    for body in ("first", "second", "third"):
        client.post(f"{API}/tickets/{t['id']}/comments", headers=admin_headers, json={"body": body})
    assert [c["body"] for c in client.get(f"{API}/tickets/{t['id']}/comments", headers=admin_headers).json()] == ["first", "second", "third"]
    assert client.post(f"{API}/tickets/nope/comments", headers=admin_headers, json={"body": "x"}).status_code == 404


def test_ticket_list_filters_search_and_sorting(client, admin_headers, cust):
    a = make_ticket(client, admin_headers, cust["id"], subject="Roaming broken abroad", priority="low", category="voice_issue")
    b = make_ticket(client, admin_headers, cust["id"], subject="Slow data speeds", priority="critical")
    _status(client, admin_headers, b, "in_progress")
    ids = lambda **p: [t["id"] for t in client.get(f"{API}/tickets", headers=admin_headers, params=p).json()["items"]]
    assert ids(priority="critical") == [b["id"]]
    assert ids(ticket_status="in_progress") == [b["id"]]
    assert ids(search="roaming") == [a["id"]]
    assert ids(search=a["ticket_code"].lower()) == [a["id"]]
    assert ids(sort_by="priority", sort_order="asc")[0] in (a["id"], b["id"])
    assert set(ids(customer_id=cust["id"])) == {a["id"], b["id"]}


def test_resolution_time_and_service_trend_reports(client, admin_headers, cust):
    for cat in ("network_issue", "network_issue", "sim_issue"):
        t = make_ticket(client, admin_headers, cust["id"], category=cat)
        _status(client, admin_headers, t, "in_progress"); _status(client, admin_headers, t, "resolved")
    res = client.get(f"{API}/reports/ticket-resolution-time", headers=admin_headers).json()
    assert res["ticket_count"] == 3 and res["avg_resolution_hours"] >= 0
    trends = client.get(f"{API}/reports/customer-service-trends", headers=admin_headers).json()
    assert trends[0]["by_category"] == {"network_issue": 2, "sim_issue": 1}
    only = client.get(f"{API}/reports/customer-service-trends", headers=admin_headers, params={"category": "sim_issue"}).json()
    assert only[0]["by_category"] == {"sim_issue": 1}


def test_report_date_range_filtering(client, admin_headers, cust):
    make_ticket(client, admin_headers, cust["id"])
    far_future = (datetime.now(timezone.utc) + timedelta(days=400)).date().isoformat()
    past = (datetime.now(timezone.utc) - timedelta(days=400)).date().isoformat()
    assert client.get(f"{API}/reports/customer-service-trends", headers=admin_headers, params={"start": far_future}).json() == []
    assert client.get(f"{API}/reports/customer-growth", headers=admin_headers, params={"end": past}).json() == []
    assert len(client.get(f"{API}/reports/customer-service-trends", headers=admin_headers, params={"start": past}).json()) == 1


# --------------------------------------------------------------- service requests
def test_service_request_status_history(client, admin_headers, cust):
    r = client.post(f"{API}/service-requests", headers=admin_headers, json={
        "customer_id": cust["id"], "request_type": "number_change", "details": "new number please", "payload": '{"pref":"98"}'})
    assert r.status_code == 201
    req = r.json()
    assert req["request_code"].startswith("SRQ-") and req["status"] == "submitted"
    for s, note in (("in_progress", "picked up"), ("approved", "kyc ok"), ("completed", "done")):
        u = client.patch(f"{API}/service-requests/{req['id']}/status", headers=admin_headers, json={"status": s, "notes": note})
        assert u.status_code == 200 and u.json()["status"] == s
    hist = client.get(f"{API}/service-requests/{req['id']}/history", headers=admin_headers).json()
    assert [(h["from_status"], h["to_status"]) for h in hist] == [
        ("approved", "completed"), ("in_progress", "approved"), ("submitted", "in_progress"), (None, "submitted")]
    assert hist[0]["notes"] == "done"


@pytest.mark.parametrize("terminal", ["completed", "rejected"])
def test_terminal_service_requests_cannot_be_reopened(client, admin_headers, cust, terminal):
    req = client.post(f"{API}/service-requests", headers=admin_headers, json={"customer_id": cust["id"], "request_type": "plan_change"}).json()
    client.patch(f"{API}/service-requests/{req['id']}/status", headers=admin_headers, json={"status": terminal})
    r = client.patch(f"{API}/service-requests/{req['id']}/status", headers=admin_headers, json={"status": "in_progress"})
    assert r.status_code == 409 and error_code(r) == "INVALID_TRANSITION"


def test_service_request_filters_and_all_types(client, admin_headers, cust):
    types = ["sim_replacement", "number_change", "plan_change", "device_replacement",
             "service_activation", "service_suspension", "service_termination"]
    for t in types:
        assert client.post(f"{API}/service-requests", headers=admin_headers, json={"customer_id": cust["id"], "request_type": t}).status_code == 201
    listed = client.get(f"{API}/service-requests", headers=admin_headers, params={"request_type": "plan_change"}).json()
    assert listed["total"] == 1
    assert client.get(f"{API}/service-requests", headers=admin_headers).json()["total"] == 7
    assert client.post(f"{API}/service-requests", headers=admin_headers, json={"customer_id": cust["id"], "request_type": "teleport"}).status_code == 422


def test_sla_rule_creation_success_path(client, admin_headers, db):
    from app.models.sla import SLARule
    db.query(SLARule).delete(); db.commit()
    body = {"ticket_category": "device_issue", "priority": "medium", "customer_type": "prepaid",
            "response_time_minutes": 30, "resolution_time_minutes": 600}
    r = client.post(f"{API}/sla/rules", headers=admin_headers, json=body)
    assert r.status_code == 201
    created = r.json()
    assert created["response_time_minutes"] == 30 and created["resolution_time_minutes"] == 600
    assert len(client.get(f"{API}/sla/rules", headers=admin_headers).json()) == 1

    cust = make_customer(client, admin_headers, customer_type="prepaid")
    t = make_ticket(client, admin_headers, cust["id"], category="device_issue", priority="medium")
    sla = _sla(client, admin_headers, t).json()
    assert sla["sla_rule_id"] == created["id"]


def test_ticket_resolution_report_status_filter(client, admin_headers, cust):
    open_t = make_ticket(client, admin_headers, cust["id"])
    resolved_t = make_ticket(client, admin_headers, cust["id"])
    _status(client, admin_headers, resolved_t, "in_progress"); _status(client, admin_headers, resolved_t, "resolved")
    _status(client, admin_headers, resolved_t, "closed")
    only_resolved = client.get(f"{API}/reports/ticket-resolution-time", headers=admin_headers, params={"ticket_status": "resolved"}).json()
    only_closed = client.get(f"{API}/reports/ticket-resolution-time", headers=admin_headers, params={"ticket_status": "closed"}).json()
    assert only_resolved["ticket_count"] == 0 and only_closed["ticket_count"] == 1


def test_data_consumption_report_combined_customer_and_plan_filter(client, admin_headers, cust):
    from datetime import date
    plan = make_plan(client, admin_headers)
    sub = make_subscription(client, admin_headers, cust["id"], make_sim(client, admin_headers, cust["id"])["id"], plan["id"])
    client.post(f"{API}/usage", headers=admin_headers, json={"subscription_id": sub["id"], "usage_date": date.today().isoformat(), "data_used_mb": 77})
    r = client.get(f"{API}/reports/data-consumption", headers=admin_headers, params={"customer_id": cust["id"], "plan_id": plan["id"]}).json()
    assert r[0]["total_data_used_mb"] == 77
