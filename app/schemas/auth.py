from pydantic import BaseModel, EmailStr, Field

from app.models.enums import UserRole
from app.schemas.common import ORMModel


class UserRegister(BaseModel):
    email: EmailStr
    full_name: str
    phone: str | None = None
    password: str = Field(min_length=8)


class AdminUserCreate(BaseModel):
    """Used by Super Admins to create staff accounts (or customer logins linked to a customer profile)."""
    email: EmailStr
    full_name: str
    phone: str | None = None
    password: str = Field(min_length=8)
    role: UserRole
    customer_id: str | None = None


class UserOut(ORMModel):
    id: str
    email: str
    full_name: str
    phone: str | None
    role: UserRole
    is_active: bool
    customer_id: str | None = None


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class TokenResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"


class RefreshRequest(BaseModel):
    refresh_token: str


class AccessTokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"


class LogoutRequest(BaseModel):
    refresh_token: str


class PasswordResetRequest(BaseModel):
    email: EmailStr


class PasswordResetConfirm(BaseModel):
    token: str
    new_password: str = Field(min_length=8)


class PasswordChangeRequest(BaseModel):
    old_password: str
    new_password: str = Field(min_length=8)


class ActivationRequest(BaseModel):
    is_active: bool
