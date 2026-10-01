"""
Reusable FastAPI dependencies: DB session, current user, role-based access control.
"""
from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from jose import JWTError
from sqlalchemy.orm import Session

from app.core.security import decode_token, TOKEN_TYPE_ACCESS
from app.db.session import get_db
from app.models.user import User
from app.models.enums import UserRole

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/v1/auth/login", auto_error=False)


def get_current_user(
    token: str | None = Depends(oauth2_scheme),
    db: Session = Depends(get_db),
) -> User:
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    if token is None:
        raise credentials_exception
    try:
        payload = decode_token(token)
        if payload.get("type") != TOKEN_TYPE_ACCESS:
            raise credentials_exception
        user_id = payload.get("sub")
        if user_id is None:
            raise credentials_exception
    except JWTError:
        raise credentials_exception

    user = db.get(User, user_id)
    if user is None:
        raise credentials_exception
    if not user.is_active:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Account is deactivated")
    return user


class RoleChecker:
    """Usage: Depends(RoleChecker([UserRole.SUPER_ADMIN, UserRole.OPS_MANAGER]))"""

    def __init__(self, allowed_roles: list[UserRole]):
        self.allowed_roles = allowed_roles

    def __call__(self, current_user: User = Depends(get_current_user)) -> User:
        if current_user.role not in self.allowed_roles:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Role '{current_user.role.value}' is not permitted to perform this action",
            )
        return current_user


def assert_customer_access(user: User, customer_id: str | None) -> None:
    """Customers may only touch their own records; staff may touch any."""
    if user.role == UserRole.CUSTOMER and (customer_id is None or user.customer_id != customer_id):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="You can only access your own records")


# Common role bundles
require_super_admin = RoleChecker([UserRole.SUPER_ADMIN])
require_admin_or_ops = RoleChecker([UserRole.SUPER_ADMIN, UserRole.OPS_MANAGER])
require_staff = RoleChecker(
    [
        UserRole.SUPER_ADMIN,
        UserRole.OPS_MANAGER,
        UserRole.SUPPORT_AGENT,
        UserRole.NETWORK_ENGINEER,
        UserRole.FIELD_TECHNICIAN,
    ]
)
require_support_staff = RoleChecker([UserRole.SUPER_ADMIN, UserRole.OPS_MANAGER, UserRole.SUPPORT_AGENT])
require_network_staff = RoleChecker([UserRole.SUPER_ADMIN, UserRole.OPS_MANAGER, UserRole.NETWORK_ENGINEER])
