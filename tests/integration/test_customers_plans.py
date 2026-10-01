from tests.factories import API, error_code, make_customer, make_plan, uniq


# --------------------------------------------------------------------- customers
def test_create_customer_with_address_and_generated_code(client, admin_headers):
    c = make_customer(client, admin_headers, address={
        "line1": "1 Beach Rd", "city": "Chennai", "state": "TN", "postal_code": "600001", "is_primary": True})
    assert c["customer_code"].startswith("CUST-") and c["kyc_status"] == "pending" and c["is_active"] is True
    assert len(c["addresses"]) == 1 and c["addresses"][0]["is_primary"] is True


def test_duplicate_email_or_phone_rejected(client, admin_headers):
    c = make_customer(client, admin_headers)
    base = {"full_name": "Dup", "email": f"d.{uniq()}@example.com", "phone": f"+91{uniq()}"}
    r = client.post(f"{API}/customers", headers=admin_headers, json={**base, "email": c["email"]})
    assert r.status_code == 409 and error_code(r) == "CUSTOMER_EXISTS"
    r = client.post(f"{API}/customers", headers=admin_headers, json={**base, "phone": c["phone"]})
    assert r.status_code == 409 and error_code(r) == "CUSTOMER_EXISTS"


def test_customer_validation(client, admin_headers):
    r = client.post(f"{API}/customers", headers=admin_headers, json={"full_name": "x", "email": "bad", "phone": "1"})
    assert r.status_code == 422
    r = client.post(f"{API}/customers", headers=admin_headers, json={"full_name": "x", "email": "a@example.com"})
    assert r.status_code == 422  # phone missing


def test_update_customer_and_conflicting_email(client, admin_headers):
    a, b = make_customer(client, admin_headers), make_customer(client, admin_headers)
    ok = client.patch(f"{API}/customers/{a['id']}", headers=admin_headers, json={"full_name": "Renamed"})
    assert ok.status_code == 200 and ok.json()["full_name"] == "Renamed"
    clash = client.patch(f"{API}/customers/{a['id']}", headers=admin_headers, json={"email": b["email"]})
    assert clash.status_code == 409  # DB unique constraint surfaces as a clean conflict, not a 500
    assert client.get(f"{API}/customers/{a['id']}", headers=admin_headers).json()["email"] == a["email"]


def test_list_search_filter_sort_and_paginate(client, admin_headers):
    names = ["Alpha Kumar", "Bravo Singh", "Charlie Rao", "Delta Iyer", "Echo Nair"]
    for i, n in enumerate(names):
        make_customer(client, admin_headers, full_name=n, customer_type="enterprise" if i == 0 else "prepaid")

    page1 = client.get(f"{API}/customers", headers=admin_headers, params={"page_size": 2, "sort_by": "full_name"}).json()
    assert page1["total"] == 5 and page1["pages"] == 3 and [i["full_name"] for i in page1["items"]] == names[:2]
    page3 = client.get(f"{API}/customers", headers=admin_headers, params={"page": 3, "page_size": 2, "sort_by": "full_name"}).json()
    assert [i["full_name"] for i in page3["items"]] == [names[4]]

    desc = client.get(f"{API}/customers", headers=admin_headers, params={"sort_by": "full_name", "sort_order": "desc"}).json()
    assert [i["full_name"] for i in desc["items"]] == names[::-1]

    found = client.get(f"{API}/customers", headers=admin_headers, params={"search": "charlie"}).json()
    assert found["total"] == 1 and found["items"][0]["full_name"] == "Charlie Rao"
    ent = client.get(f"{API}/customers", headers=admin_headers, params={"customer_type": "enterprise"}).json()
    assert ent["total"] == 1


