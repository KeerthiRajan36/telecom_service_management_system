"""Role-permission tests: who may do what, and customer data isolation."""
import pytest

from tests.factories import (
    API, make_customer, make_customer_login, make_plan, make_sim, make_subscription,
    make_ticket, make_tower, make_technician, uniq,
)

PLAN_BODY = {"name": "P", "code": "RBAC-PLAN", "plan_type": "prepaid", "category": "data", "price": 99, "validity_days": 28}
TOWER_BODY = {"code": "RBAC-T", "name": "T", "latitude": 1.0, "longitude": 2.0}


# ----------------------------------------------------------------- role matrix
@pytest.mark.parametrize("role,expected", [
    ("super_admin", 201), ("ops_manager", 201),
    ("support_agent", 403), ("network_engineer", 403), ("field_technician", 403), ("customer", 403),
])
def test_who_can_create_plans(client, admin_headers, staff, role, expected):
    headers = admin_headers if role == "super_admin" else staff(role)[1]
    body = {**PLAN_BODY, "code": f"RBAC-{uniq()}"}
    assert client.post(f"{API}/plans", headers=headers, json=body).status_code == expected


@pytest.mark.parametrize("role,expected", [
    ("super_admin", 201), ("ops_manager", 201), ("network_engineer", 201),
    ("support_agent", 403), ("field_technician", 403), ("customer", 403),
])
def test_who_can_register_towers(client, admin_headers, staff, role, expected):
    headers = admin_headers if role == "super_admin" else staff(role)[1]
    body = {**TOWER_BODY, "code": f"T-{uniq()}"}
    assert client.post(f"{API}/towers", headers=headers, json=body).status_code == expected


@pytest.mark.parametrize("role,expected", [
    ("super_admin", 201), ("ops_manager", 201), ("support_agent", 201),
    ("network_engineer", 403), ("field_technician", 403), ("customer", 403),
])
def test_who_can_create_customers(client, admin_headers, staff, role, expected):
    headers = admin_headers if role == "super_admin" else staff(role)[1]
    body = {"full_name": "N", "email": f"n.{uniq()}@example.com", "phone": f"+91{uniq()}"}
    assert client.post(f"{API}/customers", headers=headers, json=body).status_code == expected


@pytest.mark.parametrize("path", [
    "/dashboard/operations", "/audit-logs", "/reports/customer-growth", "/reports/sla-performance",
    "/customers", "/towers", "/sims", "/devices", "/subscriptions", "/outages", "/technicians", "/sla/breached",
])
def test_customers_are_locked_out_of_staff_endpoints(client, admin_headers, path):
    customer = make_customer(client, admin_headers)
    h = make_customer_login(client, admin_headers, customer)
    assert client.get(f"{API}{path}", headers=h).status_code == 403


@pytest.mark.parametrize("role", ["support_agent", "network_engineer", "field_technician"])
def test_reports_are_restricted_to_admin_and_ops(client, staff, role):
    assert client.get(f"{API}/reports/customer-growth", headers=staff(role)[1]).status_code == 403
    assert client.get(f"{API}/audit-logs", headers=staff(role)[1]).status_code == 403


def test_ops_manager_can_view_reports_dashboard_and_audit(client, staff):
    _, ops = staff("ops_manager")
    for path in ("/reports/customer-growth", "/dashboard/operations", "/audit-logs"):
        assert client.get(f"{API}{path}", headers=ops).status_code == 200


def test_every_staff_role_can_see_the_dashboard(client, staff):
    for role in ("support_agent", "network_engineer", "field_technician"):
        assert client.get(f"{API}/dashboard/operations", headers=staff(role)[1]).status_code == 200


def test_unauthenticated_requests_are_rejected_everywhere_sensitive(client):
    for path in ("/customers", "/sims", "/tickets", "/dashboard/operations", "/audit-logs", "/notifications"):
        assert client.get(f"{API}{path}").status_code == 401


