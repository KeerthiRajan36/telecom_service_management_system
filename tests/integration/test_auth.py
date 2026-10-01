import pytest
import re

from tests.factories import API, PASSWORD, error_code, login, make_staff, uniq


def _register(client, email=None, **extra):
    email = email or f"user.{uniq()}@example.com"
    r = client.post(f"{API}/auth/register", json={"email": email, "full_name": "Test User", "password": PASSWORD, **extra})
    return email, r


def _tokens(client, email, password=PASSWORD):
    return client.post(f"{API}/auth/login", data={"username": email, "password": password})


def test_register_creates_customer_role_user(client):
    email, r = _register(client)
    assert r.status_code == 201
    body = r.json()
    assert body["email"] == email and body["role"] == "customer" and body["is_active"] is True
    assert "password" not in body and "hashed_password" not in body


def test_register_cannot_self_assign_privileged_role(client):
    """Regression: the public endpoint must ignore any attempt to pick a role."""
    for role in ("super_admin", "ops_manager", "support_agent"):
        _, r = _register(client, role=role)
        assert r.status_code == 201
        assert r.json()["role"] == "customer"


def test_register_duplicate_email_conflicts(client):
    email, _ = _register(client)
    _, r = _register(client, email=email)
    assert r.status_code == 409 and error_code(r) == "USER_EXISTS"


def test_register_rejects_short_password_and_bad_email(client):
    r = client.post(f"{API}/auth/register", json={"email": "a@example.com", "full_name": "x", "password": "short"})
    assert r.status_code == 422 and error_code(r) == "VALIDATION_ERROR"
    r = client.post(f"{API}/auth/register", json={"email": "not-an-email", "full_name": "x", "password": PASSWORD})
    assert r.status_code == 422


def test_login_success_returns_both_tokens(client):
    email, _ = _register(client)
    r = _tokens(client, email)
    assert r.status_code == 200
    body = r.json()
    assert body["token_type"] == "bearer" and body["access_token"] and body["refresh_token"]


def test_login_wrong_password_and_unknown_user_are_indistinguishable(client):
    email, _ = _register(client)
    wrong_pw = _tokens(client, email, "WrongPassword1")
    unknown = _tokens(client, "nobody@example.com")
    assert wrong_pw.status_code == unknown.status_code == 401
    assert wrong_pw.json() == unknown.json()  # no user-enumeration leak


def test_me_requires_authentication(client):
    assert client.get(f"{API}/auth/me").status_code == 401
    assert client.get(f"{API}/auth/me", headers={"Authorization": "Bearer garbage"}).status_code == 401


def test_me_returns_current_user(client):
    email, _ = _register(client)
    headers = login(client, email, PASSWORD)
    assert client.get(f"{API}/auth/me", headers=headers).json()["email"] == email


def test_refresh_token_cannot_be_used_as_access_token(client):
    email, _ = _register(client)
    refresh = _tokens(client, email).json()["refresh_token"]
    r = client.get(f"{API}/auth/me", headers={"Authorization": f"Bearer {refresh}"})
    assert r.status_code == 401


def test_access_token_cannot_be_used_to_refresh(client):
    email, _ = _register(client)
    access = _tokens(client, email).json()["access_token"]
    r = client.post(f"{API}/auth/refresh", json={"refresh_token": access})
    assert r.status_code == 401


def test_refresh_issues_working_access_token(client):
    email, _ = _register(client)
    refresh = _tokens(client, email).json()["refresh_token"]
    r = client.post(f"{API}/auth/refresh", json={"refresh_token": refresh})
    assert r.status_code == 200
    me = client.get(f"{API}/auth/me", headers={"Authorization": f"Bearer {r.json()['access_token']}"})
    assert me.status_code == 200


def test_logout_revokes_refresh_token(client):
    email, _ = _register(client)
    refresh = _tokens(client, email).json()["refresh_token"]
    assert client.post(f"{API}/auth/logout", json={"refresh_token": refresh}).status_code == 200
    r = client.post(f"{API}/auth/refresh", json={"refresh_token": refresh})
    assert r.status_code == 401 and error_code(r) == "TOKEN_REVOKED"


def test_logout_is_idempotent_and_tolerates_garbage(client):
    assert client.post(f"{API}/auth/logout", json={"refresh_token": "not-a-jwt"}).status_code == 200


