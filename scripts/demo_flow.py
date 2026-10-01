"""
Mandatory end-to-end demo flow:

Admin Login -> Create Customer -> Create Plan -> Register SIM -> Register Device ->
Activate Subscription -> Generate Usage -> Register Network Tower -> Create Outage ->
Identify Affected Customers -> Create Support Ticket -> Assign Agent/Technician ->
Track SLA -> Resolve Ticket -> Restore Network -> Generate Notifications ->
View Operations Dashboard -> Generate Reports -> Verify Audit Logs

Run against a live server (after `python -m scripts.seed` and `uvicorn app.main:app`):

    python -m scripts.demo_flow --base-url http://localhost:8000

`run_demo` accepts any httpx-compatible client, so the test-suite reuses it with
FastAPI's TestClient.
"""
import argparse
import random
from datetime import date, datetime, timedelta, timezone
from uuid import uuid4

API = "/api/v1"


def _ok(resp, label, expected=(200, 201)):
    if resp.status_code not in expected:
        raise AssertionError(f"[{label}] {resp.request.method} {resp.request.url} -> {resp.status_code}: {resp.text}")
    return resp.json() if resp.content else None


def run_demo(client, admin_email="admin@example.com", admin_password="Admin@12345", log=print) -> dict:
    sfx = uuid4().hex[:6].upper()
    out: dict = {}
    n = 0

    def step(title):
        nonlocal n
        n += 1
        log(f"\n[{n:02d}] {title}")

    # 1 ---------------------------------------------------------------- login
    step("Admin login")
    tokens = _ok(client.post(f"{API}/auth/login", data={"username": admin_email, "password": admin_password}), "login")
    H = {"Authorization": f"Bearer {tokens['access_token']}"}
    me = _ok(client.get(f"{API}/auth/me", headers=H), "me")
    log(f"     logged in as {me['email']} ({me['role']})")
    out["admin"] = me

    # 2 ------------------------------------------------------------- customer
    step("Create customer")
    customer = _ok(client.post(f"{API}/customers", headers=H, json={
        "full_name": f"Asha Raman {sfx}", "email": f"asha.{sfx.lower()}@example.com",
        "phone": f"+9198{random.randint(10000000, 99999999)}", "customer_type": "postpaid",
        "kyc_document_type": "aadhaar", "kyc_document_number": "XXXX-XXXX-1234",
        "address": {"line1": "12 Marina Road", "city": "Chennai", "state": "Tamil Nadu",
                    "postal_code": "600001", "is_primary": True},
    }), "create customer")
    customer = _ok(client.patch(f"{API}/customers/{customer['id']}/kyc", headers=H, json={"kyc_status": "verified"}), "kyc")
    log(f"     {customer['customer_code']} KYC={customer['kyc_status']}")
    out["customer"] = customer

    # 3 ------------------------------------------------------------------ plan
    step("Create service plan")
    plan = _ok(client.post(f"{API}/plans", headers=H, json={
        "name": f"Postpaid Combo 499 {sfx}", "code": f"PLN-{sfx}", "plan_type": "postpaid", "category": "combo",
        "price": 499, "validity_days": 30, "data_limit_mb": 10000, "voice_limit_minutes": 1000, "sms_limit_count": 500,
    }), "create plan")
    log(f"     {plan['code']}  Rs.{plan['price']}  data={plan['data_limit_mb']}MB")
    out["plan"] = plan

    # 4 ------------------------------------------------------------------- SIM
    step("Register SIM and map to customer")
    sim = _ok(client.post(f"{API}/sims", headers=H, json={"sim_number": f"8991{random.randint(10**14, 10**15 - 1)}", "sim_type": "physical"}), "create sim")
    sim = _ok(client.post(f"{API}/sims/{sim['id']}/assign-customer", headers=H, json={"customer_id": customer["id"]}), "assign sim")
    log(f"     SIM {sim['sim_number']} status={sim['status']}")
    out["sim"] = sim

    # 5 ---------------------------------------------------------------- device
    step("Register device (and verify duplicate-IMEI protection)")
    imei = str(random.randint(10**14, 10**15 - 1))
    device = _ok(client.post(f"{API}/devices", headers=H, json={
        "imei": imei, "model": "Galaxy S24", "manufacturer": "Samsung", "device_type": "smartphone",
        "customer_id": customer["id"], "sim_id": sim["id"],
    }), "create device")
    dup = client.post(f"{API}/devices", headers=H, json={"imei": imei, "model": "X", "manufacturer": "Y"})
    assert dup.status_code == 409, f"duplicate IMEI should be rejected, got {dup.status_code}"
    log(f"     device {device['imei']} registered; duplicate IMEI correctly rejected (409)")
    out["device"] = device

    # 6 ----------------------------------------------------------- subscription
    step("Activate subscription")
    sub = _ok(client.post(f"{API}/subscriptions", headers=H, json={
        "customer_id": customer["id"], "sim_id": sim["id"], "plan_id": plan["id"]}), "create subscription")
    sim = _ok(client.get(f"{API}/sims/{sim['id']}", headers=H), "get sim")
    log(f"     subscription {sub['status']} until {sub['end_date'][:10]}; SIM now {sim['status']}")
    out["subscription"] = sub

    # 7 ------------------------------------------------------------------ usage
    step("Generate usage")
    _ok(client.post(f"{API}/usage", headers=H, json={
        "subscription_id": sub["id"], "usage_date": date.today().isoformat(),
        "data_used_mb": 2500, "voice_used_minutes": 120, "sms_used_count": 40}), "usage")
    summary = _ok(client.get(f"{API}/usage/subscriptions/{sub['id']}/summary", headers=H), "usage summary")
    log(f"     data {summary['data_usage_percent']}% used, {summary['data_remaining_mb']}MB remaining")
    assert summary["data_usage_percent"] == 25.0
    out["usage_summary"] = summary

    # 8 ------------------------------------------------------------------ tower
    step("Register network tower and map SIM to it")
    tower = _ok(client.post(f"{API}/towers", headers=H, json={
        "code": f"TWR-{sfx}", "name": f"Marina Beach Tower {sfx}", "tower_type": "macro",
        "latitude": 13.0500, "longitude": 80.2824, "coverage_radius_km": 6, "capacity": 5000}), "create tower")
    _ok(client.post(f"{API}/sims/{sim['id']}/assign-tower", headers=H, json={"tower_id": tower["id"]}), "assign tower")
    log(f"     tower {tower['code']} ({tower['status']})")
    out["tower"] = tower

    # 9-10 ------------------------------------------------ outage + affected
    step("Create outage and auto-identify affected customers")
    now = datetime.now(timezone.utc)
    outage = _ok(client.post(f"{API}/outages", headers=H, json={
        "title": "Fibre cut near Marina", "description": "Backhaul link down", "outage_type": "unplanned",
        "severity": "high", "tower_ids": [tower["id"]], "start_time": now.isoformat(),
        "expected_resolution": (now + timedelta(hours=4)).isoformat()}), "create outage")
    affected = _ok(client.get(f"{API}/outages/{outage['id']}/affected-customers", headers=H), "affected")
    affected_ids = [a["customer_id"] for a in affected]
    assert customer["id"] in affected_ids, "customer should be auto-identified as affected"
    log(f"     outage severity={outage['severity']}; {len(affected)} affected customer(s) identified automatically")
    out["outage"] = outage
    out["affected_customers"] = affected_ids

    # 11 ---------------------------------------------------------------- ticket
    step("Create support ticket")
    ticket = _ok(client.post(f"{API}/tickets", headers=H, json={
        "customer_id": customer["id"], "category": "network_issue", "priority": "high",
        "subject": "No signal since morning", "description": "Phone shows no service near Marina.",
        "related_sim_id": sim["id"], "related_device_id": device["id"]}), "create ticket")
    log(f"     {ticket['ticket_code']} status={ticket['status']} priority={ticket['priority']}")
    out["ticket"] = ticket

    # 12 ----------------------------------------------------- assign agent/tech
    step("Assign support agent and field technician")
    agent = _ok(client.post(f"{API}/auth/users", headers=H, json={
        "email": f"agent.{sfx.lower()}@example.com", "full_name": "Priya Agent",
        "password": "Agent@12345", "role": "support_agent"}), "create agent")
    ticket = _ok(client.post(f"{API}/tickets/{ticket['id']}/assign-agent", headers=H, json={"agent_id": agent["id"]}), "assign agent")
    tech = _ok(client.post(f"{API}/technicians", headers=H, json={
        "full_name": "Karthik Tech", "phone": "+919800000001", "skills": "fibre,rf,base-station",
        "service_area": "Chennai Central"}), "create technician")
    ticket = _ok(client.post(f"{API}/tickets/{ticket['id']}/assign-technician", headers=H, json={"technician_id": tech["id"]}), "assign technician")
    workload = _ok(client.get(f"{API}/technicians/{tech['id']}/workload", headers=H), "workload")
    log(f"     agent={agent['full_name']}, technician={tech['full_name']} (pending jobs: {workload['pending_jobs']})")
    assert workload["pending_jobs"] == 1
    out["agent"], out["technician"] = agent, tech

    # 13 ------------------------------------------------------------------- SLA
    step("Track SLA")
    sla = _ok(client.get(f"{API}/sla/tickets/{ticket['id']}", headers=H), "sla")
    soon = _ok(client.get(f"{API}/sla/soon-to-breach", headers=H, params={"within_minutes": 100000}), "soon to breach")
    breached = _ok(client.get(f"{API}/sla/breached", headers=H), "breached")
    assert any(t["ticket_id"] == ticket["id"] for t in soon)
    log(f"     deadline {sla['sla_deadline'][:16]}, breached={sla['breached']}; currently breached tickets: {len(breached)}")
    out["sla"] = sla

    # 14 ------------------------------------------------------ resolve ticket
    step("Resolve ticket")
    _ok(client.patch(f"{API}/tickets/{ticket['id']}/status", headers=H, json={"status": "in_progress"}), "in progress")
    _ok(client.post(f"{API}/tickets/{ticket['id']}/comments", headers=H, json={"body": "Fibre cut confirmed at backhaul.", "is_internal": True}), "comment")
    ticket = _ok(client.patch(f"{API}/tickets/{ticket['id']}/status", headers=H, json={
        "status": "resolved", "resolution_notes": "Backhaul restored by field team."}), "resolve")
    assignments = _ok(client.get(f"{API}/technicians/{tech['id']}/assignments", headers=H), "assignments")
    _ok(client.post(f"{API}/technicians/assignments/{assignments[0]['id']}/complete", headers=H), "complete assignment")
    sla = _ok(client.get(f"{API}/sla/tickets/{ticket['id']}", headers=H), "sla after")
    assert sla["resolved_time"] is not None and sla["breached"] is False
    history = _ok(client.get(f"{API}/tickets/{ticket['id']}/history", headers=H), "ticket history")
    log(f"     ticket {ticket['status']}; SLA met (breached={sla['breached']}); {len(history)} history entries")
    out["ticket_final"] = ticket

    # 15 -------------------------------------------------------- restore network
    step("Restore network (resolve outage)")
    _ok(client.post(f"{API}/outages/{outage['id']}/in-progress", headers=H), "outage in progress")
    outage = _ok(client.post(f"{API}/outages/{outage['id']}/resolve", headers=H, json={}), "resolve outage")
    tower = _ok(client.get(f"{API}/towers/{tower['id']}", headers=H), "tower")
    log(f"     outage {outage['status']}; tower {tower['status']}")
    out["outage_final"] = outage

    # 16 ----------------------------------------------------------- notifications
    step("Notifications generated (background tasks)")
    notes = _ok(client.get(f"{API}/notifications/all", headers=H, params={"customer_id": customer["id"]}), "notifications")
    types = sorted({x["notification_type"] for x in notes["items"]})
    log(f"     {notes['total']} notification(s) for customer: {', '.join(types)}")
    assert "network_outage" in types and "service_restoration" in types and "ticket_assignment" in types
    out["notification_types"] = types

    # 17 --------------------------------------------------------------- dashboard
    step("Operations dashboard")
    dash = _ok(client.get(f"{API}/dashboard/operations", headers=H), "dashboard")
    log("     " + ", ".join(f"{k}={dash[k]}" for k in (
        "total_customers", "active_subscriptions", "active_sims", "open_network_outages",
        "open_tickets", "sla_breaches", "towers_active")))
    out["dashboard"] = dash

    # 18 ------------------------------------------------------------------ reports
    step("Reports")
    reports = {}
    for name in ("customer-growth", "subscription-trends", "plan-popularity", "data-consumption", "network-uptime",
                 "outage-frequency", "ticket-resolution-time", "sla-performance", "technician-performance",
                 "customer-service-trends"):
        reports[name] = _ok(client.get(f"{API}/reports/{name}", headers=H), f"report {name}")
    log(f"     generated {len(reports)} reports; SLA compliance={reports['sla-performance']['compliance_percent']}%")
    out["reports"] = reports

    # 19 ---------------------------------------------------------------- audit logs
    step("Verify audit logs")
    audit = _ok(client.get(f"{API}/audit-logs", headers=H, params={"page_size": 100}), "audit")
    seen = {(a["entity"], a["action"]) for a in audit["items"]}
    for expected in [("User", "LOGIN"), ("Customer", "CREATE"), ("ServicePlan", "CREATE"), ("SimCard", "CREATE"),
                     ("Device", "CREATE"), ("Subscription", "CREATE"), ("Tower", "CREATE"), ("Outage", "CREATE"),
                     ("Ticket", "CREATE"), ("Ticket", "STATUS_CHANGE"), ("Outage", "RESOLVE")]:
        assert expected in seen, f"missing audit entry {expected}"
    log(f"     {audit['total']} audit records; all expected entity/action pairs present")
    out["audit_total"] = audit["total"]

    log("\nDemo flow completed successfully.")
    return out


def main():
    import httpx

    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url", default="http://localhost:8000")
    parser.add_argument("--email", default="admin@example.com")
    parser.add_argument("--password", default="Admin@12345")
    args = parser.parse_args()
    try:
        with httpx.Client(base_url=args.base_url, timeout=30) as client:
            run_demo(client, args.email, args.password)
    except httpx.ConnectError:
        raise SystemExit(
            f"Could not connect to {args.base_url}. Start the API first (e.g. `docker compose up` or "
            "`python -m scripts.seed && uvicorn app.main:app`), or pass --base-url."
        )


if __name__ == "__main__":
    main()
