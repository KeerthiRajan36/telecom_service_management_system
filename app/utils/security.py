from datetime import datetime, timedelta, timezone
from typing import Optional

from jose import jwt, JWTError
from passlib.context import CryptContext

from app.config import settings

pwd_context = CryptContext(
    schemes=["argon2"],
    deprecated="auto"
)

def hash_password(plain_password:str) -> str:
    return pwd_context.hash(plain_password)

def verify_password(plain_password:str,hashed_password:str)-> bool:
    return pwd_context.verify(
        plain_password,
        hashed_password
    )

def _create_token(subject:str, role:str, expires_delta: timedelta,token_type:str)->str:
    now = datetime.now(timezone.utc)
    payload = {
        "sub": subject,
        "role": role,
        "type":token_type,
        "iat":now,
        "exp":now+expires_delta
    }
    return jwt.encode(payload,settings.SECRET_KEY,algorithm=settings.JWT_ALGORITHM)


def create_access_token(subject:str,role:str)->str:
    return _create_token(
        subject,role, timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES),token_type="access"
    )

def create_refresh_token(subject:str,role:str)-> str:
    return _create_token(
        subject,role,timedelta(days=settings.REFRESH_TOKEN_EXPIRE_DAYS),token_type="refresh"
    )

def decode_token(token:str)-> Optional[dict]:
    try:
        return jwt.decode(token,settings.SECRET_KEY,algorithms=[settings.JWT_ALGORITHM])
    except JWTError:
        return None