import uuid
from datetime import datetime, timedelta, timezone

from jose import JWTError
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.exceptions import AppError, NotFoundError
from app.core.security import (
    hash_password,
    verify_password,
    create_access_token,
    create_refresh_token,
    create_password_reset_token,
    decode_token,
    TOKEN_TYPE_REFRESH,
    TOKEN_TYPE_RESET,
)
from app.models.user import User, RefreshToken, PasswordResetToken
from app.models.customer import Customer
from app.models.enums import UserRole
from app.schemas.auth import UserRegister, AdminUserCreate
from app.utils.audit_logger import record_audit


def register_user(db: Session, payload: UserRegister) -> User:
    if db.query(User).filter(User.email == payload.email).first():
        raise AppError("A user with this email already exists", 409, "USER_EXISTS")

    user = User(
        email=payload.email,
        full_name=payload.full_name,
        phone=payload.phone,
        hashed_password=hash_password(payload.password),
        role=UserRole.CUSTOMER,  # public registration can NEVER create privileged roles
    )
    db.add(user)
    db.flush()
    record_audit(db, user_id=user.id, action="REGISTER", entity="User", entity_id=user.id, new_value={"email": user.email, "role": user.role.value})
    db.commit()
    db.refresh(user)
    return user


def admin_create_user(db: Session, actor: User, payload: AdminUserCreate) -> User:
    if db.query(User).filter(User.email == payload.email).first():
        raise AppError("A user with this email already exists", 409, "USER_EXISTS")
    if payload.customer_id:
        if not db.get(Customer, payload.customer_id):
            raise NotFoundError("Customer not found")
        if payload.role != UserRole.CUSTOMER:
            raise AppError("Only customer-role users can be linked to a customer profile", 422, "INVALID_LINK")

    user = User(
        email=payload.email,
        full_name=payload.full_name,
        phone=payload.phone,
        hashed_password=hash_password(payload.password),
        role=payload.role,
        customer_id=payload.customer_id,
    )
    db.add(user)
    db.flush()
    record_audit(db, user_id=actor.id, action="CREATE", entity="User", entity_id=user.id, new_value={"email": user.email, "role": user.role.value})
    db.commit()
    db.refresh(user)
    return user


def _issue_tokens(db: Session, user: User) -> tuple[str, str]:
    jti = str(uuid.uuid4())
    access = create_access_token(user.id, user.role.value)
    refresh = create_refresh_token(user.id, jti)

    db.add(
        RefreshToken(
            jti=jti,
            user_id=user.id,
            expires_at=datetime.now(timezone.utc) + timedelta(days=settings.REFRESH_TOKEN_EXPIRE_DAYS),
        )
    )
    db.commit()
    return access, refresh


def login(db: Session, email: str, password: str) -> tuple[str, str]:
    user = db.query(User).filter(User.email == email).first()
    if not user or not verify_password(password, user.hashed_password):
        raise AppError("Invalid email or password", 401, "INVALID_CREDENTIALS")
    if not user.is_active:
        raise AppError("Account is deactivated", 403, "ACCOUNT_DEACTIVATED")

    access, refresh = _issue_tokens(db, user)
    record_audit(db, user_id=user.id, action="LOGIN", entity="User", entity_id=user.id)
    db.commit()
    return access, refresh


def refresh_access_token(db: Session, refresh_token: str) -> str:
    try:
        payload = decode_token(refresh_token)
    except JWTError:
        raise AppError("Invalid or expired refresh token", 401, "INVALID_TOKEN")

    if payload.get("type") != TOKEN_TYPE_REFRESH:
        raise AppError("Invalid token type", 401, "INVALID_TOKEN")

    jti = payload.get("jti")
    stored = db.query(RefreshToken).filter(RefreshToken.jti == jti).first()
    if not stored or stored.revoked:
        raise AppError("Refresh token has been revoked", 401, "TOKEN_REVOKED")
    if stored.expires_at < datetime.now(timezone.utc):
        raise AppError("Refresh token has expired", 401, "TOKEN_EXPIRED")

    user = db.get(User, payload.get("sub"))
    if not user or not user.is_active:
        raise AppError("User not found or inactive", 401, "INVALID_USER")

    return create_access_token(user.id, user.role.value)


def logout(db: Session, refresh_token: str) -> None:
    try:
        payload = decode_token(refresh_token)
    except JWTError:
        return  # already invalid; logout is idempotent
    jti = payload.get("jti")
    stored = db.query(RefreshToken).filter(RefreshToken.jti == jti).first()
    if stored:
        stored.revoked = True
        db.commit()


def request_password_reset(db: Session, email: str) -> str | None:
    user = db.query(User).filter(User.email == email).first()
    if not user:
        # Do not leak whether the email exists.
        return None
    token = create_password_reset_token(user.id)
    db.add(
        PasswordResetToken(
            user_id=user.id,
            token=token,
            expires_at=datetime.now(timezone.utc) + timedelta(minutes=settings.PASSWORD_RESET_TOKEN_EXPIRE_MINUTES),
        )
    )
    db.commit()
    return token  # In production this would be emailed, not returned.


def confirm_password_reset(db: Session, token: str, new_password: str) -> None:
    try:
        payload = decode_token(token)
    except JWTError:
        raise AppError("Invalid or expired reset token", 400, "INVALID_TOKEN")
    if payload.get("type") != TOKEN_TYPE_RESET:
        raise AppError("Invalid token type", 400, "INVALID_TOKEN")

    record = db.query(PasswordResetToken).filter(PasswordResetToken.token == token).first()
    if not record or record.used:
        raise AppError("Reset token already used or invalid", 400, "INVALID_TOKEN")
    if record.expires_at < datetime.now(timezone.utc):
        raise AppError("Reset token expired", 400, "TOKEN_EXPIRED")

    user = db.get(User, payload.get("sub"))
    if not user:
        raise NotFoundError("User not found")

    user.hashed_password = hash_password(new_password)
    record.used = True
    record_audit(db, user_id=user.id, action="PASSWORD_RESET", entity="User", entity_id=user.id)
    db.commit()


def change_password(db: Session, user: User, old_password: str, new_password: str) -> None:
    if not verify_password(old_password, user.hashed_password):
        raise AppError("Old password is incorrect", 400, "INVALID_PASSWORD")
    user.hashed_password = hash_password(new_password)
    record_audit(db, user_id=user.id, action="PASSWORD_CHANGE", entity="User", entity_id=user.id)
    db.commit()


def set_user_active(db: Session, actor: User, target_user_id: str, is_active: bool) -> User:
    target = db.get(User, target_user_id)
    if not target:
        raise NotFoundError("User not found")
    previous = target.is_active
    target.is_active = is_active
    record_audit(
        db,
        user_id=actor.id,
        action="ACTIVATE" if is_active else "DEACTIVATE",
        entity="User",
        entity_id=target.id,
        previous_value={"is_active": previous},
        new_value={"is_active": is_active},
    )
    db.commit()
    db.refresh(target)
    return target