def test_kyc_update_and_filter(client, admin_headers):
    a, _ = make_customer(client, admin_headers), make_customer(client, admin_headers)
    r = client.patch(f"{API}/customers/{a['id']}/kyc", headers=admin_headers,
                     json={"kyc_status": "verified", "kyc_document_type": "passport", "kyc_document_number": "P123"})
    assert r.json()["kyc_status"] == "verified"
    verified = client.get(f"{API}/customers", headers=admin_headers, params={"kyc_status": "verified"}).json()
    assert [c["id"] for c in verified["items"]] == [a["id"]]
    assert client.patch(f"{API}/customers/{a['id']}/kyc", headers=admin_headers, json={"kyc_status": "nonsense"}).status_code == 422


def test_activation_toggle_and_filter(client, admin_headers):
    a, b = make_customer(client, admin_headers), make_customer(client, admin_headers)
    r = client.patch(f"{API}/customers/{a['id']}/activation", headers=admin_headers, json={"is_active": False})
    assert r.json()["is_active"] is False
    inactive = client.get(f"{API}/customers", headers=admin_headers, params={"is_active": False}).json()
    assert [c["id"] for c in inactive["items"]] == [a["id"]]
    active = client.get(f"{API}/customers", headers=admin_headers, params={"is_active": True}).json()
    assert [c["id"] for c in active["items"]] == [b["id"]]


def test_primary_address_is_exclusive(client, admin_headers):
    c = make_customer(client, admin_headers)
    addr = {"line1": "x", "city": "c", "state": "s", "postal_code": "1"}
    client.post(f"{API}/customers/{c['id']}/addresses", headers=admin_headers, json={**addr, "is_primary": True})
    client.post(f"{API}/customers/{c['id']}/addresses", headers=admin_headers, json={**addr, "label": "office", "is_primary": True})
    addrs = client.get(f"{API}/customers/{c['id']}", headers=admin_headers).json()["addresses"]
    assert len(addrs) == 2 and sum(a["is_primary"] for a in addrs) == 1
    assert next(a for a in addrs if a["is_primary"])["label"] == "office"


def test_history_records_before_and_after_values(client, admin_headers):
    c = make_customer(client, admin_headers, full_name="Before Name")
    client.patch(f"{API}/customers/{c['id']}", headers=admin_headers, json={"full_name": "After Name"})
    client.patch(f"{API}/customers/{c['id']}/kyc", headers=admin_headers, json={"kyc_status": "verified"})
    history = client.get(f"{API}/customers/{c['id']}/history", headers=admin_headers).json()
    assert {h["action"] for h in history} >= {"CREATE", "UPDATE", "KYC_UPDATE"}
    update = next(h for h in history if h["action"] == "UPDATE")
    assert "Before Name" in update["previous_value"] and "After Name" in update["new_value"]
    assert all(h["user_id"] for h in history)


def test_soft_delete_hides_customer_but_keeps_row(client, admin_headers, db):
    from app.models.customer import Customer
    c = make_customer(client, admin_headers)
    assert client.delete(f"{API}/customers/{c['id']}", headers=admin_headers).status_code == 200
    assert client.get(f"{API}/customers/{c['id']}", headers=admin_headers).status_code == 404
    assert client.delete(f"{API}/customers/{c['id']}", headers=admin_headers).status_code == 404
    assert c["id"] not in [i["id"] for i in client.get(f"{API}/customers", headers=admin_headers).json()["items"]]
    row = db.get(Customer, c["id"])
    assert row is not None and row.is_deleted is True and row.deleted_at is not None
    assert client.get(f"{API}/audit-logs", headers=admin_headers, params={"entity": "Customer", "action": "DELETE"}).json()["total"] == 1


def test_soft_deleted_customer_cannot_receive_new_records(client, admin_headers):
    from tests.factories import make_sim
    c = make_customer(client, admin_headers)
    sim = make_sim(client, admin_headers)
    client.delete(f"{API}/customers/{c['id']}", headers=admin_headers)
    assert client.post(f"{API}/sims/{sim['id']}/assign-customer", headers=admin_headers, json={"customer_id": c["id"]}).status_code == 404
    assert client.post(f"{API}/tickets", headers=admin_headers, json={
        "customer_id": c["id"], "category": "sim_issue", "subject": "s", "description": "d"}).status_code == 404
    assert client.post(f"{API}/service-requests", headers=admin_headers,
                       json={"customer_id": c["id"], "request_type": "plan_change"}).status_code == 404


