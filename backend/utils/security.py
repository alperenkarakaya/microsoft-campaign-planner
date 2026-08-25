"""Authentication primitives: password hashing, JWT issuance/verification.

Configuration (all optional, with safe local defaults):
  JWT_SECRET_KEY                   signing secret — MUST be set in production
  JWT_ALGORITHM                    default HS256
  JWT_ACCESS_TOKEN_EXPIRE_MINUTES  default 30
  ENVIRONMENT                      "production" makes a weak secret fatal
"""

import os
import logging
from datetime import datetime, timedelta, timezone
from typing import Optional

import bcrypt as _bcrypt
from jose import JWTError, jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.orm import Session

from database import get_db
from models import User

logger = logging.getLogger(__name__)

# Known insecure values that must never be used to sign tokens in production.
_WEAK_SECRETS = {
    "",
    "super-secret-key-change-in-production",
    "your-secret-key-here",
    "change-me-in-production",
}

ENVIRONMENT = os.getenv("ENVIRONMENT", "development").lower()
# Accept either JWT_SECRET_KEY (preferred) or legacy SECRET_KEY.
SECRET_KEY = os.getenv("JWT_SECRET_KEY") or os.getenv("SECRET_KEY") or ""
ALGORITHM = os.getenv("JWT_ALGORITHM", "HS256")
ACCESS_TOKEN_EXPIRE_MINUTES = int(os.getenv("JWT_ACCESS_TOKEN_EXPIRE_MINUTES", "30"))

# bcrypt only consumes the first 72 bytes; longer inputs raise ValueError in the
# raw library, so we truncate consistently for both hashing and verification.
_BCRYPT_MAX_BYTES = 72

if SECRET_KEY in _WEAK_SECRETS:
    if ENVIRONMENT == "production":
        raise RuntimeError(
            "JWT_SECRET_KEY is unset or using a known weak default. Set a strong "
            "JWT_SECRET_KEY environment variable before running in production."
        )
    logger.warning(
        "JWT_SECRET_KEY is weak/unset; using an insecure development fallback. "
        "Set JWT_SECRET_KEY before deploying."
    )
    SECRET_KEY = SECRET_KEY or "dev-only-insecure-secret"

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="api/v1/auth/login")


def _truncate(password: str) -> bytes:
    return password.encode("utf-8")[:_BCRYPT_MAX_BYTES]


def verify_password(plain_password: str, hashed_password: str) -> bool:
    try:
        return _bcrypt.checkpw(_truncate(plain_password), hashed_password.encode("utf-8"))
    except (ValueError, TypeError):
        return False


def get_password_hash(password: str) -> str:
    return _bcrypt.hashpw(_truncate(password), _bcrypt.gensalt()).decode("utf-8")


def create_access_token(data: dict, expires_delta: Optional[timedelta] = None) -> str:
    """Create a signed JWT. Expiry defaults to ACCESS_TOKEN_EXPIRE_MINUTES."""
    to_encode = data.copy()
    expire = datetime.now(timezone.utc) + (
        expires_delta or timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    )
    to_encode.update({"exp": expire})
    return jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)


async def get_current_user(
    token: str = Depends(oauth2_scheme),
    db: Session = Depends(get_db),
) -> User:
    """Resolve the active user from a bearer token. Raises 401 on any failure."""
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )

    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        sub = payload.get("sub")
        if sub is None:
            raise credentials_exception
        user_id = int(sub)
    except (JWTError, ValueError, TypeError):
        raise credentials_exception

    user = db.query(User).filter(User.id == user_id).first()
    if user is None:
        raise credentials_exception
    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="User account is disabled",
        )

    return user
