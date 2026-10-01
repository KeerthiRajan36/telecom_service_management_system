# Telecom Service & Network Management System

A backend platform for managing telecom customers, service plans, SIM cards, devices,
subscriptions, network infrastructure, outages, support tickets, SLAs, and operational
analytics — built with FastAPI, SQLAlchemy, and PostgreSQL.

**Status:** all 21 levels of the spec are implemented with working business logic (not stubs),
269 tests passing at 99% coverage, verified against both SQLite and PostgreSQL. See
[What's simplified](#whats-simplified-honestly) for the handful of things that are intentionally
lighter-weight than a real production system would need.

## Contents

- [Quick start](#quick-start) — Docker Compose, or run locally
- [Architecture](#architecture)
- [Authentication & roles](#authentication--roles)
- [Key design decisions](#key-design-decisions) — worth reading before diving into the code
- [Testing](#testing)
- [Generated docs](#generated-docs--keeping-them-honest) — ER diagram, OpenAPI, Postman
- [Database migrations](#database-migrations)
- [Project structure](#project-structure)
- [What's simplified](#whats-simplified-honestly)

## Quick start

### Option A — Docker Compose (recommended)

```bash
cp .env.example .env          # defaults work as-is for local use
docker compose up --build
```

This starts PostgreSQL and the API. On first boot the entrypoint runs `alembic upgrade head`
then seeds the Super Admin account and the default SLA rule matrix. Once healthy:

- Swagger UI: http://localhost:8000/docs
- ReDoc: http://localhost:8000/redoc
- Health check: http://localhost:8000/health
- Login: `admin@example.com` / `Admin@12345` (change `ADMIN_PASSWORD` in `.env` before any
  real deployment — the app refuses to start in `ENV=production` with the default password,
  a placeholder `SECRET_KEY`, or `DEBUG=true`)

### Option B — run locally (SQLite, zero setup)

```bash
python -m venv venv && source venv/bin/activate   # Windows: venv\Scripts\activate
pip install -r requirements.txt
python -m scripts.seed                             # creates tables, Super Admin, SLA rules
uvicorn app.main:app --reload
```

`DATABASE_URL` defaults to `sqlite:///./telecom.db`. Point it at Postgres/MySQL by setting
the env var (see `.env.example`) — every service and migration is written to be
database-agnostic.

### Run the mandatory end-to-end demo

With the server running:

```bash
python -m scripts.demo_flow --base-url http://localhost:8000
```

This walks the full mandated flow — admin login → customer → plan → SIM → device →
subscription → usage → tower → outage → affected-customer detection → ticket → agent/technician
assignment → SLA tracking → resolution → network restoration → notifications → dashboard →
reports → audit logs — printing each step's result. The same function is also run as an
automated test (`tests/integration/test_e2e_demo.py`) and is the source of the
`docs/postman_collection.json` demo folder, so all three stay in sync automatically.

## Architecture

```
Client → FastAPI routers (app/api/v1) → Services (app/services) → SQLAlchemy models (app/models) → DB
                ↓                              ↓
         Pydantic schemas              Background jobs (app/workers) for notifications
```

- **Routers** (`app/api/v1/`) handle HTTP concerns only: parsing, auth dependencies, status
  codes. All business logic lives in **services** (`app/services/`), which routers call and
  which are directly unit/integration-testable without spinning up HTTP.
- **Models** (`app/models/`) are SQLAlchemy 2.0 declarative classes, one or a few per domain
  file, plus `app/models/enums.py` for every status/type enum used across the schema.
- **Schemas** (`app/schemas/`) are Pydantic request/response models — kept separate from ORM
  models so the API contract can evolve independently of storage.
- Every state-changing service call writes to `AuditLog` via `app/utils/audit_logger.py`
  (Level 19), and most raise domain-specific errors (`AppError` subclasses in
  `app/core/exceptions.py`) that a global handler turns into a consistent JSON envelope:
  `{"error": {"code": ..., "message": ..., "details": ...}}`.

## Authentication & roles

JWT access + refresh tokens (`app/core/security.py`), refresh tokens are stored server-side
(`RefreshToken` table) so **logout actually revokes** them rather than just discarding the
client's copy. Roles: `super_admin`, `ops_manager`, `support_agent`, `network_engineer`,
`field_technician`, `customer`.

- `POST /api/v1/auth/register` is public but **always** creates a `customer` account — it
  ignores any role the caller tries to supply, so there's no privilege-escalation path through
  self-registration (see `tests/integration/test_auth.py::test_register_cannot_self_assign_privileged_role`).
- Staff accounts (and customer logins linked to a specific `Customer` profile) are created via
  `POST /api/v1/auth/users`, **Super Admin only**.
- Customers are scoped to their own data everywhere: their own profile, SIMs, devices,
  subscriptions, usage, tickets (including comments — internal notes are hidden from them),
  and service requests. This is enforced server-side (`app/core/deps.py::assert_customer_access`
  and per-router checks), not just hidden in the UI — see `tests/integration/test_rbac.py` for
  the full isolation matrix, including confirmation that a spoofed `customer_id` query
  parameter is ignored.
- Every other endpoint uses role-bundle dependencies (`require_staff`, `require_admin_or_ops`,
  `require_network_staff`, ...) — see `app/core/deps.py` for the exact bundles and
  `test_rbac.py` for the parametrized "who can do X" matrix.

## Key design decisions

A few choices that aren't obvious from skimming the code, worth knowing before you dig in:

- **Tower/SIM service mapping drives automatic outage impact.** The spec asks outages to
  "automatically identify affected customers based on tower/service mapping." Each active SIM
  has a `serving_tower_id`; creating an outage against a tower auto-derives every customer with
  an active SIM on that tower (deduplicated, multiple SIMs per customer counted once) and
  fires a background notification. See `app/services/outage_service.py::_identify_affected_customers`.
- **Outages actually move tower status.** An unplanned outage takes its towers `OFFLINE`; a
  planned one puts them into `MAINTENANCE`. Resolving an outage restores a tower to `ACTIVE`
  **only if no other unresolved outage still covers it** — overlapping outages on the same
  tower don't fight each other.
- **SLA rules are looked up by (ticket category × priority × customer type)** at ticket-creation
  time; if no matching rule exists, the ticket is created without SLA tracking rather than
  failing (a missing rule shouldn't block support). The seed script populates the full
  cartesian product (7 categories × 4 priorities × 3 customer types = 84 rules) as sensible
  defaults.
- **State machines reject no-op transitions**, not just illegal ones (e.g. suspending an
  already-suspended subscription is a 409, not a silent success) — this keeps history tables
  meaningful instead of accumulating misleading duplicate entries.
- **Soft delete for customers, hard delete nowhere for users.** Customers are soft-deleted
  (`is_deleted`/`deleted_at`) so plans, subscriptions, and tickets keep valid references. There
  is intentionally no "delete a user" endpoint — accounts are activated/deactivated per the
  spec — but the schema still behaves sensibly if a user row is ever purged directly: their own
  refresh/reset tokens cascade away, while `audit_logs.user_id` deliberately has **no** cascade,
  so a user's audit trail can never be silently erased by removing their account (see the last
  two tests in `tests/integration/test_auth.py`).
- **SQLite foreign keys are explicitly turned on** (`app/db/session.py`). SQLite ignores FK
  constraints and `ON DELETE` behavior by default; without the `PRAGMA foreign_keys=ON`
  connect-event, local/dev/test runs on SQLite could silently allow states that Postgres would
  correctly reject in production. This was caught by running the full suite against real
  Postgres partway through development (see the git-style history of the test file for the
  bug it caught).
- **Datetimes are always timezone-aware UTC**, enforced by a custom `UTCDateTime` type
  (`app/db/types.py`) rather than relying on each database driver's own behavior — SQLite
  silently drops tzinfo on read, Postgres keeps it; the custom type normalizes both ways so
  application code can always safely compare against `datetime.now(timezone.utc)`.
- **The rate limiter is in-process** (`app/middleware/rate_limit.py`), a sliding window keyed by
  client IP. It's genuinely enforced (tested), but with multiple API replicas each process has
  its own counter — swap for a Redis-backed limiter behind a load balancer for horizontal
  scaling (noted again in [What's simplified](#whats-simplified-honestly)).
- **Background jobs are plain functions, not a task queue** — `app/workers/jobs.py` holds
  idempotent jobs (subscription auto-renewal/expiry, plan-expiry warnings, maintenance-schedule
  notices, SLA-breach flagging) callable via `POST /api/v1/ops/run-jobs` (admin/ops) or wired
  into cron/Celery beat/APScheduler in front of `run_all_jobs(db)`. Usage-threshold checks
  (80%/100% of quota) run as a `BackgroundTasks` callback right after usage is recorded. All are
  de-duplicated (checking for an existing matching notification) so running them on a tight
  schedule never spams customers.

## Testing

```bash
pip install -r requirements-dev.txt
pytest                                    # SQLite, ~45s
pytest --cov=app --cov-report=term-missing   # with coverage

# Against real PostgreSQL instead:
TEST_DATABASE_URL=postgresql+psycopg2://telecom:telecom_pw@localhost:5432/telecom_test pytest
```

269 tests, 99% line coverage (3,558 statements / 29 missed, almost entirely repetitive 404
branches already covered by an equivalent test elsewhere). Breakdown:

| File | Covers |
|---|---|
| `test_auth.py` | Registration (incl. the anti-privilege-escalation regression), login, refresh/logout/revocation, password reset & change, activation, token expiry, user-deletion cascade semantics |
| `test_rbac.py` | Full role-permission matrix; customer data isolation across every resource type |
| `test_customers_plans.py` | Customer CRUD/KYC/search/filter/pagination/soft-delete, plan CRUD/comparison |
| `test_sims_devices_subscriptions.py` | SIM/subscription state machines, IMEI/SIM-mapping guards, usage % & quota math |
| `test_network_outages.py` | Towers, equipment heartbeats, outage auto-affected-customer detection, tower status transitions, technician assignment/reassignment/workload |
| `test_tickets_sla.py` | Ticket lifecycle, SLA deadline computation & breach detection, service requests |
| `test_workers_notifications.py` | Every scheduled job, usage-threshold alerting, notification inbox |
| `test_validation_and_database.py` | Error envelope consistency, SQL-injection inertness, DB indexes/constraints exist and are enforced, dashboard/report correctness |
| `test_generated_docs.py` | The ER diagram, OpenAPI spec, and Postman collection are internally consistent **and the Postman demo flow is actually executed** against a live test server |
| `test_e2e_demo.py` | The mandatory end-to-end flow, run as a real test |

Tests favor real business-rule assertions over "does it return 200": state machines are tested
for illegal *and* redundant transitions, ownership checks are tested with a second customer's
data (not just "no token"), and several tests were written specifically to catch bugs that were
found and fixed during development (see inline comments referencing what they regression-test).

## Generated docs & keeping them honest

`python -m scripts.generate_docs` regenerates all submission artifacts **from the running code**,
so they can't drift from what the API actually does:

- `docs/ER_DIAGRAM.md` — Mermaid ER diagram built from live SQLAlchemy metadata
- `docs/openapi.json` — the exact spec served at `/docs`
- `docs/API_REFERENCE.md` — endpoint table grouped by tag
- `docs/postman_collection.json` — every endpoint, plus a `00 - End-to-End Demo Flow` folder
  that runs the mandated scenario in order using Postman's own variable-chaining (each request
  saves the ids the next one needs). This exact flow is executed against a live test server in
  `test_generated_docs.py::test_postman_demo_steps_actually_run_against_the_api` — the collection
  isn't just schema-valid, it's proven to work.

Import `docs/postman_collection.json` into Postman, set `baseUrl` if not running on
`localhost:8000`, and run the demo folder with the Collection Runner.

## Database migrations

Alembic is wired to `app.models` and `DATABASE_URL`, so `alembic revision --autogenerate` always
reflects the current models regardless of dialect.

```bash
alembic upgrade head        # apply
alembic revision --autogenerate -m "description"   # after changing models
alembic check                                       # verify no drift between models and migrations
```

The single initial migration (`alembic/versions/0001_initial_schema.py`) creates all 28
tables. It's been verified to apply cleanly, round-trip (`upgrade` → `downgrade` →
`upgrade` again), and pass `alembic check` with zero drift on **both** SQLite and PostgreSQL 16
— including PostgreSQL-specific cleanup of the 27 ENUM types on downgrade, which Postgres
(unlike SQLite/MySQL) tracks as separate objects that `DROP TABLE` alone doesn't remove.

## Project structure

```
app/
├── api/v1/          One router file per domain (auth, customers, plans, sims, ...)
├── core/            config, JWT/password security, RBAC deps, global exception handling
├── models/          SQLAlchemy models, one/few per domain file, + enums.py
├── schemas/         Pydantic request/response models
├── services/        Business logic — the layer routers call and tests exercise directly
├── middleware/      Rate limiting, request logging
├── utils/           Pagination, audit logging, code generation
├── workers/         Scheduled/background jobs (Level 16 notifications, expiry, SLA scanning)
├── db/              Engine/session, declarative base + mixins, the UTCDateTime type
└── main.py          App wiring: middleware, exception handlers, health check

alembic/             Migrations (env.py reads DATABASE_URL from app settings — no hardcoded URL)
scripts/
├── seed.py                First Super Admin + default SLA rule matrix
├── demo_flow.py            The mandatory end-to-end demo (also used as a test and to build the Postman demo folder)
└── generate_docs.py        Regenerates docs/ from the live app
tests/
├── unit/            Pure-function tests: security, config validation, helpers, generated-docs consistency
└── integration/     Full-stack tests through the real API + database
docs/                Generated: ER diagram, OpenAPI spec, API reference, Postman collection
```

## What's simplified (honestly)

Being upfront about where this diverges from a fully hardened production system:

- **Rate limiting is per-process**, not distributed (see above) — fine for a single instance or
  behind a load balancer with sticky sessions; add Redis for real horizontal scaling.
- **No Celery/Redis** — background jobs are plain idempotent functions (`app/workers/jobs.py`)
  runnable via an admin endpoint or any external scheduler. This was a deliberate call to avoid
  adding infrastructure the project doesn't strictly need; swapping in Celery means wrapping
  each existing function as a `@task`, since they're already side-effect-isolated.
  Reports also aggregate in Python rather than SQL `GROUP BY`, which is simpler and fully
  dialect-portable (works identically on SQLite/Postgres/MySQL) but would need revisiting at
  very large table sizes.
- **No email/SMS delivery** — `Notification` rows are created (and are what the tests assert
  against) but nothing pushes them out; wire a provider into `app/services/notification_service.py`.
- **No WebSocket live outage feed, CSV/Excel export, or Prometheus metrics** — all listed as
  *bonus* features in the spec and not implemented; the `/health` endpoint covers basic
  liveness/readiness.
- **CI runs tests + a Docker build**, not a full deploy pipeline — see `.github/workflows/ci.yml`.

Everything in the 21 numbered levels of the spec — including the full mandatory end-to-end
demo flow — is implemented with real logic and tested, not stubbed.
