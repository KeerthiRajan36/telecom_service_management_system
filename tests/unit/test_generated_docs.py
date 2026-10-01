"""The submission artifacts (Postman collection, ER diagram, OpenAPI) are generated from code; these tests keep them honest."""
import json
import random
import re
import time
from datetime import date, datetime, timezone

import pytest

from scripts import generate_docs as gd

VAR = re.compile(r"\{\{([^}]+)\}\}")
BASE_VARS = {"baseUrl", "admin_email", "admin_password", "access_token", "refresh_token"}


@pytest.fixture(scope="module")
def spec():
    return gd.build_openapi()


@pytest.fixture(scope="module")
def collection(spec):
    return gd.build_postman(spec)


def _requests(collection):
    for folder in collection["item"]:
        for item in folder["item"]:
            yield folder["name"], item


def _template_path(item) -> str:
    """Postman ':id' path -> OpenAPI '{id}' template. Includes the /api/v1 prefix,
    since that's how `_url()` builds the segments (see generate_docs.py)."""
    parts = [p for p in item["request"]["url"]["path"]]
    return "/" + "/".join("{" + p[1:] + "}" if p.startswith(":") else p for p in parts)


def test_collection_is_valid_json_with_auth_and_variables(collection):
    json.loads(json.dumps(collection))
    assert collection["auth"]["type"] == "bearer" and "{{access_token}}" in json.dumps(collection["auth"])
    assert BASE_VARS <= {v["key"] for v in collection["variable"]}
    assert collection["item"][0]["name"].startswith("00")


def test_every_request_maps_to_a_real_openapi_operation(collection, spec):
    checked = 0
    for _, item in _requests(collection):
        full, method = _template_path(item), item["request"]["method"].lower()
        assert full in spec["paths"] and method in spec["paths"][full], f"{method.upper()} {full} not in OpenAPI"
        checked += 1
    # Every /api/v1 operation gets one request, plus the ordered demo-flow steps (which reuse some of the same operations).
    n_api_ops = sum(len(ops) for p, ops in spec["paths"].items() if p.startswith("/api/v1"))
    assert checked == n_api_ops + len(gd.DEMO_STEPS)


def test_collection_covers_every_openapi_operation(collection, spec):
    in_collection = {(item["request"]["method"].lower(), _template_path(item)) for name, item in _requests(collection) if not name.startswith("00")}
    in_spec = {(m, p) for p, ops in spec["paths"].items() if p.startswith("/api/v1") for m in ops}
    assert in_spec == in_collection, (
        f"missing from Postman: {sorted(in_spec - in_collection)[:5]}; extra in Postman: {sorted(in_collection - in_spec)[:5]}")


def test_public_endpoints_disable_auth_and_protected_ones_inherit_it(collection):
    by_path = {(_template_path(i), i["request"]["method"]): i for n, i in _requests(collection) if not n.startswith("00")}
    assert by_path[("/api/v1/auth/login", "POST")]["request"]["auth"] == {"type": "noauth"}
    assert "auth" not in by_path[("/api/v1/customers", "GET")]["request"]


def test_demo_variables_are_always_defined_before_use(collection):
    known = set(BASE_VARS)
    for step, item in zip(gd.DEMO_STEPS, collection["item"][0]["item"]):
        text = json.dumps(item["request"])
        used = {v for v in VAR.findall(text) if not v.startswith("$")}
        assert used <= known | {"today"}, f"{step['name']} uses undefined {used - known}"
        if step.get("pre"):
            known.add("today")
        known |= set(step.get("save", {}))