def test_password_reset_full_flow_and_single_use(client):
    email, _ = _register(client)
    r = client.post(f"{API}/auth/password-reset/request", json={"email": email})
    token = re.search(r"token: (\S+)\]", r.json()["message"]).group(1)

    new_pw = "BrandNewPass9"
    assert client.post(f"{API}/auth/password-reset/confirm", json={"token": token, "new_password": new_pw}).status_code == 200
    assert _tokens(client, email, new_pw).status_code == 200
    assert _tokens(client, email, PASSWORD).status_code == 401

    reuse = client.post(f"{API}/auth/password-reset/confirm", json={"token": token, "new_password": "AnotherPass77"})
    assert reuse.status_code == 400


def test_password_reset_for_unknown_email_does_not_leak_existence(client):
    r = client.post(f"{API}/auth/password-reset/request", json={"email": "ghost@example.com"})
    assert r.status_code == 200 and "token" not in r.json()["message"]


def test_password_reset_rejects_wrong_token_type(client):
    email, _ = _register(client)
    access = _tokens(client, email).json()["access_token"]
    r = client.post(f"{API}/auth/password-reset/confirm", json={"token": access, "new_password": "SomethingNew12"})
    assert r.status_code == 400


def test_change_password(client):
    email, _ = _register(client)
    h = login(client, email, PASSWORD)
    bad = client.post(f"{API}/auth/password-change", headers=h, json={"old_password": "nope", "new_password": "NewPassw0rd!"})
    assert bad.status_code == 400
    ok = client.post(f"{API}/auth/password-change", headers=h, json={"old_password": PASSWORD, "new_password": "NewPassw0rd!"})
    assert ok.status_code == 200
    assert _tokens(client, email, "NewPassw0rd!").status_code == 200


def test_deactivated_account_is_locked_out_immediately(client, admin_headers):
    email, r = _register(client)
    user_id = r.json()["id"]
    h = login(client, email, PASSWORD)  # token issued while still active

    r = client.patch(f"{API}/auth/users/{user_id}/activation", headers=admin_headers, json={"is_active": False})
    assert r.status_code == 200 and r.json()["is_active"] is False

    assert _tokens(client, email).status_code == 403                                  # cannot log in
    assert client.get(f"{API}/auth/me", headers=h).status_code == 403                 # existing token dead
    refresh_attempt = client.post(f"{API}/auth/refresh", json={"refresh_token": "x"})
    assert refresh_attempt.status_code == 401

    client.patch(f"{API}/auth/users/{user_id}/activation", headers=admin_headers, json={"is_active": True})
    assert _tokens(client, email).status_code == 200                                  # reactivation works


def test_deactivated_user_cannot_refresh_existing_refresh_token(client, admin_headers):
    email, r = _register(client)
    refresh = _tokens(client, email).json()["refresh_token"]
    client.patch(f"{API}/auth/users/{r.json()['id']}/activation", headers=admin_headers, json={"is_active": False})
    assert client.post(f"{API}/auth/refresh", json={"refresh_token": refresh}).status_code == 401


def test_only_super_admin_can_create_staff(client, staff):
    _, ops = staff("ops_manager")
    r = client.post(f"{API}/auth/users", headers=ops, json={
        "email": f"x.{uniq()}@example.com", "full_name": "X", "password": PASSWORD, "role": "super_admin"})
    assert r.status_code == 403


def test_activation_endpoint_unknown_user_404(client, admin_headers):
    r = client.patch(f"{API}/auth/users/does-not-exist/activation", headers=admin_headers, json={"is_active": False})
    assert r.status_code == 404 and error_code(r) == "NOT_FOUND"


def test_login_is_audited(client, admin_headers):
    r = client.get(f"{API}/audit-logs", headers=admin_headers, params={"entity": "User", "action": "LOGIN"})
    assert r.json()["total"] >= 1


def test_admin_create_user_duplicate_email(client, admin_headers):
    email, _ = _register(client)
    r = client.post(f"{API}/auth/users", headers=admin_headers, json={
        "email": email, "full_name": "Dup", "password": PASSWORD, "role": "support_agent"})
    assert r.status_code == 409 and error_code(r) == "USER_EXISTS"


