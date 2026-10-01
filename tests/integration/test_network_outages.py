from datetime import datetime, timedelta, timezone

from tests.factories import (
    API, error_code, make_customer, make_outage, make_plan, make_sim, make_subscription,
    make_ticket, make_technician, make_tower, uniq,
)


def _served_customer(client, H, tower, sim_status="active"):
    """A customer whose SIM is served by `tower`."""
    cust = make_customer(client, H)
    sim = make_sim(client, H, cust["id"])
    client.post(f"{API}/sims/{sim['id']}/assign-tower", headers=H, json={"tower_id": tower["id"]})
    if sim_status != "available":
        client.patch(f"{API}/sims/{sim['id']}/status", headers=H, json={"status": "active"})
        if sim_status == "suspended":
            client.patch(f"{API}/sims/{sim['id']}/status", headers=H, json={"status": "suspended"})
    return cust, sim


def _tower_status(client, H, tower):
    return client.get(f"{API}/towers/{tower['id']}", headers=H).json()["status"]


# ------------------------------------------------------------------------ towers
def test_tower_registration_update_and_status(client, admin_headers):
    t = make_tower(client, admin_headers, code="TWR-1", tower_type="micro", coverage_radius_km=2.5, capacity=300)
    assert t["status"] == "active" and t["coverage_radius_km"] == 2.5 and t["tower_type"] == "micro"
    dup = client.post(f"{API}/towers", headers=admin_headers, json={"code": "TWR-1", "name": "x", "latitude": 1, "longitude": 1})
    assert dup.status_code == 409 and error_code(dup) == "TOWER_EXISTS"

    u = client.patch(f"{API}/towers/{t['id']}", headers=admin_headers, json={"capacity": 900, "name": "Renamed"})
    assert u.json()["capacity"] == 900 and u.json()["name"] == "Renamed"
    for s in ("maintenance", "offline", "decommissioned", "active"):
        r = client.patch(f"{API}/towers/{t['id']}/status", headers=admin_headers, params={"tower_status": s})
        assert r.json()["status"] == s
    assert client.patch(f"{API}/towers/{t['id']}/status", headers=admin_headers, params={"tower_status": "exploded"}).status_code == 422


def test_tower_filter_and_search(client, admin_headers):
    a, b = make_tower(client, admin_headers, name="Marina North"), make_tower(client, admin_headers, name="Adyar South")
    client.patch(f"{API}/towers/{b['id']}/status", headers=admin_headers, params={"tower_status": "offline"})
    assert [t["id"] for t in client.get(f"{API}/towers", headers=admin_headers, params={"tower_status": "offline"}).json()["items"]] == [b["id"]]
    assert [t["id"] for t in client.get(f"{API}/towers", headers=admin_headers, params={"search": "marina"}).json()["items"]] == [a["id"]]


# --------------------------------------------------------------------- equipment
def test_equipment_heartbeat_and_stale_detection(client, admin_headers):
    tower = make_tower(client, admin_headers)
    mk = lambda **kw: client.post(f"{API}/equipment", headers=admin_headers, json={
        "tower_id": tower["id"], "name": f"eq-{uniq()}", "equipment_type": "router", **kw}).json()
    silent, alive = mk(), mk(installation_date="2025-01-01", maintenance_schedule="2027-01-01")
    assert alive["last_heartbeat"] is None and alive["status"] == "online"

    hb = client.post(f"{API}/equipment/{alive['id']}/heartbeat", headers=admin_headers,
                     json={"cpu_usage_percent": 91.5, "memory_usage_percent": 40, "status": "degraded"}).json()
    assert hb["cpu_usage_percent"] == 91.5 and hb["status"] == "degraded" and hb["last_heartbeat"]

    stale = {e["id"] for e in client.get(f"{API}/equipment/stale", headers=admin_headers).json()}
    assert stale == {silent["id"]}                                    # never-seen equipment is stale, fresh one isn't
    by_status = client.get(f"{API}/equipment", headers=admin_headers, params={"equipment_status": "degraded"}).json()
    assert [e["id"] for e in by_status["items"]] == [alive["id"]]
    by_tower = client.get(f"{API}/equipment", headers=admin_headers, params={"tower_id": tower["id"]}).json()
    assert by_tower["total"] == 2


def test_equipment_requires_existing_tower_and_valid_type(client, admin_headers):
    r = client.post(f"{API}/equipment", headers=admin_headers, json={"tower_id": "nope", "name": "x", "equipment_type": "router"})
    assert r.status_code == 404
    tower = make_tower(client, admin_headers)
    r = client.post(f"{API}/equipment", headers=admin_headers, json={"tower_id": tower["id"], "name": "x", "equipment_type": "toaster"})
    assert r.status_code == 422


