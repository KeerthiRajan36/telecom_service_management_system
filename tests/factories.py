"""Small helpers that create domain objects through the public API."""
import random
import uuid
from datetime import datetime, timedelta, timezone

API = "/api/v1"
PASSWORD = "Passw0rd!x"


def uniq() -> str:
    return uuid.uuid4().hex[:8]


def login(client, email: str, password: str) -> dict:
    r = client.post(f"{API}/auth/login", data={"username": email, "password": password})
    assert r.status_code == 200, r.text
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


def make_staff(client, admin_headers, role: str):
    email = f"{role}.{uniq()}@example.com"
    r = client.post(f"{API}/auth/users", headers=admin_headers, json={
        "email": email, "full_name": f"Test {role}", "password": PASSWORD, "role": role})
    assert r.status_code == 201, r.text
    return r.json(), login(client, email, PASSWORD)


def make_customer(client, headers, **overrides) -> dict:
    payload = {
        "full_name": f"Customer {uniq()}", "email": f"cust.{uniq()}@example.com",
        "phone": f"+9199{random.randint(10000000, 99999999)}", "customer_type": "postpaid",
    }
    payload.update(overrides)
    r = client.post(f"{API}/customers", headers=headers, json=payload)
    assert r.status_code == 201, r.text
    return r.json()


def make_customer_login(client, admin_headers, customer: dict):
    """Creates a customer-role login linked to the given customer profile."""
    email = f"login.{uniq()}@example.com"
    r = client.post(f"{API}/auth/users", headers=admin_headers, json={
        "email": email, "full_name": customer["full_name"], "password": PASSWORD,
        "role": "customer", "customer_id": customer["id"]})
    assert r.status_code == 201, r.text
    return login(client, email, PASSWORD)


def make_plan(client, headers, **overrides) -> dict:
    payload = {
        "name": f"Plan {uniq()}", "code": f"P-{uniq()}", "plan_type": "postpaid", "category": "combo",
        "price": 499, "validity_days": 30, "data_limit_mb": 10000,
        "voice_limit_minutes": 1000, "sms_limit_count": 500,
    }
    payload.update(overrides)
    r = client.post(f"{API}/plans", headers=headers, json=payload)
    assert r.status_code == 201, r.text
    return r.json()


def make_sim(client, headers, customer_id: str | None = None) -> dict:
    r = client.post(f"{API}/sims", headers=headers, json={"sim_number": f"8991{random.randint(10**14, 10**15 - 1)}"})
    assert r.status_code == 201, r.text
    sim = r.json()
    if customer_id:
        r = client.post(f"{API}/sims/{sim['id']}/assign-customer", headers=headers, json={"customer_id": customer_id})
        assert r.status_code == 200, r.text
        sim = r.json()
    return sim


def make_subscription(client, headers, customer_id: str, sim_id: str, plan_id: str) -> dict:
    r = client.post(f"{API}/subscriptions", headers=headers, json={
        "customer_id": customer_id, "sim_id": sim_id, "plan_id": plan_id})
    assert r.status_code == 201, r.text
    return r.json()


def make_tower(client, headers, **overrides) -> dict:
    payload = {"code": f"T-{uniq()}", "name": f"Tower {uniq()}", "latitude": 13.05, "longitude": 80.28}
    payload.update(overrides)
    r = client.post(f"{API}/towers", headers=headers, json=payload)
    assert r.status_code == 201, r.text
    return r.json()


def make_outage(client, headers, tower_ids: list[str], **overrides) -> dict:
    now = datetime.now(timezone.utc)
    payload = {"title": "Test outage", "severity": "high", "tower_ids": tower_ids,
               "start_time": now.isoformat(), "expected_resolution": (now + timedelta(hours=2)).isoformat()}
    payload.update(overrides)
    r = client.post(f"{API}/outages", headers=headers, json=payload)
    assert r.status_code == 201, r.text
    return r.json()


def make_ticket(client, headers, customer_id: str, **overrides) -> dict:
    payload = {"customer_id": customer_id, "category": "network_issue", "priority": "high",
               "subject": "No signal", "description": "Cannot connect."}
    payload.update(overrides)
    r = client.post(f"{API}/tickets", headers=headers, json=payload)
    assert r.status_code == 201, r.text
    return r.json()


def make_technician(client, headers, **overrides) -> dict:
    payload = {"full_name": f"Tech {uniq()}", "phone": "+919800000000", "skills": "fibre", "service_area": "Chennai"}
    payload.update(overrides)
    r = client.post(f"{API}/technicians", headers=headers, json=payload)
    assert r.status_code == 201, r.text
    return r.json()


def error_code(response) -> str:
    return response.json()["error"]["code"]