def test_plan_catalogue_is_public(client, admin_headers):
    make_plan(client, admin_headers)
    assert client.get(f"{API}/plans").status_code == 200


# ------------------------------------------------------------ customer isolation
@pytest.fixture()
def two_customers(client, admin_headers):
    a, b = make_customer(client, admin_headers), make_customer(client, admin_headers)
    plan = make_plan(client, admin_headers)
    out = {}
    for key, c in (("a", a), ("b", b)):
        sim = make_sim(client, admin_headers, c["id"])
        out[key] = {
            "customer": c, "sim": sim, "headers": make_customer_login(client, admin_headers, c),
            "sub": make_subscription(client, admin_headers, c["id"], sim["id"], plan["id"]),
        }
    return out


def test_customer_can_read_own_but_not_others_profile(client, two_customers):
    a, b = two_customers["a"], two_customers["b"]
    assert client.get(f"{API}/customers/{a['customer']['id']}", headers=a["headers"]).status_code == 200
    assert client.get(f"{API}/customers/{b['customer']['id']}", headers=a["headers"]).status_code == 403


def test_customer_cannot_read_others_sim_subscription_or_usage(client, two_customers):
    a, b = two_customers["a"], two_customers["b"]
    h = a["headers"]
    assert client.get(f"{API}/sims/{a['sim']['id']}", headers=h).status_code == 200
    assert client.get(f"{API}/sims/{b['sim']['id']}", headers=h).status_code == 403
    assert client.get(f"{API}/subscriptions/{a['sub']['id']}", headers=h).status_code == 200
    assert client.get(f"{API}/subscriptions/{b['sub']['id']}", headers=h).status_code == 403
    assert client.get(f"{API}/usage/subscriptions/{b['sub']['id']}/summary", headers=h).status_code == 403
    assert client.get(f"{API}/usage/sims/{b['sim']['id']}", headers=h).status_code == 403
    assert client.get(f"{API}/usage/customers/{b['customer']['id']}", headers=h).status_code == 403
    assert client.get(f"{API}/usage/customers/{a['customer']['id']}", headers=h).status_code == 200


def test_customer_cannot_read_others_device(client, admin_headers, two_customers):
    a, b = two_customers["a"], two_customers["b"]
    r = client.post(f"{API}/devices", headers=admin_headers, json={
        "imei": f"35{uniq()}1234567"[:15], "model": "M", "manufacturer": "X", "customer_id": b["customer"]["id"]})
    assert r.status_code == 201
    assert client.get(f"{API}/devices/{r.json()['id']}", headers=a["headers"]).status_code == 403
    assert client.get(f"{API}/devices/{r.json()['id']}", headers=b["headers"]).status_code == 200


def test_customer_ticket_isolation(client, admin_headers, staff, two_customers):
    a, b = two_customers["a"], two_customers["b"]
    ta = make_ticket(client, admin_headers, a["customer"]["id"], subject="A's ticket")
    tb = make_ticket(client, admin_headers, b["customer"]["id"], subject="B's ticket")

    listed = client.get(f"{API}/tickets", headers=a["headers"]).json()
    assert [t["id"] for t in listed["items"]] == [ta["id"]]
    # even an explicit filter for someone else's customer_id is ignored
    spoof = client.get(f"{API}/tickets", headers=a["headers"], params={"customer_id": b["customer"]["id"]}).json()
    assert [t["id"] for t in spoof["items"]] == [ta["id"]]

    assert client.get(f"{API}/tickets/{tb['id']}", headers=a["headers"]).status_code == 403
    assert client.get(f"{API}/tickets/{tb['id']}/comments", headers=a["headers"]).status_code == 403
    assert client.post(f"{API}/tickets/{tb['id']}/comments", headers=a["headers"], json={"body": "hi"}).status_code == 403


