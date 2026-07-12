from datetime import datetime, timedelta, timezone
from typing import Annotated

from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from jose import JWTError, jwt
from passlib.context import CryptContext
from sqlalchemy.orm import Session

from app.config import get_settings
from app.db import get_db
from app.models import User, UserRole

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/auth/login")
settings = get_settings()


def hash_password(password: str) -> str:
    return pwd_context.hash(password[:72])


def verify_password(plain: str, hashed: str) -> bool:
    return pwd_context.verify(plain[:72], hashed)


def create_access_token(subject: str, role: str, expires_minutes: int | None = None) -> str:
    expire = datetime.now(timezone.utc) + timedelta(
        minutes=expires_minutes or settings.access_token_expire_minutes
    )
    payload = {"sub": subject, "role": role, "exp": expire}
    return jwt.encode(payload, settings.secret_key, algorithm=settings.algorithm)


def get_user_by_username(db: Session, username: str) -> User | None:
    return db.query(User).filter(User.username == username).first()


def authenticate_user(db: Session, username: str, password: str) -> User | None:
    user = get_user_by_username(db, username)
    if not user or not verify_password(password, user.password_hash):
        return None
    return user


def get_current_user(
    token: Annotated[str, Depends(oauth2_scheme)],
    db: Annotated[Session, Depends(get_db)],
) -> User:
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="无效的认证凭证",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        payload = jwt.decode(token, settings.secret_key, algorithms=[settings.algorithm])
        username = payload.get("sub")
        if not username:
            raise credentials_exception
    except JWTError as exc:
        raise credentials_exception from exc

    user = get_user_by_username(db, username)
    if not user or not user.is_active:
        raise credentials_exception
    return user


def get_current_admin(user: Annotated[User, Depends(get_current_user)]) -> User:
    if user.role != UserRole.admin.value:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="需要管理员权限")
    return user


def bootstrap_admin(db: Session) -> None:
    """Create bootstrap admin. Prefer fixed primary key id=1 when available."""
    cfg = get_settings()
    username = cfg.bootstrap_admin_username
    password = cfg.bootstrap_admin_password
    if not username or not password:
        return
    existing = get_user_by_username(db, username)
    if existing:
        return

    password_hash = hash_password(password)
    id_one = db.query(User).filter(User.id == 1).first()
    if id_one is None:
        admin = User(
            id=1,
            username=username,
            password_hash=password_hash,
            role=UserRole.admin.value,
            is_active=True,
        )
    else:
        # Extreme case: id=1 already taken by another user; fall back to autoincrement.
        admin = User(
            username=username,
            password_hash=password_hash,
            role=UserRole.admin.value,
            is_active=True,
        )
    db.add(admin)
    db.commit()
