from typing import Annotated
from urllib.parse import urlsplit, urlunsplit

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.config import get_settings
from app.db import get_db
from app.models import Book, BookVisibility, Job, User, UserRole
from app.schemas import (
    AdminBookUpdate,
    AdminUserCreate,
    BookOut,
    JobOut,
    MessageOut,
    SettingsOut,
    SettingsUpdate,
    SystemInfoOut,
    UserOut,
    UserUpdate,
)
from app.services.auth import get_current_admin, get_user_by_username, hash_password
from app.services.books import cleanup_book_files, cleanup_user_data
from app.services.settings_service import get_or_create_settings

router = APIRouter(prefix="/admin", tags=["admin"])
APP_VERSION = "0.1.0"


def _redact_database_url(url: str) -> str:
    try:
        parts = urlsplit(url)
        if parts.password is None and "@" not in (parts.netloc or ""):
            return url
        # rebuild netloc without password
        host = parts.hostname or ""
        if parts.port:
            host = f"{host}:{parts.port}"
        if parts.username:
            netloc = f"{parts.username}:***@{host}"
        else:
            netloc = host
        return urlunsplit((parts.scheme, netloc, parts.path, parts.query, parts.fragment))
    except Exception:  # noqa: BLE001
        return "***"


@router.get("/users", response_model=list[UserOut])
def list_users(
    db: Annotated[Session, Depends(get_db)],
    _: Annotated[User, Depends(get_current_admin)],
) -> list[User]:
    return db.query(User).order_by(User.id.asc()).all()


@router.post("/users", response_model=UserOut, status_code=status.HTTP_201_CREATED)
def create_user(
    payload: AdminUserCreate,
    db: Annotated[Session, Depends(get_db)],
    _: Annotated[User, Depends(get_current_admin)],
) -> User:
    if get_user_by_username(db, payload.username):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="用户名已存在")
    role = payload.role or UserRole.user.value
    if role not in {UserRole.user.value, UserRole.admin.value}:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="角色无效")
    user = User(
        username=payload.username,
        password_hash=hash_password(payload.password),
        role=role,
        is_active=True,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


@router.patch("/users/{user_id}", response_model=UserOut)
def update_user(
    user_id: int,
    payload: UserUpdate,
    db: Annotated[Session, Depends(get_db)],
    admin: Annotated[User, Depends(get_current_admin)],
) -> User:
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="用户不存在")

    # Admin accounts cannot be demoted or disabled.
    if user.role == UserRole.admin.value:
        if payload.role is not None and payload.role != UserRole.admin.value:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="管理员账号不可降级",
            )
        if payload.is_active is False:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="管理员账号不可禁用",
            )

    if payload.password is not None:
        user.password_hash = hash_password(payload.password)
    if payload.role is not None:
        user.role = payload.role
    if payload.is_active is not None:
        user.is_active = payload.is_active
    db.commit()
    db.refresh(user)
    return user


@router.delete("/users/{user_id}", response_model=MessageOut)
def delete_user(
    user_id: int,
    db: Annotated[Session, Depends(get_db)],
    admin: Annotated[User, Depends(get_current_admin)],
) -> MessageOut:
    if admin.id == user_id:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="不能删除当前管理员自己")
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="用户不存在")
    if user.role == UserRole.admin.value:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="不能删除管理员账号")
    cleanup_user_data(db, user)
    db.delete(user)
    db.commit()
    return MessageOut(message="已删除")


@router.get("/settings", response_model=SettingsOut)
def get_settings_admin(
    db: Annotated[Session, Depends(get_db)],
    _: Annotated[User, Depends(get_current_admin)],
) -> SettingsOut:
    row = get_or_create_settings(db)
    return SettingsOut(
        registration_enabled=row.registration_enabled,
        invite_required=row.invite_required,
        invite_code=row.invite_code,
        updated_at=row.updated_at,
    )


@router.put("/settings", response_model=SettingsOut)
def update_settings_admin(
    payload: SettingsUpdate,
    db: Annotated[Session, Depends(get_db)],
    _: Annotated[User, Depends(get_current_admin)],
) -> SettingsOut:
    row = get_or_create_settings(db)
    if payload.registration_enabled is not None:
        row.registration_enabled = payload.registration_enabled
    if payload.invite_required is not None:
        row.invite_required = payload.invite_required
    if payload.invite_code is not None:
        row.invite_code = payload.invite_code
    db.commit()
    db.refresh(row)
    return SettingsOut(
        registration_enabled=row.registration_enabled,
        invite_required=row.invite_required,
        invite_code=row.invite_code,
        updated_at=row.updated_at,
    )


@router.get("/jobs", response_model=list[JobOut])
def list_jobs(
    db: Annotated[Session, Depends(get_db)],
    _: Annotated[User, Depends(get_current_admin)],
) -> list[Job]:
    return db.query(Job).order_by(Job.id.desc()).all()


@router.get("/books", response_model=list[BookOut])
def list_all_books(
    db: Annotated[Session, Depends(get_db)],
    _: Annotated[User, Depends(get_current_admin)],
) -> list[Book]:
    return db.query(Book).order_by(Book.id.desc()).all()


@router.patch("/books/{book_id}", response_model=BookOut)
def admin_update_book(
    book_id: int,
    payload: AdminBookUpdate,
    db: Annotated[Session, Depends(get_db)],
    _: Annotated[User, Depends(get_current_admin)],
) -> Book:
    book = db.query(Book).filter(Book.id == book_id).first()
    if not book:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="书籍不存在")
    if payload.title is not None:
        book.title = payload.title
    if payload.author is not None:
        book.author = payload.author
    # Public library removed: force private when visibility/is_public is provided.
    if payload.visibility is not None or payload.is_public is not None:
        book.visibility = BookVisibility.private.value
    db.commit()
    db.refresh(book)
    return book


@router.delete("/books/{book_id}", response_model=MessageOut)
def admin_delete_book(
    book_id: int,
    db: Annotated[Session, Depends(get_db)],
    _: Annotated[User, Depends(get_current_admin)],
) -> MessageOut:
    book = db.query(Book).filter(Book.id == book_id).first()
    if not book:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="书籍不存在")
    cleanup_book_files(book)
    db.delete(book)
    db.commit()
    return MessageOut(message="已删除")


@router.get("/system", response_model=SystemInfoOut)
def system_info(
    db: Annotated[Session, Depends(get_db)],
    _: Annotated[User, Depends(get_current_admin)],
) -> SystemInfoOut:
    cfg = get_settings()
    return SystemInfoOut(
        app_name=cfg.app_name,
        database_url=_redact_database_url(cfg.database_url),
        user_count=db.query(User).count(),
        book_count=db.query(Book).count(),
        job_count=db.query(Job).count(),
        version=APP_VERSION,
    )