def test_customer_can_only_raise_tickets_for_themselves(client, two_customers):
    a, b = two_customers["a"], two_customers["b"]
    base = {"category": "sim_issue", "subject": "s", "description": "d"}
    assert client.post(f"{API}/tickets", headers=a["headers"], json={**base, "customer_id": b["customer"]["id"]}).status_code == 403
    assert client.post(f"{API}/tickets", headers=a["headers"], json={**base, "customer_id": a["customer"]["id"]}).status_code == 201


def test_internal_comments_are_hidden_from_customers(client, admin_headers, two_customers):
    a = two_customers["a"]
    ticket = make_ticket(client, admin_headers, a["customer"]["id"])
    tid = ticket["id"]
    client.post(f"{API}/tickets/{tid}/comments", headers=admin_headers, json={"body": "internal only", "is_internal": True})
    client.post(f"{API}/tickets/{tid}/comments", headers=admin_headers, json={"body": "visible reply", "is_internal": False})

    assert client.post(f"{API}/tickets/{tid}/comments", headers=a["headers"],
                       json={"body": "sneaky", "is_internal": True}).status_code == 403
    customer_view = [c["body"] for c in client.get(f"{API}/tickets/{tid}/comments", headers=a["headers"]).json()]
    staff_view = [c["body"] for c in client.get(f"{API}/tickets/{tid}/comments", headers=admin_headers).json()]
    assert customer_view == ["visible reply"]
    assert set(staff_view) == {"internal only", "visible reply"}


def test_customer_cannot_see_ticket_history_or_change_status(client, admin_headers, two_customers):
    a = two_customers["a"]
    tid = make_ticket(client, admin_headers, a["customer"]["id"])["id"]
    assert client.get(f"{API}/tickets/{tid}/history", headers=a["headers"]).status_code == 403
    assert client.patch(f"{API}/tickets/{tid}/status", headers=a["headers"], json={"status": "closed"}).status_code == 403
    assert client.post(f"{API}/tickets/{tid}/escalate", headers=a["headers"], json={}).status_code == 403


def test_customer_service_request_isolation(client, two_customers):
    a, b = two_customers["a"], two_customers["b"]
    body = {"request_type": "sim_replacement", "details": "lost"}
    assert client.post(f"{API}/service-requests", headers=a["headers"], json={**body, "customer_id": b["customer"]["id"]}).status_code == 403
    mine = client.post(f"{API}/service-requests", headers=a["headers"], json={**body, "customer_id": a["customer"]["id"]})
    assert mine.status_code == 201
    other = client.post(f"{API}/service-requests", headers=b["headers"], json={**body, "customer_id": b["customer"]["id"]}).json()
    assert client.get(f"{API}/service-requests/{other['id']}", headers=a["headers"]).status_code == 403
    listed = client.get(f"{API}/service-requests", headers=a["headers"]).json()
    assert [r["id"] for r in listed["items"]] == [mine.json()["id"]]
    # customers cannot progress their own request
    assert client.patch(f"{API}/service-requests/{mine.json()['id']}/status", headers=a["headers"],
                        json={"status": "completed"}).status_code == 403


def test_customer_cannot_mark_someone_elses_notification_read(client, db, two_customers):
    from app.models.notification import Notification
    from app.models.enums import NotificationType
    a, b = two_customers["a"], two_customers["b"]
    note = Notification(recipient_customer_id=b["customer"]["id"], notification_type=NotificationType.PLAN_EXPIRY,
                        title="t", message="m")
    db.add(note); db.commit()
    assert client.patch(f"{API}/notifications/{note.id}/read", headers=a["headers"]).status_code == 403
    assert client.patch(f"{API}/notifications/{note.id}/read", headers=b["headers"]).status_code == 200


def test_customer_without_linked_profile_cannot_list_tickets(client):
    from tests.factories import login, PASSWORD
    email = f"orphan.{uniq()}@example.com"
    client.post(f"{API}/auth/register", json={"email": email, "full_name": "Orphan", "password": PASSWORD})
    assert client.get(f"{API}/tickets", headers=login(client, email, PASSWORD)).status_code == 403
