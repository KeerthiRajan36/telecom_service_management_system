from fastapi import APIRouter, Depends, status
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy.orm import Session

from app.core.deps import get_current_user, require_admin_or_ops, require_super_admin
from app.db.session import get_db
from app.models.user import User
from app.schemas.auth import (
    UserRegister, UserOut, TokenResponse, RefreshRequest, AccessTokenResponse,
    LogoutRequest, PasswordResetRequest, PasswordResetConfirm, PasswordChangeRequest,
    ActivationRequest, AdminUserCreate,
)
from app.schemas.common import MessageResponse
from app.services import auth_service

router = APIRouter(prefix="/auth", tags=["Authentication"])


@router.post("/register", response_model=UserOut, status_code=status.HTTP_201_CREATED)
def register(payload: UserRegister, db: Session = Depends(get_db)):
    return auth_service.register_user(db, payload)


@router.post("/users", response_model=UserOut, status_code=status.HTTP_201_CREATED)
def admin_create_user(
    payload: AdminUserCreate,
    current_user: User = Depends(require_super_admin),
    db: Session = Depends(get_db),
):
    """Super Admin only: create staff accounts or customer logins linked to a customer profile."""
    return auth_service.admin_create_user(db, current_user, payload)


@router.post("/login", response_model=TokenResponse)
def login(form_data: OAuth2PasswordRequestForm = Depends(), db: Session = Depends(get_db)):
    """Note: use the account's email address as the 'username' field."""
    access, refresh = auth_service.login(db, form_data.username, form_data.password)
    return TokenResponse(access_token=access, refresh_token=refresh)


@router.post("/refresh", response_model=AccessTokenResponse)
def refresh(payload: RefreshRequest, db: Session = Depends(get_db)):
    access = auth_service.refresh_access_token(db, payload.refresh_token)
    return AccessTokenResponse(access_token=access)


@router.post("/logout", response_model=MessageResponse)
def logout(payload: LogoutRequest, db: Session = Depends(get_db)):
    auth_service.logout(db, payload.refresh_token)
    return MessageResponse(message="Logged out successfully")


@router.get("/me", response_model=UserOut)
def me(current_user: User = Depends(get_current_user)):
    return current_user


@router.post("/password-reset/request", response_model=MessageResponse)
def request_password_reset(payload: PasswordResetRequest, db: Session = Depends(get_db)):
    token = auth_service.request_password_reset(db, payload.email)
    # In production this token would be emailed, never returned in the API response.
    # It's included here only because this project has no email backend configured.
    msg = "If that email exists, a reset link has been sent."
    if token:
        msg += f" [DEV MODE token: {token}]"
    return MessageResponse(message=msg)


@router.post("/password-reset/confirm", response_model=MessageResponse)
def confirm_password_reset(payload: PasswordResetConfirm, db: Session = Depends(get_db)):
    auth_service.confirm_password_reset(db, payload.token, payload.new_password)
    return MessageResponse(message="Password has been reset successfully")


@router.post("/password-change", response_model=MessageResponse)
def change_password(
    payload: PasswordChangeRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    auth_service.change_password(db, current_user, payload.old_password, payload.new_password)
    return MessageResponse(message="Password changed successfully")


@router.patch("/users/{user_id}/activation", response_model=UserOut)
def set_user_activation(
    user_id: str,
    payload: ActivationRequest,
    current_user: User = Depends(require_admin_or_ops),
    db: Session = Depends(get_db),
):
    return auth_service.set_user_active(db, current_user, user_id, payload.is_active)
