"""
Generates submission artifacts straight from the code, so they can never drift from reality:

  docs/ER_DIAGRAM.md            Mermaid ER diagram built from the SQLAlchemy metadata
  docs/openapi.json             OpenAPI 3 spec (what Swagger UI serves at /docs)
  docs/API_REFERENCE.md         Endpoint table grouped by tag
  docs/postman_collection.json  Postman v2.1 collection: every endpoint + an ordered end-to-end demo folder

    python -m scripts.generate_docs
"""
import json
import pathlib
from collections import OrderedDict, defaultdict

DOCS = pathlib.Path("docs")
PREFIX = "/api/v1"


# ----------------------------------------------------------------------------- ER diagram
_TYPE_NAMES = {"VARCHAR": "varchar", "TEXT": "text", "INTEGER": "int", "FLOAT": "float", "BOOLEAN": "bool",
               "DATE": "date", "DATETIME": "datetime", "ENUM": "enum", "UTCDATETIME": "datetime"}


def _col_type(column) -> str:
    name = type(column.type).__name__.upper()
    return _TYPE_NAMES.get(name, name.lower())


def build_er_diagram() -> str:
    import app.models  # noqa: F401
    from app.db.base_class import Base

    lines = ["erDiagram"]
    tables = sorted(Base.metadata.tables.values(), key=lambda t: t.name)
    for table in tables:
        lines.append(f"    {table.name} {{")
        fk_cols = {fk.parent.name for fk in table.foreign_keys}
        for col in table.columns:
            keys = []
            if col.primary_key:
                keys.append("PK")
            if col.name in fk_cols:
                keys.append("FK")
            if col.unique and not col.primary_key:
                keys.append("UK")
            suffix = f" {','.join(keys)}" if keys else ""
            lines.append(f"        {_col_type(col)} {col.name}{suffix}")
        lines.append("    }")
    for table in tables:
        for fk in sorted(table.foreign_keys, key=lambda f: f.parent.name):
            parent = fk.column.table.name
            card = "|o--o{" if fk.parent.nullable else "||--o{"
            if fk.parent.unique or fk.parent.primary_key:
                card = "|o--o|" if fk.parent.nullable else "||--o|"
            lines.append(f'    {parent} {card} {table.name} : "{fk.parent.name}"')
    body = "\n".join(lines)
    return (
        "# Entity-Relationship Diagram\n\n"
        f"Generated from the SQLAlchemy models ({len(tables)} tables). "
        "PK = primary key, FK = foreign key, UK = unique. "
        "`||--o{` = one-to-many, `|o--o{` = optional one-to-many, `|o--o|` = optional one-to-one.\n\n"
        "```mermaid\n" + body + "\n```\n"
    )


# ----------------------------------------------------------------------------- OpenAPI / reference
def build_openapi() -> dict:
    from app.main import app
    return app.openapi()


def build_api_reference(spec: dict) -> str:
    by_tag = defaultdict(list)
    for path, ops in spec["paths"].items():
        for method, op in ops.items():
            by_tag[(op.get("tags") or ["Other"])[0]].append((path, method.upper(), op.get("summary", "")))
    total = sum(len(v) for v in by_tag.values())
    out = [f"# API Reference\n\n{total} endpoints. Interactive docs: `/docs` (Swagger UI) and `/redoc`. "
           "Endpoints marked 🔒 need a Bearer token.\n"]
    for tag in sorted(by_tag):
        out.append(f"\n## {tag}\n\n| Method | Path | Summary | Auth |\n|---|---|---|---|")
        for path, method, summary in sorted(by_tag[tag]):
            op = spec["paths"][path][method.lower()]
            locked = "🔒" if op.get("security") else "public"
            out.append(f"| `{method}` | `{path}` | {summary} | {locked} |")
    return "\n".join(out) + "\n"


# ----------------------------------------------------------------------------- Postman
def _resolve(schema: dict, spec: dict) -> dict:
    while "$ref" in schema:
        node = spec
        for part in schema["$ref"].lstrip("#/").split("/"):
            node = node[part]
        schema = node
    return schema


def example_for(schema: dict, spec: dict, depth: int = 0):
    """Builds a plausible example value from a JSON schema."""
    schema = _resolve(schema, spec)
    if "example" in schema:
        return schema["example"]
    if "default" in schema and schema["default"] is not None:
        return schema["default"]
    for key in ("anyOf", "oneOf"):
        if key in schema:
            options = [s for s in schema[key] if s.get("type") != "null"]
            return example_for(options[0], spec, depth) if options else None
    if "allOf" in schema:
        return example_for(schema["allOf"][0], spec, depth)
    if "enum" in schema:
        return schema["enum"][0]
    t, fmt = schema.get("type"), schema.get("format")
    if t == "object" or "properties" in schema:
        if depth > 3:
            return {}
        required = set(schema.get("required", []))
        return {k: example_for(v, spec, depth + 1) for k, v in schema.get("properties", {}).items()
                if k in required or depth == 0}
    if t == "array":
        return [example_for(schema.get("items", {}), spec, depth + 1)]
    if t == "string":
        return {"email": "user@example.com", "date": "2026-01-01", "date-time": "2026-01-01T10:00:00Z"}.get(fmt, "string")
    if t == "integer":
        return schema.get("minimum", 1) if schema.get("minimum", 0) > 0 else 1
    if t == "number":
        return 1.5
    if t == "boolean":
        return False
    return None


