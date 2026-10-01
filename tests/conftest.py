"""
Test configuration.

Environment variables MUST be set before any `app.*` import, because settings
are read once at import time. Each test gets a freshly created SQLite schema
seeded with the Super Admin and default SLA rules.
"""
import os
import tempfile

_TMP_DIR = tempfile.mkdtemp(prefix="telecom_tests_")
# Set TEST_DATABASE_URL to run the whole suite against PostgreSQL/MySQL instead of the default SQLite file.
os.environ["DATABASE_URL"] = os.environ.get("TEST_DATABASE_URL") or f"sqlite:///{_TMP_DIR}/test.db"
os.environ["RATE_LIMIT_DEFAULT"] = "1000000/minute"
os.environ["ENV"] = "test"
os.environ["SECRET_KEY"] = "test-secret-key"

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from app.core import security  # noqa: E402
from app.db.base_class import Base  # noqa: E402
from app.db.session import engine, SessionLocal  # noqa: E402
from app.main import app as fastapi_app  # noqa: E402  (alias: `import app.models` would shadow `app`)
import app.models  # noqa: E402,F401
from scripts.seed import seed_admin, seed_sla_rules  # noqa: E402

import logging  # noqa: E402
for _name in ("httpx", "telecom.requests"):  # keep failure output readable
    logging.getLogger(_name).setLevel(logging.WARNING)

# Cheap bcrypt cost keeps the suite fast; production keeps the default.
security.pwd_context.update(bcrypt__rounds=4)

ADMIN_EMAIL = "admin@example.com"
ADMIN_PASSWORD = "Admin@12345"


@pytest.fixture()
def db():
    """Direct DB session for assertions / setup that bypass the API."""
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()


@pytest.fixture()
def client():
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    with SessionLocal() as session:
        seed_admin(session)
        seed_sla_rules(session)
    with TestClient(fastapi_app) as test_client:
        yield test_client


@pytest.fixture()
def admin_headers(client):
    from tests.factories import login
    return login(client, ADMIN_EMAIL, ADMIN_PASSWORD)


@pytest.fixture()
def staff(client, admin_headers):
    """Factory: staff('support_agent') -> (user_dict, auth_headers)."""
    from tests.factories import make_staff

    def _make(role: str):
        return make_staff(client, admin_headers, role)

    return _make
