from datetime import datetime, timedelta, timezone

import pytest

from tests.factories import (
    API, error_code, make_customer, make_plan, make_sim, make_subscription, make_tower, uniq,
)


def _imei():
    return f"{uniq()}{uniq()}"[:15]


# -------------------------------------------------------------------------- SIMs
def test_sim_starts_available_and_number_is_unique(client, admin_headers):
    sim = make_sim(client, admin_headers)
    assert sim["status"] == "available" and sim["activation_date"] is None
    dup = client.post(f"{API}/sims", headers=admin_headers, json={"sim_number": sim["sim_number"]})
    assert dup.status_code == 409 and error_code(dup) == "SIM_EXISTS"


def test_sim_status_state_machine(client, admin_headers):
    sim = make_sim(client, admin_headers)
    set_status = lambda s: client.patch(f"{API}/sims/{sim['id']}/status", headers=admin_headers, json={"status": s})

    assert set_status("suspended").status_code == 409                       # available -> suspended is illegal
    active = set_status("active")
    assert active.status_code == 200 and active.json()["activation_date"] is not None
    first_activation = active.json()["activation_date"]
    assert set_status("suspended").status_code == 200
    assert set_status("suspended").status_code == 409                        # already suspended
    reactivated = set_status("active")
    assert reactivated.json()["activation_date"] == first_activation         # first activation date is preserved
    assert set_status("lost").status_code == 200
    assert set_status("active").status_code == 409                           # lost can't come back
    assert set_status("blocked").status_code == 200
    assert set_status("deactivated").status_code == 200
    r = set_status("active")
    assert r.status_code == 409 and error_code(r) == "INVALID_TRANSITION"    # deactivated is terminal


def test_sim_customer_assignment_only_when_available(client, admin_headers):
    c1, c2 = make_customer(client, admin_headers), make_customer(client, admin_headers)
    sim = make_sim(client, admin_headers, c1["id"])
    client.patch(f"{API}/sims/{sim['id']}/status", headers=admin_headers, json={"status": "active"})
    r = client.post(f"{API}/sims/{sim['id']}/assign-customer", headers=admin_headers, json={"customer_id": c2["id"]})
    assert r.status_code == 409 and error_code(r) == "INVALID_SIM_STATE"
    assert client.post(f"{API}/sims/{sim['id']}/assign-customer", headers=admin_headers, json={"customer_id": "nope"}).status_code == 404


def test_sim_replacement_moves_customer_and_plan_and_keeps_history(client, admin_headers):
    cust, plan = make_customer(client, admin_headers), make_plan(client, admin_headers)
    old = make_sim(client, admin_headers, cust["id"])
    make_subscription(client, admin_headers, cust["id"], old["id"], plan["id"])

    r = client.post(f"{API}/sims/{old['id']}/replace", headers=admin_headers,
                    json={"new_sim_number": f"NEW{uniq()}", "reason": "damaged"})
    assert r.status_code == 201
    new = r.json()
    assert new["status"] == "active" and new["customer_id"] == cust["id"] and new["current_plan_id"] == plan["id"]

    old_after = client.get(f"{API}/sims/{old['id']}", headers=admin_headers).json()
    assert old_after["status"] == "deactivated" and old_after["customer_id"] is None

    history = client.get(f"{API}/sims/customers/{cust['id']}/replacements", headers=admin_headers).json()
    assert len(history) == 1 and history[0]["old_sim_id"] == old["id"] and history[0]["new_sim_id"] == new["id"]
    assert history[0]["reason"] == "damaged"


def test_sim_replacement_guards(client, admin_headers):
    unassigned = make_sim(client, admin_headers)
    r = client.post(f"{API}/sims/{unassigned['id']}/replace", headers=admin_headers, json={"new_sim_number": f"N{uniq()}"})
    assert r.status_code == 409 and error_code(r) == "SIM_NOT_ASSIGNED"
    cust = make_customer(client, admin_headers)
    taken = make_sim(client, admin_headers)
    assigned = make_sim(client, admin_headers, cust["id"])
    r = client.post(f"{API}/sims/{assigned['id']}/replace", headers=admin_headers, json={"new_sim_number": taken["sim_number"]})
    assert r.status_code == 409 and error_code(r) == "SIM_EXISTS"


