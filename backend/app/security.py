from datetime import datetime, timedelta, timezone
from typing import Any, Union, List, Optional
from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
import jwt
from passlib.context import CryptContext
from sqlalchemy.orm import Session
from app.config import settings
from app.db.session import get_db

# Password hashing configuration
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

# OAuth2 scheme definition
oauth2_scheme = OAuth2PasswordBearer(
    tokenUrl=f"{settings.API_V1_STR}/auth/token"
)


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Validate a raw password against its stored bcrypt hash."""
    return pwd_context.verify(plain_password, hashed_password)


def get_password_hash(password: str) -> str:
    """Generate a bcrypt hash of the provided password."""
    return pwd_context.hash(password)


def create_access_token(
    subject: Union[str, Any],
    role: Optional[str] = None,
    expires_delta: timedelta = None
) -> str:
    """
    Generate a cryptographically secure JWT access token signed with the HS256 algorithm.
    Packs role information directly in JWT claims for stateless gatekeeping.
    """
    if expires_delta:
        expire = datetime.now(timezone.utc) + expires_delta
    else:
        expire = datetime.now(timezone.utc) + timedelta(
            minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES
        )

    to_encode = {"exp": expire, "sub": str(subject)}
    if role:
        to_encode["role"] = str(role)

    encoded_jwt = jwt.encode(
        to_encode,
        settings.JWT_SECRET_KEY,
        algorithm=settings.JWT_ALGORITHM
    )
    return encoded_jwt


def get_current_user(
    db: Session = Depends(get_db),
    token: str = Depends(oauth2_scheme)
) -> Any:
    """
    FastAPI dependency validating the access token.
    Extracts user details and checks existence within PostgreSQL.
    """
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        payload = jwt.decode(
            token,
            settings.JWT_SECRET_KEY,
            algorithms=[settings.JWT_ALGORITHM]
        )
        username: str = payload.get("sub")
        if username is None:
            raise credentials_exception
    except jwt.PyJWTError:
        raise credentials_exception

    # Dynamic import to prevent circular dependency with user model
    from app.models.user import User

    user = db.query(User).filter(User.username == username).first()
    if user is None:
        raise credentials_exception

    return user


class RoleChecker:
    """
    FastAPI dependency guard protecting API endpoints using Role-Based Access Control (RBAC).
    Checks that the current authorized user possesses an allowed role.
    """
    def __init__(self, allowed_roles: List[str]):
        self.allowed_roles = [r.lower() for r in allowed_roles]

    def __call__(self, current_user: Any = Depends(get_current_user)) -> Any:
        if current_user.role.lower() not in self.allowed_roles:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Operation not permitted. Required roles: {self.allowed_roles}. Your role: {current_user.role}"
            )
        return current_user