def test_admin_create_user_customer_link_validation(client, admin_headers):
    body = {"email": f"x.{uniq()}@example.com", "full_name": "x", "password": PASSWORD}
    r = client.post(f"{API}/auth/users", headers=admin_headers, json={**body, "role": "customer", "customer_id": "nope"})
    assert r.status_code == 404 and error_code(r) == "NOT_FOUND"

    from tests.factories import make_customer
    cust = make_customer(client, admin_headers)
    r = client.post(f"{API}/auth/users", headers=admin_headers, json={
        **body, "email": f"y.{uniq()}@example.com", "role": "support_agent", "customer_id": cust["id"]})
    assert r.status_code == 422 and error_code(r) == "INVALID_LINK"

    ok = client.post(f"{API}/auth/users", headers=admin_headers, json={
        **body, "email": f"z.{uniq()}@example.com", "role": "customer", "customer_id": cust["id"]})
    assert ok.status_code == 201 and ok.json()["customer_id"] == cust["id"]


def test_refresh_token_naturally_expires(client, db):
    from datetime import datetime, timedelta, timezone
    from app.models.user import RefreshToken
    email, _ = _register(client)
    refresh = _tokens(client, email).json()["refresh_token"]
    row = db.query(RefreshToken).order_by(RefreshToken.created_at.desc()).first()
    row.expires_at = datetime.now(timezone.utc) - timedelta(seconds=1)
    db.commit()
    r = client.post(f"{API}/auth/refresh", json={"refresh_token": refresh})
    assert r.status_code == 401 and error_code(r) == "TOKEN_EXPIRED"


def test_password_reset_confirm_rejects_garbage_token(client):
    r = client.post(f"{API}/auth/password-reset/confirm", json={"token": "not-a-jwt-at-all", "new_password": "Whatever123"})
    assert r.status_code == 400 and error_code(r) == "INVALID_TOKEN"


def test_password_reset_naturally_expires(client, db):
    from datetime import datetime, timedelta, timezone
    from app.models.user import PasswordResetToken
    email, _ = _register(client)
    r = client.post(f"{API}/auth/password-reset/request", json={"email": email})
    token = re.search(r"token: (\S+)\]", r.json()["message"]).group(1)
    row = db.query(PasswordResetToken).filter_by(token=token).one()
    row.expires_at = datetime.now(timezone.utc) - timedelta(seconds=1)
    db.commit()
    r = client.post(f"{API}/auth/password-reset/confirm", json={"token": token, "new_password": "Whatever123"})
    assert r.status_code == 400 and error_code(r) == "TOKEN_EXPIRED"


def test_hard_deleting_a_user_cascades_their_own_tokens(client, db):
    """No API endpoint hard-deletes a user (accounts are only ever deactivated - see the
    activation tests above); this documents the schema's behavior if a user row is ever purged
    directly, e.g. by a future GDPR erasure job. A user's OWN session artifacts (refresh tokens,
    password-reset tokens) are tied 1:1 to their account and should disappear with it."""
    from app.models.user import User, RefreshToken, PasswordResetToken
    from app.core.security import hash_password

    user = User(email=f"cascade.{uniq()}@example.com", full_name="Cascade Test", hashed_password=hash_password(PASSWORD))
    db.add(user); db.commit()
    db.add(RefreshToken(jti=uniq(), user_id=user.id, expires_at=__import__("datetime").datetime.now(__import__("datetime").timezone.utc)))
    db.add(PasswordResetToken(user_id=user.id, token="x", expires_at=__import__("datetime").datetime.now(__import__("datetime").timezone.utc)))
    db.commit()

    db.query(User).filter_by(id=user.id).delete()
    db.commit()  # must not raise ForeignKeyViolation

    assert db.query(RefreshToken).filter_by(user_id=user.id).count() == 0
    assert db.query(PasswordResetToken).filter_by(user_id=user.id).count() == 0


def test_a_user_with_audit_history_cannot_be_hard_deleted(client, db):
    """The flip side of the cascade above: audit_logs.user_id intentionally has NO cascade, so the
    audit trail can never be silently destroyed by removing the account that produced it. Once a
    user has done anything audited (logging in, in this case), only deactivation remains possible -
    which is exactly the activation/deactivation flow this API actually exposes."""
    from sqlalchemy.exc import IntegrityError
    from app.models.user import User

    email, _ = _register(client)               # REGISTER is audited
    _tokens(client, email)                      # LOGIN is audited too
    user = db.query(User).filter_by(email=email).one()

    with pytest.raises(IntegrityError):
        db.query(User).filter_by(id=user.id).delete()
        db.commit()
    db.rollback()

    assert db.get(User, user.id) is not None    # untouched; deactivation is the supported path
    client_h = login(client, email, PASSWORD)
    assert client.get(f"{API}/auth/me", headers=client_h).status_code == 200