def test_sim_tower_assignment_and_filters(client, admin_headers):
    tower, cust = make_tower(client, admin_headers), make_customer(client, admin_headers)
    sim = make_sim(client, admin_headers, cust["id"])
    other = make_sim(client, admin_headers)
    r = client.post(f"{API}/sims/{sim['id']}/assign-tower", headers=admin_headers, json={"tower_id": tower["id"]})
    assert r.json()["serving_tower_id"] == tower["id"]
    assert client.post(f"{API}/sims/{sim['id']}/assign-tower", headers=admin_headers, json={"tower_id": "nope"}).status_code == 404
    mine = client.get(f"{API}/sims", headers=admin_headers, params={"customer_id": cust["id"]}).json()
    assert [s["id"] for s in mine["items"]] == [sim["id"]]
    avail = client.get(f"{API}/sims", headers=admin_headers, params={"sim_status": "available"}).json()
    assert {s["id"] for s in avail["items"]} == {sim["id"], other["id"]}


def test_suspending_a_sim_notifies_the_customer(client, admin_headers):
    cust = make_customer(client, admin_headers)
    sim = make_sim(client, admin_headers, cust["id"])
    client.patch(f"{API}/sims/{sim['id']}/status", headers=admin_headers, json={"status": "active"})
    client.patch(f"{API}/sims/{sim['id']}/status", headers=admin_headers, json={"status": "suspended"})
    notes = client.get(f"{API}/notifications/all", headers=admin_headers, params={"customer_id": cust["id"]}).json()
    assert [n["notification_type"] for n in notes["items"]] == ["sim_suspension"]
    assert sim["sim_number"] in notes["items"][0]["message"]


# ----------------------------------------------------------------------- devices
def _device(client, headers, **kw):
    body = {"imei": _imei(), "model": "Pixel", "manufacturer": "Google", **kw}
    return client.post(f"{API}/devices", headers=headers, json=body)


def test_duplicate_imei_is_rejected(client, admin_headers):
    r = _device(client, admin_headers)
    assert r.status_code == 201
    dup = _device(client, admin_headers, imei=r.json()["imei"])
    assert dup.status_code == 409 and error_code(dup) == "DUPLICATE_IMEI"


def test_sim_cannot_be_mapped_to_two_devices(client, admin_headers):
    sim = make_sim(client, admin_headers)
    assert _device(client, admin_headers, sim_id=sim["id"]).status_code == 201
    r = _device(client, admin_headers, sim_id=sim["id"])
    assert r.status_code == 409 and error_code(r) == "SIM_ALREADY_MAPPED"
    free = _device(client, admin_headers).json()
    r = client.post(f"{API}/devices/{free['id']}/assign-sim", headers=admin_headers, json={"sim_id": sim["id"]})
    assert r.status_code == 409 and error_code(r) == "SIM_ALREADY_MAPPED"


@pytest.mark.parametrize("bad_status", ["blocked", "deactivated"])
def test_unusable_sims_cannot_be_assigned_to_devices(client, admin_headers, bad_status):
    sim = make_sim(client, admin_headers)
    if bad_status == "blocked":
        client.patch(f"{API}/sims/{sim['id']}/status", headers=admin_headers, json={"status": "blocked"})
    else:
        for s in ("active", "deactivated"):
            client.patch(f"{API}/sims/{sim['id']}/status", headers=admin_headers, json={"status": s})
    r = _device(client, admin_headers, sim_id=sim["id"])
    assert r.status_code == 409 and error_code(r) == "INVALID_SIM_ASSIGNMENT"


def test_device_cannot_use_a_sim_owned_by_another_customer(client, admin_headers):
    a, b = make_customer(client, admin_headers), make_customer(client, admin_headers)
    sim_b = make_sim(client, admin_headers, b["id"])
    r = _device(client, admin_headers, customer_id=a["id"], sim_id=sim_b["id"])
    assert r.status_code == 409 and error_code(r) == "INVALID_SIM_ASSIGNMENT"
    ok = _device(client, admin_headers, customer_id=b["id"], sim_id=sim_b["id"])
    assert ok.status_code == 201
    dev = _device(client, admin_headers, customer_id=a["id"]).json()
    r = client.post(f"{API}/devices/{dev['id']}/assign-sim", headers=admin_headers, json={"sim_id": sim_b["id"]})
    assert r.status_code == 409  # already mapped / wrong owner - either way rejected