# ----------------------------------------------------------------------- outages
def test_outage_identifies_only_customers_actually_served_by_the_tower(client, admin_headers):
    hit, other = make_tower(client, admin_headers), make_tower(client, admin_headers)
    affected, _ = _served_customer(client, admin_headers, hit)
    also_affected, _ = _served_customer(client, admin_headers, hit)
    elsewhere, _ = _served_customer(client, admin_headers, other)
    suspended, _ = _served_customer(client, admin_headers, hit, sim_status="suspended")
    inactive_sim, _ = _served_customer(client, admin_headers, hit, sim_status="available")

    outage = make_outage(client, admin_headers, [hit["id"]])
    ids = {a["customer_id"] for a in client.get(f"{API}/outages/{outage['id']}/affected-customers", headers=admin_headers).json()}
    assert ids == {affected["id"], also_affected["id"]}
    assert not ids & {elsewhere["id"], suspended["id"], inactive_sim["id"]}


def test_customer_with_two_sims_on_the_tower_is_counted_once(client, admin_headers):
    tower = make_tower(client, admin_headers)
    cust, _ = _served_customer(client, admin_headers, tower)
    sim2 = make_sim(client, admin_headers, cust["id"])
    client.post(f"{API}/sims/{sim2['id']}/assign-tower", headers=admin_headers, json={"tower_id": tower["id"]})
    client.patch(f"{API}/sims/{sim2['id']}/status", headers=admin_headers, json={"status": "active"})
    outage = make_outage(client, admin_headers, [tower["id"]])
    assert len(client.get(f"{API}/outages/{outage['id']}/affected-customers", headers=admin_headers).json()) == 1


def test_outage_spanning_multiple_towers_unions_customers(client, admin_headers):
    t1, t2 = make_tower(client, admin_headers), make_tower(client, admin_headers)
    c1, _ = _served_customer(client, admin_headers, t1)
    c2, _ = _served_customer(client, admin_headers, t2)
    outage = make_outage(client, admin_headers, [t1["id"], t2["id"]], severity="critical")
    assert sorted(outage["tower_ids"]) == sorted([t1["id"], t2["id"]])
    ids = {a["customer_id"] for a in client.get(f"{API}/outages/{outage['id']}/affected-customers", headers=admin_headers).json()}
    assert ids == {c1["id"], c2["id"]}


def test_outage_validation(client, admin_headers):
    now = datetime.now(timezone.utc).isoformat()
    base = {"title": "t", "severity": "low", "start_time": now}
    assert client.post(f"{API}/outages", headers=admin_headers, json={**base, "tower_ids": ["nope"]}).status_code == 404
    assert client.post(f"{API}/outages", headers=admin_headers, json={**base, "tower_ids": []}).status_code == 422
    tower = make_tower(client, admin_headers)
    assert client.post(f"{API}/outages", headers=admin_headers, json={**base, "tower_ids": [tower["id"]], "severity": "apocalyptic"}).status_code == 422


def test_unplanned_outage_takes_tower_offline_and_resolution_restores_it(client, admin_headers):
    tower = make_tower(client, admin_headers)
    outage = make_outage(client, admin_headers, [tower["id"]], outage_type="unplanned")
    assert _tower_status(client, admin_headers, tower) == "offline"
    r = client.post(f"{API}/outages/{outage['id']}/resolve", headers=admin_headers, json={})
    assert r.status_code == 200 and r.json()["status"] == "resolved" and r.json()["actual_resolution"]
    assert _tower_status(client, admin_headers, tower) == "active"


def test_planned_outage_puts_tower_into_maintenance(client, admin_headers):
    tower = make_tower(client, admin_headers)
    outage = make_outage(client, admin_headers, [tower["id"]], outage_type="planned", severity="low")
    assert _tower_status(client, admin_headers, tower) == "maintenance"
    client.post(f"{API}/outages/{outage['id']}/resolve", headers=admin_headers, json={})
    assert _tower_status(client, admin_headers, tower) == "active"


def test_decommissioned_tower_is_left_alone(client, admin_headers):
    tower = make_tower(client, admin_headers)
    client.patch(f"{API}/towers/{tower['id']}/status", headers=admin_headers, params={"tower_status": "decommissioned"})
    outage = make_outage(client, admin_headers, [tower["id"]])
    assert _tower_status(client, admin_headers, tower) == "decommissioned"
    client.post(f"{API}/outages/{outage['id']}/resolve", headers=admin_headers, json={})
    assert _tower_status(client, admin_headers, tower) == "decommissioned"


