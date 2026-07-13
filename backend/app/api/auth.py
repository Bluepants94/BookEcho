from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.orm import Session

from app.db import get_db
from app.models import User, UserRole
from app.schemas import (
    MessageOut,
    PasswordChange,
    PublicSettingsOut,
    Token,
    UserCreate,
    UserLogin,
    UserOut,
    UserTtsSettings,
)
from app.services.user_settings import get_user_tts_settings, save_user_tts_settings
from app.services.auth import (
    authenticate_user,
    create_access_token,
    get_current_user,
    get_user_by_username,
    hash_password,
    verify_password,
)
from app.services.settings_service import get_or_create_settings

router = APIRouter(prefix="/auth", tags=["auth"])


def _issue_token(db: Session, username: str, password: str) -> Token:
    user = authenticate_user(db, username, password)
    if not user:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="用户名或密码错误")
    if not user.is_active:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="账号已禁用")
    token = create_access_token(user.username, user.role)
    return Token(access_token=token)


async def _extract_login_credentials(request: Request) -> tuple[str, str]:
    content_type = (request.headers.get("content-type") or "").lower()
    username: Any = None
    password: Any = None
    if "application/json" in content_type:
        body = await request.json()
        if not isinstance(body, dict):
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="无效的登录请求")
        username = body.get("username")
        password = body.get("password")
    else:
        form = await request.form()
        username = form.get("username")
        password = form.get("password")
    if not username or not password:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="缺少用户名或密码",
        )
    return str(username), str(password)


@router.post("/register", response_model=UserOut, status_code=status.HTTP_201_CREATED)
def register(payload: UserCreate, db: Annotated[Session, Depends(get_db)]) -> User:
    settings = get_or_create_settings(db)
    if not settings.registration_enabled:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="当前未开放注册")
    if settings.invite_required:
        if not payload.invite_code or payload.invite_code != settings.invite_code:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="邀请码无效")
    if get_user_by_username(db, payload.username):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="用户名已存在")

    user = User(
        username=payload.username,
        password_hash=hash_password(payload.password),
        role=UserRole.user.value,
        is_active=True,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


@router.post("/login", response_model=Token)
async def login(
    request: Request,
    db: Annotated[Session, Depends(get_db)],
) -> Token:
    """Accept both form-urlencoded (OAuth2) and JSON body credentials."""
    username, password = await _extract_login_credentials(request)
    return _issue_token(db, username, password)


@router.post("/login/json", response_model=Token)
def login_json(payload: UserLogin, db: Annotated[Session, Depends(get_db)]) -> Token:
    return _issue_token(db, payload.username, payload.password)


@router.get("/me", response_model=UserOut)
def me(user: Annotated[User, Depends(get_current_user)]) -> User:
    return user


def _public_settings(db: Session) -> PublicSettingsOut:
    settings = get_or_create_settings(db)
    return PublicSettingsOut(
        registration_enabled=settings.registration_enabled,
        invite_required=settings.invite_required,
    )


@router.get("/registration-status", response_model=PublicSettingsOut)
def registration_status(db: Annotated[Session, Depends(get_db)]) -> PublicSettingsOut:
    return _public_settings(db)


@router.get("/public-settings", response_model=PublicSettingsOut)
def public_settings(db: Annotated[Session, Depends(get_db)]) -> PublicSettingsOut:
    return _public_settings(db)

@router.post("/change-password", response_model=MessageOut)
def change_password(
    payload: PasswordChange,
    db: Annotated[Session, Depends(get_db)],
    user: Annotated[User, Depends(get_current_user)],
) -> MessageOut:
    if not verify_password(payload.old_password, user.password_hash):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="原密码不正确")
    user.password_hash = hash_password(payload.new_password)
    db.commit()
    return MessageOut(message="密码已修改")


@router.get("/tts-settings", response_model=UserTtsSettings)
def get_tts_settings(user: Annotated[User, Depends(get_current_user)]) -> UserTtsSettings:
    return UserTtsSettings(**get_user_tts_settings(user))


@router.put("/tts-settings", response_model=UserTtsSettings)
def put_tts_settings(
    payload: UserTtsSettings,
    db: Annotated[Session, Depends(get_db)],
    user: Annotated[User, Depends(get_current_user)],
) -> UserTtsSettings:
    saved = save_user_tts_settings(db, user, payload.model_dump())
    return UserTtsSettings(**saved)