def test_device_references_are_validated(client, admin_headers):
    assert _device(client, admin_headers, sim_id="nope").status_code == 404
    assert _device(client, admin_headers, customer_id="nope").status_code == 404
    assert client.get(f"{API}/devices/nope", headers=admin_headers).status_code == 404


def test_device_update_search_and_filter(client, admin_headers):
    d = _device(client, admin_headers, model="UniqueModelX").json()
    _device(client, admin_headers)
    r = client.patch(f"{API}/devices/{d['id']}", headers=admin_headers, json={"status": "blocked"})
    assert r.json()["status"] == "blocked"
    found = client.get(f"{API}/devices", headers=admin_headers, params={"search": "uniquemodelx"}).json()
    assert [x["id"] for x in found["items"]] == [d["id"]]
    blocked = client.get(f"{API}/devices", headers=admin_headers, params={"device_status": "blocked"}).json()
    assert blocked["total"] == 1


# ------------------------------------------------------------------ subscriptions
@pytest.fixture()
def setup(client, admin_headers):
    cust = make_customer(client, admin_headers)
    plan = make_plan(client, admin_headers, price=299, validity_days=28)
    sim = make_sim(client, admin_headers, cust["id"])
    return {"cust": cust, "plan": plan, "sim": sim}


def test_subscription_activates_sim_and_sets_validity_window(client, admin_headers, setup):
    sub = make_subscription(client, admin_headers, setup["cust"]["id"], setup["sim"]["id"], setup["plan"]["id"])
    assert sub["status"] == "active"
    start = datetime.fromisoformat(sub["start_date"]); end = datetime.fromisoformat(sub["end_date"])
    assert end - start == timedelta(days=28)
    sim = client.get(f"{API}/sims/{setup['sim']['id']}", headers=admin_headers).json()
    assert sim["status"] == "active" and sim["activation_date"] and sim["current_plan_id"] == setup["plan"]["id"]


def test_subscription_business_rules(client, admin_headers, setup):
    c, p, s = setup["cust"], setup["plan"], setup["sim"]
    make_subscription(client, admin_headers, c["id"], s["id"], p["id"])
    dup = client.post(f"{API}/subscriptions", headers=admin_headers, json={"customer_id": c["id"], "sim_id": s["id"], "plan_id": p["id"]})
    assert dup.status_code == 409 and error_code(dup) == "SUBSCRIPTION_EXISTS"

    other_sim = make_sim(client, admin_headers, make_customer(client, admin_headers)["id"])
    r = client.post(f"{API}/subscriptions", headers=admin_headers, json={"customer_id": c["id"], "sim_id": other_sim["id"], "plan_id": p["id"]})
    assert r.status_code == 409 and error_code(r) == "SIM_OWNERSHIP_MISMATCH"

    blocked = make_sim(client, admin_headers, c["id"])
    client.patch(f"{API}/sims/{blocked['id']}/status", headers=admin_headers, json={"status": "blocked"})
    r = client.post(f"{API}/subscriptions", headers=admin_headers, json={"customer_id": c["id"], "sim_id": blocked["id"], "plan_id": p["id"]})
    assert r.status_code == 409 and error_code(r) == "INVALID_SIM_STATE"

    dead_plan = make_plan(client, admin_headers)
    client.patch(f"{API}/plans/{dead_plan['id']}/status", headers=admin_headers, params={"plan_status": "inactive"})
    fresh = make_sim(client, admin_headers, c["id"])
    r = client.post(f"{API}/subscriptions", headers=admin_headers, json={"customer_id": c["id"], "sim_id": fresh["id"], "plan_id": dead_plan["id"]})
    assert r.status_code == 409 and error_code(r) == "PLAN_INACTIVE"

    client.patch(f"{API}/customers/{c['id']}/activation", headers=admin_headers, json={"is_active": False})
    r = client.post(f"{API}/subscriptions", headers=admin_headers, json={"customer_id": c["id"], "sim_id": fresh["id"], "plan_id": p["id"]})
    assert r.status_code == 409 and error_code(r) == "CUSTOMER_INACTIVE"