def test_unknown_customer_is_404_with_error_envelope(client, admin_headers):
    r = client.get(f"{API}/customers/nope", headers=admin_headers)
    assert r.status_code == 404 and error_code(r) == "NOT_FOUND"


# ------------------------------------------------------------------------- plans
def test_plan_creation_rules(client, admin_headers):
    p = make_plan(client, admin_headers, code="DUP-1")
    assert p["status"] == "active"
    dup = client.post(f"{API}/plans", headers=admin_headers, json={
        "name": "x", "code": "DUP-1", "plan_type": "prepaid", "category": "data", "price": 10, "validity_days": 1})
    assert dup.status_code == 409 and error_code(dup) == "PLAN_EXISTS"
    for bad in ({"price": 0}, {"price": -5}, {"validity_days": 0}, {"plan_type": "weekly"}, {"category": "video"}):
        body = {"name": "x", "code": f"C-{uniq()}", "plan_type": "prepaid", "category": "data", "price": 10, "validity_days": 1, **bad}
        assert client.post(f"{API}/plans", headers=admin_headers, json=body).status_code == 422, bad


def test_plan_filters_search_and_pagination(client, admin_headers):
    make_plan(client, admin_headers, name="Data Booster", plan_type="prepaid", category="data", price=99)
    make_plan(client, admin_headers, name="Talk Time", plan_type="prepaid", category="voice", price=49)
    make_plan(client, admin_headers, name="Family Pack", plan_type="postpaid", category="combo", price=799)
    make_plan(client, admin_headers, name="SMS Saver", plan_type="prepaid", category="sms", price=19)

    def names(**params):
        return sorted(p["name"] for p in client.get(f"{API}/plans", params=params).json()["items"])

    assert names(plan_type="postpaid") == ["Family Pack"]
    assert names(category="voice") == ["Talk Time"]
    assert names(min_price=50, max_price=800) == ["Data Booster", "Family Pack"]
    assert names(search="saver") == ["SMS Saver"]
    paged = client.get(f"{API}/plans", params={"page_size": 3, "sort_by": "price"}).json()
    assert paged["total"] == 4 and [p["price"] for p in paged["items"]] == [19, 49, 99]


def test_plan_update_and_activation_toggle(client, admin_headers):
    p = make_plan(client, admin_headers)
    u = client.patch(f"{API}/plans/{p['id']}", headers=admin_headers, json={"price": 599, "data_limit_mb": 20000})
    assert u.json()["price"] == 599 and u.json()["data_limit_mb"] == 20000
    off = client.patch(f"{API}/plans/{p['id']}/status", headers=admin_headers, params={"plan_status": "inactive"})
    assert off.json()["status"] == "inactive"
    listed = client.get(f"{API}/plans", params={"status": "inactive"}).json()
    assert [x["id"] for x in listed["items"]] == [p["id"]]
    hist = client.get(f"{API}/audit-logs", headers=admin_headers, params={"entity": "ServicePlan", "entity_id": p["id"]}).json()
    assert {"CREATE", "UPDATE", "STATUS_CHANGE"} <= {h["action"] for h in hist["items"]}


def test_plan_comparison(client, admin_headers):
    a, b, c = (make_plan(client, admin_headers, price=p) for p in (100, 200, 300))
    r = client.post(f"{API}/plans/compare", json={"plan_ids": [c["id"], a["id"], b["id"]]})
    assert r.status_code == 200 and [p["id"] for p in r.json()] == [c["id"], a["id"], b["id"]]  # requested order kept
    assert client.post(f"{API}/plans/compare", json={"plan_ids": [a["id"], "missing"]}).status_code == 404
    assert client.post(f"{API}/plans/compare", json={"plan_ids": [a["id"]]}).status_code == 422
    assert client.post(f"{API}/plans/compare", json={"plan_ids": [a["id"]] * 6}).status_code == 422
