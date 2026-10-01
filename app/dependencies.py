from fastapi import Depends
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from sqlalchemy.orm import Session

from app.db.database import get_db
from app.models.user import User, UserRole
from app.utils.security import decode_token

bearer_scheme = HTTPBearer(auto_error=False)

def get_current_user(
        credentials:HTTPAuthorizationCredentials = Depends(get_db),
        db:Session = Depends(get_db)
) ->User:
    if credentials is None:
       raise Exception("Missing Bearer token.")

    token = credentials.credentials
    payload = decode_token(token)

    if payload is None or payload.get("type") != "access":
        raise Exception("Invalid or Expired access token")

    user = db.query(User).filter(User.email == payload.get("sub")).first()
    if user is None:
        raise Exception("user no longer exists")

    if not user.is_active:
        raise Exception("This account has been deactivated.")

    return user

def require_roles(*allowed_roles:UserRole):

    def _checker(current_user:User = Depends(get_current_user))-> User:
        if current_user.role not in allowed_roles:
            raise Exception(f"Role'{current_user.role.value}' is not perform this action.")

        return current_user
    return _checker


require_super_admin = require_roles(UserRole.SUPER_ADMIN)

require_any_authenticated = get_current_user