def test_unassigned_sim_is_claimed_by_the_subscribing_customer(client, admin_headers, setup):
    loose = make_sim(client, admin_headers)
    sub = make_subscription(client, admin_headers, setup["cust"]["id"], loose["id"], setup["plan"]["id"])
    assert client.get(f"{API}/sims/{loose['id']}", headers=admin_headers).json()["customer_id"] == setup["cust"]["id"]
    assert sub["customer_id"] == setup["cust"]["id"]


def test_upgrade_and_downgrade_are_detected_by_price(client, admin_headers, setup):
    c, s = setup["cust"], setup["sim"]
    sub = make_subscription(client, admin_headers, c["id"], s["id"], setup["plan"]["id"])
    pricey, cheap = make_plan(client, admin_headers, price=999), make_plan(client, admin_headers, price=99)

    up = client.post(f"{API}/subscriptions/{sub['id']}/change-plan", headers=admin_headers, json={"new_plan_id": pricey["id"]})
    assert up.status_code == 200 and up.json()["plan_id"] == pricey["id"]
    down = client.post(f"{API}/subscriptions/{sub['id']}/change-plan", headers=admin_headers, json={"new_plan_id": cheap["id"], "notes": "budget"})
    assert down.status_code == 200
    same = client.post(f"{API}/subscriptions/{sub['id']}/change-plan", headers=admin_headers, json={"new_plan_id": cheap["id"]})
    assert same.status_code == 409 and error_code(same) == "SAME_PLAN"

    history = client.get(f"{API}/subscriptions/{sub['id']}/history", headers=admin_headers).json()
    assert sorted(h["action"] for h in history) == ["created", "downgraded", "upgraded"]
    assert client.get(f"{API}/sims/{s['id']}", headers=admin_headers).json()["current_plan_id"] == cheap["id"]


def test_subscription_lifecycle_suspend_reactivate_cancel(client, admin_headers, setup):
    c, s = setup["cust"], setup["sim"]
    sub = make_subscription(client, admin_headers, c["id"], s["id"], setup["plan"]["id"])
    url = f"{API}/subscriptions/{sub['id']}"
    noop = client.post(f"{url}/reactivate", headers=admin_headers)
    assert noop.status_code == 409 and error_code(noop) == "ALREADY_IN_STATE"          # no misleading history rows
    assert client.post(f"{url}/suspend", headers=admin_headers).json()["status"] == "suspended"
    assert client.post(f"{url}/suspend", headers=admin_headers).status_code == 409
    other = make_plan(client, admin_headers)
    blocked = client.post(f"{url}/change-plan", headers=admin_headers, json={"new_plan_id": other["id"]})
    assert blocked.status_code == 409                                                  # can't change plan while suspended
    assert client.post(f"{url}/reactivate", headers=admin_headers).json()["status"] == "active"
    assert client.post(f"{url}/cancel", headers=admin_headers).json()["status"] == "cancelled"
    for action in ("reactivate", "suspend", "renew"):
        r = client.post(f"{url}/{action}", headers=admin_headers)
        assert r.status_code == 409 and error_code(r) == "INVALID_TRANSITION", action
    assert client.get(f"{API}/sims/{s['id']}", headers=admin_headers).json()["status"] == "suspended"
    actions = [h["action"] for h in client.get(f"{url}/history", headers=admin_headers).json()]
    assert {"created", "suspended", "reactivated", "cancelled"} <= set(actions)


def test_renewal_extends_from_current_end_date(client, admin_headers, setup):
    sub = make_subscription(client, admin_headers, setup["cust"]["id"], setup["sim"]["id"], setup["plan"]["id"])
    renewed = client.post(f"{API}/subscriptions/{sub['id']}/renew", headers=admin_headers).json()
    assert datetime.fromisoformat(renewed["end_date"]) - datetime.fromisoformat(sub["end_date"]) == timedelta(days=28)