def test_demo_covers_the_mandatory_flow_in_order():
    seq = [(s["method"], re.sub(r"\{[a-z_]+\}", "{}", s["path"])) for s in gd.DEMO_STEPS]
    required = [
        ("POST", "/auth/login"), ("POST", "/customers"), ("POST", "/plans"), ("POST", "/sims"), ("POST", "/devices"),
        ("POST", "/subscriptions"), ("POST", "/usage"), ("POST", "/towers"), ("POST", "/outages"),
        ("GET", "/outages/{}/affected-customers"), ("POST", "/tickets"), ("POST", "/tickets/{}/assign-agent"),
        ("POST", "/tickets/{}/assign-technician"), ("GET", "/sla/tickets/{}"), ("PATCH", "/tickets/{}/status"),
        ("POST", "/outages/{}/resolve"), ("GET", "/notifications/all"), ("GET", "/dashboard/operations"),
        ("GET", "/reports/sla-performance"), ("GET", "/audit-logs"),
    ]
    idx = -1
    for step in required:
        assert step in seq[idx + 1:], f"{step} missing or out of order in the demo flow"
        idx = seq.index(step, idx + 1)


def _sub(text: str, variables: dict) -> str:
    def repl(m):
        name = m.group(1)
        if name == "$timestamp":
            return str(int(time.time()))
        if name == "$randomInt":
            return str(random.randint(0, 999))
        if name == "$isoTimestamp":
            return datetime.now(timezone.utc).isoformat()
        return str(variables[name])
    return VAR.sub(repl, text)


def test_postman_demo_steps_actually_run_against_the_api(client, admin_headers):
    """A mini-Newman: substitutes variables, sends each demo request, applies the `save` mappings."""
    variables = {"admin_email": "admin@example.com", "admin_password": "Admin@12345"}
    headers = {}
    for step in gd.DEMO_STEPS:
        if step.get("pre"):
            variables["today"] = date.today().isoformat()
        path = "/api/v1" + _sub(re.sub(r"\{([a-z_]+)\}", lambda m: "{{" + m.group(1) + "}}", step["path"]), variables)
        kwargs = {}
        if step.get("form"):
            kwargs["data"] = {k: _sub(v, variables) for k, v in step["form"].items()}
        elif step.get("body") is not None:
            kwargs["json"] = json.loads(_sub(json.dumps(step["body"]), variables))
        if step.get("query"):
            kwargs["params"] = {q["key"]: _sub(q["value"], variables) for q in step["query"]}
        r = client.request(step["method"], path, headers=({} if step.get("noauth") else headers), **kwargs)
        assert 200 <= r.status_code < 300, f"{step['name']}: {r.status_code} {r.text[:200]}"
        body = r.json()
        if step.get("token"):
            headers = {"Authorization": f"Bearer {body['access_token']}"}
        for var, jpath in step.get("save", {}).items():
            node = body
            for part in jpath.split("."):
                node = node[int(part)] if part.isdigit() else node[part]
            variables[var] = node
    assert {"customer_id", "ticket_id", "outage_id", "assignment_id"} <= set(variables)


# --------------------------------------------------------------------------- ER diagram
def test_er_diagram_is_complete_and_consistent():
    import app.models  # noqa: F401
    from app.db.base_class import Base
    md = gd.build_er_diagram()
    body = md.split("```mermaid\n")[1].split("\n```")[0]
    assert body.startswith("erDiagram")
    entities = set(re.findall(r"^    (\w+) \{$", body, flags=re.M))
    assert entities == set(Base.metadata.tables)
    rels = re.findall(r'^    (\w+) [|o}{-]+ (\w+) : "(\w+)"$', body, flags=re.M)
    assert len(rels) >= 35
    assert all(a in entities and b in entities for a, b, _ in rels)
    assert all(re.fullmatch(r"\s{8}\w+ \w+( (PK|FK|UK)(,(PK|FK|UK))*)?", l) for l in re.findall(r"^\s{8}.*$", body, flags=re.M))
    assert 'tickets ||--o{ ticket_comments : "ticket_id"' in body   # a real one-to-many relationship is rendered correctly
    assert ('customers', 'users', 'customer_id') in rels           # the optional one-to-one User<->Customer link is captured


def test_openapi_operations_are_documented(spec):
    ops = [(p, m, o) for p, item in spec["paths"].items() for m, o in item.items()]
    assert len(ops) == 117 or len(ops) > 100
    assert all(o.get("tags") and o.get("summary") for _, _, o in ops)