_NOAUTH = {"/auth/login", "/auth/register", "/auth/refresh", "/auth/logout",
           "/auth/password-reset/request", "/auth/password-reset/confirm"}
_TOKEN_SCRIPT = [
    "const j = pm.response.json();",
    "pm.collectionVariables.set('access_token', j.access_token);",
    "if (j.refresh_token) pm.collectionVariables.set('refresh_token', j.refresh_token);",
]


def _url(path: str, query=None) -> dict:
    full = PREFIX + path
    segments = [s for s in full.split("/") if s]
    variables = []
    parts = []
    for seg in segments:
        if seg.startswith("{") and seg.endswith("}"):
            name = seg[1:-1]
            parts.append(f":{name}")
            variables.append({"key": name, "value": f"{{{{{name}}}}}" if name in _KNOWN_IDS else "REPLACE_ME"})
        else:
            parts.append(seg)
    url = {"raw": "{{baseUrl}}/" + "/".join(parts), "host": ["{{baseUrl}}"], "path": parts}
    if variables:
        url["variable"] = variables
    if query:
        url["query"] = query
        url["raw"] += "?" + "&".join(f"{q['key']}={q['value']}" for q in query if not q.get("disabled"))
    return url


_KNOWN_IDS = {"customer_id", "plan_id", "sim_id", "device_id", "subscription_id", "tower_id", "outage_id",
              "ticket_id", "technician_id", "assignment_id"}


def _json_body(data) -> dict:
    return {"mode": "raw", "raw": json.dumps(data, indent=2), "options": {"raw": {"language": "json"}}}


def _request(name, method, path, body=None, form=None, query=None, noauth=False, tests=None, pre=None, description=""):
    req = {"method": method, "header": [], "url": _url(path, query)}
    if description:
        req["description"] = description
    if form is not None:
        req["body"] = {"mode": "urlencoded", "urlencoded": [{"key": k, "value": v} for k, v in form.items()]}
    elif body is not None:
        req["header"].append({"key": "Content-Type", "value": "application/json"})
        req["body"] = _json_body(body)
    if noauth:
        req["auth"] = {"type": "noauth"}
    item = {"name": name, "request": req}
    events = []
    if pre:
        events.append({"listen": "prerequest", "script": {"type": "text/javascript", "exec": pre}})
    if tests:
        events.append({"listen": "test", "script": {"type": "text/javascript", "exec": tests}})
    if events:
        item["event"] = events
    return item