def test_renewal_of_lapsed_subscription_restarts_from_now(client, admin_headers, setup, db):
    from app.models.subscription import Subscription
    from app.models.enums import SubscriptionStatus
    sub = make_subscription(client, admin_headers, setup["cust"]["id"], setup["sim"]["id"], setup["plan"]["id"])
    row = db.get(Subscription, sub["id"])
    row.end_date = datetime.now(timezone.utc) - timedelta(days=10)
    row.status = SubscriptionStatus.EXPIRED
    db.commit()
    renewed = client.post(f"{API}/subscriptions/{sub['id']}/renew", headers=admin_headers).json()
    remaining = datetime.fromisoformat(renewed["end_date"]) - datetime.now(timezone.utc)
    assert renewed["status"] == "active" and timedelta(days=27) < remaining <= timedelta(days=28)


def test_subscription_list_filters(client, admin_headers, setup):
    c, p = setup["cust"], setup["plan"]
    s1 = make_subscription(client, admin_headers, c["id"], setup["sim"]["id"], p["id"])
    sim2 = make_sim(client, admin_headers, c["id"])
    s2 = make_subscription(client, admin_headers, c["id"], sim2["id"], p["id"])
    client.post(f"{API}/subscriptions/{s2['id']}/suspend", headers=admin_headers)
    active = client.get(f"{API}/subscriptions", headers=admin_headers, params={"customer_id": c["id"], "sub_status": "active"}).json()
    assert [s["id"] for s in active["items"]] == [s1["id"]]


# ---------------------------------------------------------------------------- usage
def _usage(client, headers, sub_id, day=None, **kw):
    body = {"subscription_id": sub_id, "usage_date": (day or datetime.now(timezone.utc).date()).isoformat(), **kw}
    return client.post(f"{API}/usage", headers=headers, json=body)


def test_usage_accumulates_within_a_day_and_computes_quota(client, admin_headers, setup):
    plan = make_plan(client, admin_headers, data_limit_mb=1000, voice_limit_minutes=100, sms_limit_count=50)
    sub = make_subscription(client, admin_headers, setup["cust"]["id"], setup["sim"]["id"], plan["id"])
    _usage(client, admin_headers, sub["id"], data_used_mb=200, voice_used_minutes=10, sms_used_count=5)
    r = _usage(client, admin_headers, sub["id"], data_used_mb=50, voice_used_minutes=15.5, sms_used_count=5)
    assert r.json()["data_used_mb"] == 250

    s = client.get(f"{API}/usage/subscriptions/{sub['id']}/summary", headers=admin_headers).json()
    assert s["total_data_used_mb"] == 250 and s["data_usage_percent"] == 25.0 and s["data_remaining_mb"] == 750
    assert s["voice_usage_percent"] == 25.5 and s["voice_remaining_minutes"] == 74.5
    assert s["sms_usage_percent"] == 20.0 and s["sms_remaining_count"] == 40


def test_usage_over_quota_and_unlimited_plans(client, admin_headers, setup):
    limited = make_plan(client, admin_headers, data_limit_mb=100)
    sub = make_subscription(client, admin_headers, setup["cust"]["id"], setup["sim"]["id"], limited["id"])
    _usage(client, admin_headers, sub["id"], data_used_mb=150)
    s = client.get(f"{API}/usage/subscriptions/{sub['id']}/summary", headers=admin_headers).json()
    assert s["data_usage_percent"] == 150.0 and s["data_remaining_mb"] == -50

    unlimited = make_plan(client, admin_headers, data_limit_mb=None, voice_limit_minutes=None, sms_limit_count=None)
    sim2 = make_sim(client, admin_headers, setup["cust"]["id"])
    sub2 = make_subscription(client, admin_headers, setup["cust"]["id"], sim2["id"], unlimited["id"])
    _usage(client, admin_headers, sub2["id"], data_used_mb=5000)
    s2 = client.get(f"{API}/usage/subscriptions/{sub2['id']}/summary", headers=admin_headers).json()
    assert s2["data_usage_percent"] is None and s2["data_remaining_mb"] is None and s2["total_data_used_mb"] == 5000