def test_overlapping_outages_keep_tower_down_until_the_last_one_resolves(client, admin_headers):
    tower = make_tower(client, admin_headers)
    first = make_outage(client, admin_headers, [tower["id"]], title="first")
    second = make_outage(client, admin_headers, [tower["id"]], title="second")
    client.post(f"{API}/outages/{first['id']}/resolve", headers=admin_headers, json={})
    assert _tower_status(client, admin_headers, tower) == "offline"     # still covered by `second`
    client.post(f"{API}/outages/{second['id']}/resolve", headers=admin_headers, json={})
    assert _tower_status(client, admin_headers, tower) == "active"


def test_outage_status_lifecycle_guards(client, admin_headers):
    tower = make_tower(client, admin_headers)
    o = make_outage(client, admin_headers, [tower["id"]])
    assert o["status"] == "open"
    assert client.post(f"{API}/outages/{o['id']}/in-progress", headers=admin_headers).json()["status"] == "in_progress"
    again = client.post(f"{API}/outages/{o['id']}/in-progress", headers=admin_headers)
    assert again.status_code == 409 and error_code(again) == "INVALID_TRANSITION"
    client.post(f"{API}/outages/{o['id']}/resolve", headers=admin_headers, json={})
    twice = client.post(f"{API}/outages/{o['id']}/resolve", headers=admin_headers, json={})
    assert twice.status_code == 409 and error_code(twice) == "ALREADY_RESOLVED"
    assert client.post(f"{API}/outages/{o['id']}/in-progress", headers=admin_headers).status_code == 409


def test_outage_resolution_accepts_explicit_timestamp(client, admin_headers):
    tower = make_tower(client, admin_headers)
    o = make_outage(client, admin_headers, [tower["id"]])
    when = (datetime.now(timezone.utc) - timedelta(hours=1)).replace(microsecond=0)
    r = client.post(f"{API}/outages/{o['id']}/resolve", headers=admin_headers, json={"actual_resolution": when.isoformat()})
    assert datetime.fromisoformat(r.json()["actual_resolution"]) == when


def test_outage_notifications_go_out_on_creation_and_restoration(client, admin_headers):
    tower = make_tower(client, admin_headers)
    cust, _ = _served_customer(client, admin_headers, tower)
    bystander = make_customer(client, admin_headers)
    o = make_outage(client, admin_headers, [tower["id"]])
    types = lambda cid: sorted(n["notification_type"] for n in client.get(
        f"{API}/notifications/all", headers=admin_headers, params={"customer_id": cid}).json()["items"])
    assert types(cust["id"]) == ["network_outage"]
    client.post(f"{API}/outages/{o['id']}/resolve", headers=admin_headers, json={})
    assert types(cust["id"]) == ["network_outage", "service_restoration"]
    assert types(bystander["id"]) == []


def test_outage_list_filters_search_and_tower_changes_are_audited(client, admin_headers):
    t1, t2 = make_tower(client, admin_headers), make_tower(client, admin_headers)
    a = make_outage(client, admin_headers, [t1["id"]], title="Fibre cut Adyar", severity="critical")
    make_outage(client, admin_headers, [t2["id"]], title="Power failure", severity="low")
    client.post(f"{API}/outages/{a['id']}/resolve", headers=admin_headers, json={})
    q = lambda **p: [o["title"] for o in client.get(f"{API}/outages", headers=admin_headers, params=p).json()["items"]]
    assert q(severity="critical") == ["Fibre cut Adyar"]
    assert q(outage_status="open") == ["Power failure"]
    assert q(search="fibre") == ["Fibre cut Adyar"]
    logs = client.get(f"{API}/audit-logs", headers=admin_headers, params={"entity": "Tower", "entity_id": t1["id"], "action": "STATUS_CHANGE"}).json()
    assert logs["total"] == 2   # offline on creation, active on resolution
    assert "offline" in logs["items"][1]["new_value"] and "active" in logs["items"][0]["new_value"]