# Ordered end-to-end flow. `save` maps a collection variable -> JSON path in the response.
DEMO_STEPS = [
    dict(name="01 Admin login", method="POST", path="/auth/login", noauth=True,
         form={"username": "{{admin_email}}", "password": "{{admin_password}}"}, token=True),
    dict(name="02 Create customer", method="POST", path="/customers", save={"customer_id": "id"},
         body={"full_name": "Asha Raman", "email": "asha.{{$timestamp}}@example.com", "phone": "+91{{$timestamp}}",
               "customer_type": "postpaid", "address": {"line1": "12 Marina Road", "city": "Chennai", "state": "Tamil Nadu",
                                                        "postal_code": "600001", "is_primary": True}}),
    dict(name="03 Verify KYC", method="PATCH", path="/customers/{customer_id}/kyc", body={"kyc_status": "verified"}),
    dict(name="04 Create plan", method="POST", path="/plans", save={"plan_id": "id"},
         body={"name": "Postpaid Combo 499", "code": "PLN-{{$timestamp}}", "plan_type": "postpaid", "category": "combo",
               "price": 499, "validity_days": 30, "data_limit_mb": 10000, "voice_limit_minutes": 1000, "sms_limit_count": 500}),
    dict(name="05 Register SIM", method="POST", path="/sims", save={"sim_id": "id"},
         body={"sim_number": "8991{{$timestamp}}", "sim_type": "physical"}),
    dict(name="06 Map SIM to customer", method="POST", path="/sims/{sim_id}/assign-customer", body={"customer_id": "{{customer_id}}"}),
    dict(name="07 Register device", method="POST", path="/devices", save={"device_id": "id"},
         body={"imei": "{{$timestamp}}{{$randomInt}}", "model": "Galaxy S24", "manufacturer": "Samsung",
               "device_type": "smartphone", "customer_id": "{{customer_id}}", "sim_id": "{{sim_id}}"}),
    dict(name="08 Activate subscription", method="POST", path="/subscriptions", save={"subscription_id": "id"},
         body={"customer_id": "{{customer_id}}", "sim_id": "{{sim_id}}", "plan_id": "{{plan_id}}"}),
    dict(name="09 Generate usage", method="POST", path="/usage",
         pre=["pm.collectionVariables.set('today', new Date().toISOString().slice(0, 10));"],
         body={"subscription_id": "{{subscription_id}}", "usage_date": "{{today}}", "data_used_mb": 2500,
               "voice_used_minutes": 120, "sms_used_count": 40}),
    dict(name="10 Usage summary", method="GET", path="/usage/subscriptions/{subscription_id}/summary",
         extra_tests=["pm.test('25% of data used', () => pm.expect(pm.response.json().data_usage_percent).to.eql(25));"]),
    dict(name="11 Register tower", method="POST", path="/towers", save={"tower_id": "id"},
         body={"code": "TWR-{{$timestamp}}", "name": "Marina Beach Tower", "tower_type": "macro", "latitude": 13.05,
               "longitude": 80.2824, "coverage_radius_km": 6, "capacity": 5000}),
    dict(name="12 Map SIM to tower", method="POST", path="/sims/{sim_id}/assign-tower", body={"tower_id": "{{tower_id}}"}),
    dict(name="13 Create outage", method="POST", path="/outages", save={"outage_id": "id"},
         body={"title": "Fibre cut near Marina", "description": "Backhaul link down", "outage_type": "unplanned",
               "severity": "high", "tower_ids": ["{{tower_id}}"], "start_time": "{{$isoTimestamp}}"}),
    dict(name="14 Affected customers", method="GET", path="/outages/{outage_id}/affected-customers",
         extra_tests=["pm.test('customer auto-identified', () => pm.expect(pm.response.json().map(a => a.customer_id)).to.include(pm.collectionVariables.get('customer_id')));"]),
    dict(name="15 Create ticket", method="POST", path="/tickets", save={"ticket_id": "id"},
         body={"customer_id": "{{customer_id}}", "category": "network_issue", "priority": "high",
               "subject": "No signal since morning", "description": "Phone shows no service near Marina.",
               "related_sim_id": "{{sim_id}}", "related_device_id": "{{device_id}}"}),
    dict(name="16 Create support agent", method="POST", path="/auth/users", save={"agent_id": "id"},
         body={"email": "agent.{{$timestamp}}@example.com", "full_name": "Priya Agent", "password": "Agent@12345", "role": "support_agent"}),
    dict(name="17 Assign agent", method="POST", path="/tickets/{ticket_id}/assign-agent", body={"agent_id": "{{agent_id}}"}),
    dict(name="18 Create technician", method="POST", path="/technicians", save={"technician_id": "id"},
         body={"full_name": "Karthik Tech", "phone": "+919800000001", "skills": "fibre,rf", "service_area": "Chennai Central"}),
    dict(name="19 Assign technician", method="POST", path="/tickets/{ticket_id}/assign-technician", body={"technician_id": "{{technician_id}}"}),
    dict(name="20 Track SLA", method="GET", path="/sla/tickets/{ticket_id}"),
    dict(name="21 Tickets soon to breach", method="GET", path="/sla/soon-to-breach", query=[{"key": "within_minutes", "value": "100000"}]),
    dict(name="22 Ticket -> in progress", method="PATCH", path="/tickets/{ticket_id}/status", body={"status": "in_progress"}),
    dict(name="23 Internal comment", method="POST", path="/tickets/{ticket_id}/comments",
         body={"body": "Fibre cut confirmed at backhaul.", "is_internal": True}),
    dict(name="24 Resolve ticket", method="PATCH", path="/tickets/{ticket_id}/status",
         body={"status": "resolved", "resolution_notes": "Backhaul restored by field team."}),
    dict(name="25 Technician's jobs", method="GET", path="/technicians/{technician_id}/assignments", save={"assignment_id": "0.id"}),
    dict(name="26 Complete assignment", method="POST", path="/technicians/assignments/{assignment_id}/complete"),
    dict(name="27 Outage -> in progress", method="POST", path="/outages/{outage_id}/in-progress"),
    dict(name="28 Restore network (resolve outage)", method="POST", path="/outages/{outage_id}/resolve", body={}),
    dict(name="29 Notifications generated", method="GET", path="/notifications/all", query=[{"key": "customer_id", "value": "{{customer_id}}"}]),
    dict(name="30 Operations dashboard", method="GET", path="/dashboard/operations"),
    dict(name="31 Report: SLA performance", method="GET", path="/reports/sla-performance"),
    dict(name="32 Report: plan popularity", method="GET", path="/reports/plan-popularity"),
    dict(name="33 Report: network uptime", method="GET", path="/reports/network-uptime"),
    dict(name="34 Verify audit logs", method="GET", path="/audit-logs", query=[{"key": "page_size", "value": "100"}]),
]