def test_usage_period_filtering_and_daily_records(client, admin_headers, setup):
    sub = make_subscription(client, admin_headers, setup["cust"]["id"], setup["sim"]["id"], setup["plan"]["id"])
    today = datetime.now(timezone.utc).date()
    for offset, mb in ((0, 100), (1, 200), (5, 400)):
        _usage(client, admin_headers, sub["id"], day=today - timedelta(days=offset), data_used_mb=mb)
    window = client.get(f"{API}/usage/subscriptions/{sub['id']}/summary", headers=admin_headers,
                        params={"period_start": (today - timedelta(days=2)).isoformat(), "period_end": today.isoformat()}).json()
    assert window["total_data_used_mb"] == 300
    daily = client.get(f"{API}/usage/sims/{setup['sim']['id']}", headers=admin_headers,
                       params={"period_start": (today - timedelta(days=10)).isoformat(), "period_end": today.isoformat()}).json()
    assert [d["data_used_mb"] for d in daily] == [400, 200, 100]  # ordered by date ascending


def test_customer_usage_and_plan_utilization(client, admin_headers, setup):
    plan = setup["plan"]
    s1 = make_subscription(client, admin_headers, setup["cust"]["id"], setup["sim"]["id"], plan["id"])
    cust2 = make_customer(client, admin_headers)
    s2 = make_subscription(client, admin_headers, cust2["id"], make_sim(client, admin_headers, cust2["id"])["id"], plan["id"])
    _usage(client, admin_headers, s1["id"], data_used_mb=1000)
    _usage(client, admin_headers, s2["id"], data_used_mb=3000)
    per_customer = client.get(f"{API}/usage/customers/{setup['cust']['id']}", headers=admin_headers).json()
    assert len(per_customer) == 1 and per_customer[0]["total_data_used_mb"] == 1000
    util = client.get(f"{API}/usage/plans/{plan['id']}/utilization", headers=admin_headers).json()
    assert util["subscriber_count"] == 2 and util["avg_data_used_mb"] == 2000


def test_usage_for_unknown_subscription_is_404(client, admin_headers):
    assert _usage(client, admin_headers, "nope", data_used_mb=1).status_code == 404
    assert client.get(f"{API}/usage/subscriptions/nope/summary", headers=admin_headers).status_code == 404


def test_sim_plan_assignment_endpoint(client, admin_headers):
    sim, plan = make_sim(client, admin_headers), make_plan(client, admin_headers)
    r = client.post(f"{API}/sims/{sim['id']}/assign-plan", headers=admin_headers, json={"plan_id": plan["id"]})
    assert r.status_code == 200 and r.json()["current_plan_id"] == plan["id"]
    assert client.post(f"{API}/sims/{sim['id']}/assign-plan", headers=admin_headers, json={"plan_id": "nope"}).status_code == 404


def test_device_assign_sim_success_and_filter_by_customer(client, admin_headers):
    cust = make_customer(client, admin_headers)
    sim = make_sim(client, admin_headers, cust["id"])
    device = _device(client, admin_headers, customer_id=cust["id"]).json()
    r = client.post(f"{API}/devices/{device['id']}/assign-sim", headers=admin_headers, json={"sim_id": sim["id"]})
    assert r.status_code == 200 and r.json()["sim_id"] == sim["id"]

    other = _device(client, admin_headers).json()
    mine = client.get(f"{API}/devices", headers=admin_headers, params={"customer_id": cust["id"]}).json()
    assert [d["id"] for d in mine["items"]] == [device["id"]]


def test_plan_utilization_with_zero_subscribers(client, admin_headers):
    plan = make_plan(client, admin_headers)
    r = client.get(f"{API}/usage/plans/{plan['id']}/utilization", headers=admin_headers).json()
    assert r == {"plan_id": plan["id"], "subscriber_count": 0, "avg_data_used_mb": 0.0,
                 "avg_voice_used_minutes": 0.0, "avg_sms_used_count": 0.0}


def test_usage_endpoints_404_on_unknown_sim_or_plan(client, admin_headers):
    assert client.get(f"{API}/usage/sims/nope", headers=admin_headers).status_code == 404
    assert client.get(f"{API}/usage/plans/nope/utilization", headers=admin_headers).status_code == 404