def test_network_uptime_report_reflects_downtime(client, admin_headers):
    healthy, hit = make_tower(client, admin_headers), make_tower(client, admin_headers)
    start = datetime.now(timezone.utc) - timedelta(hours=72)
    o = make_outage(client, admin_headers, [hit["id"]], start_time=start.isoformat())
    client.post(f"{API}/outages/{o['id']}/resolve", headers=admin_headers,
                json={"actual_resolution": (start + timedelta(hours=36)).isoformat()})
    report = {r["tower_id"]: r["uptime_percent"] for r in client.get(f"{API}/reports/network-uptime", headers=admin_headers).json()}
    assert report[healthy["id"]] == 100.0
    assert report[hit["id"]] == 95.0                                     # 36h down of a 720h window
    freq = client.get(f"{API}/reports/outage-frequency", headers=admin_headers).json()
    assert sum(r["outage_count"] for r in freq) == 1


# ------------------------------------------------------------------- technicians
def test_technician_assignment_workload_and_completion(client, admin_headers):
    cust = make_customer(client, admin_headers)
    tech = make_technician(client, admin_headers)
    t1, t2 = make_ticket(client, admin_headers, cust["id"]), make_ticket(client, admin_headers, cust["id"])
    assign = lambda tid: client.post(f"{API}/technicians/assignments", headers=admin_headers,
                                     json={"technician_id": tech["id"], "target_type": "ticket", "target_id": tid})
    a1, a2 = assign(t1["id"]).json(), assign(t2["id"]).json()
    assert client.get(f"{API}/technicians/{tech['id']}", headers=admin_headers).json()["availability_status"] == "busy"
    w = client.get(f"{API}/technicians/{tech['id']}/workload", headers=admin_headers).json()
    assert (w["pending_jobs"], w["completed_jobs"]) == (2, 0)

    client.post(f"{API}/technicians/assignments/{a1['id']}/complete", headers=admin_headers, params={"notes": "done"})
    w = client.get(f"{API}/technicians/{tech['id']}/workload", headers=admin_headers).json()
    assert (w["pending_jobs"], w["completed_jobs"]) == (1, 1)
    assert client.get(f"{API}/technicians/{tech['id']}", headers=admin_headers).json()["availability_status"] == "busy"
    client.post(f"{API}/technicians/assignments/{a2['id']}/complete", headers=admin_headers)
    assert client.get(f"{API}/technicians/{tech['id']}", headers=admin_headers).json()["availability_status"] == "available"

    done = client.get(f"{API}/technicians/{tech['id']}/assignments", headers=admin_headers, params={"assignment_status": "completed"}).json()
    assert len(done) == 2 and all(d["completed_at"] for d in done)
    assert client.get(f"{API}/tickets/{t1['id']}", headers=admin_headers).json()["assigned_technician_id"] == tech["id"]


def test_reassignment_transfers_the_job_and_rebalances_availability(client, admin_headers):
    cust = make_customer(client, admin_headers)
    old, new = make_technician(client, admin_headers), make_technician(client, admin_headers)
    ticket = make_ticket(client, admin_headers, cust["id"])
    a = client.post(f"{API}/technicians/assignments", headers=admin_headers,
                    json={"technician_id": old["id"], "target_type": "ticket", "target_id": ticket["id"]}).json()
    r = client.post(f"{API}/technicians/assignments/{a['id']}/reassign", headers=admin_headers, json={"new_technician_id": new["id"]})
    assert r.status_code == 200 and r.json()["technician_id"] == new["id"] and r.json()["status"] == "assigned"

    tech_state = lambda t: client.get(f"{API}/technicians/{t['id']}", headers=admin_headers).json()["availability_status"]
    assert tech_state(old) == "available" and tech_state(new) == "busy"
    assert client.get(f"{API}/tickets/{ticket['id']}", headers=admin_headers).json()["assigned_technician_id"] == new["id"]
    old_jobs = client.get(f"{API}/technicians/{old['id']}/assignments", headers=admin_headers).json()
    assert [j["status"] for j in old_jobs] == ["cancelled"]
    assert client.get(f"{API}/technicians/{old['id']}/workload", headers=admin_headers).json()["pending_jobs"] == 0


def test_off_duty_technician_cannot_take_work(client, admin_headers):
    cust = make_customer(client, admin_headers)
    ticket = make_ticket(client, admin_headers, cust["id"])
    off = make_technician(client, admin_headers)
    client.patch(f"{API}/technicians/{off['id']}", headers=admin_headers, json={"availability_status": "off_duty"})
    r = client.post(f"{API}/technicians/assignments", headers=admin_headers,
                    json={"technician_id": off["id"], "target_type": "ticket", "target_id": ticket["id"]})
    assert r.status_code == 409 and error_code(r) == "TECHNICIAN_UNAVAILABLE"
    ok = make_technician(client, admin_headers)
    a = client.post(f"{API}/technicians/assignments", headers=admin_headers,
                    json={"technician_id": ok["id"], "target_type": "ticket", "target_id": ticket["id"]}).json()
    r = client.post(f"{API}/technicians/assignments/{a['id']}/reassign", headers=admin_headers, json={"new_technician_id": off["id"]})
    assert r.status_code == 409
    assert client.get(f"{API}/technicians/{ok['id']}/assignments", headers=admin_headers).json()[0]["status"] == "assigned"  # untouched