def _demo_item(step: dict) -> dict:
    tests = ["pm.test('status is 2xx', () => pm.expect(pm.response.code).to.be.within(200, 299));"]
    if step.get("token"):
        tests += _TOKEN_SCRIPT
    if step.get("save"):
        tests.append("const body = pm.response.json();")
        for var, path in step["save"].items():
            accessor = f"body[{path.split('.')[0]}].{path.split('.', 1)[1]}" if path[0].isdigit() else f"body.{path}"
            tests.append(f"pm.collectionVariables.set('{var}', {accessor});")
    tests += step.get("extra_tests", [])
    return _request(step["name"], step["method"], step["path"], body=step.get("body"), form=step.get("form"),
                    query=step.get("query"), noauth=step.get("noauth", False), tests=tests, pre=step.get("pre"))


def build_postman(spec: dict) -> dict:
    folders: "OrderedDict[str, list]" = OrderedDict()
    for path, ops in spec["paths"].items():
        if not path.startswith(PREFIX):
            continue
        short = path[len(PREFIX):]
        for method, op in ops.items():
            tag = (op.get("tags") or ["Other"])[0]
            body = form = None
            rb = op.get("requestBody", {}).get("content", {})
            if "application/json" in rb:
                body = example_for(rb["application/json"]["schema"], spec)
            elif "application/x-www-form-urlencoded" in rb:
                form = {"username": "{{admin_email}}", "password": "{{admin_password}}"}
            query = [{"key": p["name"], "value": str(example_for(p.get("schema", {}), spec) or ""), "disabled": True}
                     for p in op.get("parameters", []) if p["in"] == "query" and p["name"] not in ("page", "page_size", "sort_by", "sort_order", "search")]
            query += [{"key": "page", "value": "1", "disabled": True}, {"key": "page_size", "value": "20", "disabled": True}] \
                if any(p["name"] == "page_size" for p in op.get("parameters", [])) else []
            if short == "/auth/refresh" or short == "/auth/logout":
                body = {"refresh_token": "{{refresh_token}}"}
            tests = list(_TOKEN_SCRIPT) if short == "/auth/login" else (
                ["const j = pm.response.json();", "pm.collectionVariables.set('access_token', j.access_token);"] if short == "/auth/refresh" else None)
            folders.setdefault(tag, []).append(_request(
                op.get("summary", f"{method.upper()} {short}"), method.upper(), short, body=body, form=form, query=query or None,
                noauth=short in _NOAUTH, tests=tests, description=(op.get("description") or "").split("\n\n")[0]))
    reference = [{"name": tag, "item": items} for tag, items in sorted(folders.items())]
    return {
        "info": {"name": "Telecom Service & Network Management System", "schema": "https://schema.getpostman.com/json/collection/v2.1.0/collection.json",
                 "description": "Folder '00 - End-to-End Demo Flow' runs the mandatory scenario in order (use the Collection Runner); "
                                "each request stores the ids the next one needs. The other folders contain every endpoint."},
        "auth": {"type": "bearer", "bearer": [{"key": "token", "value": "{{access_token}}", "type": "string"}]},
        "variable": [{"key": "baseUrl", "value": "http://localhost:8000"}, {"key": "admin_email", "value": "admin@example.com"},
                     {"key": "admin_password", "value": "Admin@12345"}, {"key": "access_token", "value": ""},
                     {"key": "refresh_token", "value": ""}],
        "item": [{"name": "00 - End-to-End Demo Flow", "item": [_demo_item(s) for s in DEMO_STEPS]}] + reference,
    }


def main() -> None:
    DOCS.mkdir(exist_ok=True)
    spec = build_openapi()
    (DOCS / "ER_DIAGRAM.md").write_text(build_er_diagram())
    (DOCS / "openapi.json").write_text(json.dumps(spec, indent=2))
    (DOCS / "API_REFERENCE.md").write_text(build_api_reference(spec))
    collection = build_postman(spec)
    (DOCS / "postman_collection.json").write_text(json.dumps(collection, indent=2))
    n_ops = sum(len(v) for v in spec["paths"].values())
    print(f"docs/ written: ER diagram, openapi.json ({n_ops} operations), API_REFERENCE.md, "
          f"postman_collection.json ({len(DEMO_STEPS)} demo steps + {n_ops} endpoint requests)")


if __name__ == "__main__":
    main()