def test_failed_assignment_leaves_no_partial_state(client, admin_headers):
    """Assigning to a ticket that doesn't exist must roll back completely (transaction atomicity)."""
    tech = make_technician(client, admin_headers)
    r = client.post(f"{API}/technicians/assignments", headers=admin_headers,
                    json={"technician_id": tech["id"], "target_type": "ticket", "target_id": "no-such-ticket"})
    assert r.status_code == 404
    assert client.get(f"{API}/technicians/{tech['id']}", headers=admin_headers).json()["availability_status"] == "available"
    assert client.get(f"{API}/technicians/{tech['id']}/assignments", headers=admin_headers).json() == []


def test_technician_search_and_filters(client, admin_headers):
    a = make_technician(client, admin_headers, full_name="Ravi Fibre", skills="fibre,splicing", service_area="Chennai North")
    b = make_technician(client, admin_headers, full_name="Meena RF", skills="rf,antenna", service_area="Madurai")
    ids = lambda **p: [t["id"] for t in client.get(f"{API}/technicians", headers=admin_headers, params=p).json()["items"]]
    assert ids(search="splicing") == [a["id"]]
    assert ids(service_area="madurai") == [b["id"]]
    client.patch(f"{API}/technicians/{b['id']}", headers=admin_headers, json={"availability_status": "off_duty", "skills": "rf"})
    assert ids(availability="off_duty") == [b["id"]]


def test_technician_performance_report(client, admin_headers):
    cust = make_customer(client, admin_headers)
    tech = make_technician(client, admin_headers)
    for _ in range(2):
        tid = make_ticket(client, admin_headers, cust["id"])["id"]
        a = client.post(f"{API}/technicians/assignments", headers=admin_headers,
                        json={"technician_id": tech["id"], "target_type": "ticket", "target_id": tid}).json()
    client.post(f"{API}/technicians/assignments/{a['id']}/complete", headers=admin_headers)
    rep = client.get(f"{API}/reports/technician-performance", headers=admin_headers, params={"technician_id": tech["id"]}).json()
    assert rep[0]["completed_jobs"] == 1 and rep[0]["pending_jobs"] == 1 and rep[0]["avg_completion_hours"] is not None


def test_network_uptime_report_location_filter(client, admin_headers):
    chennai, other = make_tower(client, admin_headers, name="Chennai Central"), make_tower(client, admin_headers, name="Mumbai West")
    ids = {r["tower_id"] for r in client.get(f"{API}/reports/network-uptime", headers=admin_headers, params={"location": "chennai"}).json()}
    assert ids == {chennai["id"]}


def test_outage_frequency_report_severity_filter(client, admin_headers):
    tower = make_tower(client, admin_headers)
    make_outage(client, admin_headers, [tower["id"]], severity="critical")
    make_outage(client, admin_headers, [tower["id"]], severity="low")
    all_freq = client.get(f"{API}/reports/outage-frequency", headers=admin_headers).json()
    crit_freq = client.get(f"{API}/reports/outage-frequency", headers=admin_headers, params={"severity": "critical"}).json()
    assert sum(r["outage_count"] for r in all_freq) == 2 and sum(r["outage_count"] for r in crit_freq) == 1


def test_technician_performance_in_progress_bucket(client, admin_headers, db):
    from tests.factories import make_customer, make_ticket
    from app.models.technician import TechnicianAssignment
    from app.models.enums import AssignmentStatus
    cust, tech = make_customer(client, admin_headers), make_technician(client, admin_headers)
    t = make_ticket(client, admin_headers, cust["id"])
    a = client.post(f"{API}/technicians/assignments", headers=admin_headers,
                    json={"technician_id": tech["id"], "target_type": "ticket", "target_id": t["id"]}).json()
    db.query(TechnicianAssignment).filter_by(id=a["id"]).update({"status": AssignmentStatus.IN_PROGRESS})
    db.commit()
    rep = client.get(f"{API}/reports/technician-performance", headers=admin_headers, params={"technician_id": tech["id"]}).json()
    assert rep[0]["in_progress_jobs"] == 1 and rep[0]["pending_jobs"] == 0
