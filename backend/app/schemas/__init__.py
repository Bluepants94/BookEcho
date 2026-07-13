from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, computed_field


class Token(BaseModel):
    access_token: str
    token_type: str = "bearer"


class UserBase(BaseModel):
    username: str = Field(min_length=3, max_length=64)


class UserCreate(UserBase):
    password: str = Field(min_length=6, max_length=128)
    invite_code: str | None = None


class AdminUserCreate(UserBase):
    password: str = Field(min_length=6, max_length=128)
    role: Literal["admin", "user"] | None = None


class UserLogin(BaseModel):
    username: str
    password: str


class PasswordChange(BaseModel):
    old_password: str = Field(min_length=1, max_length=128)
    new_password: str = Field(min_length=6, max_length=128)


class UserTtsSettings(BaseModel):
    """Per-user TTS + cache preferences persisted server-side."""

    base_url: str = Field(default="", max_length=512)
    api_key: str = Field(default="", max_length=512)
    model: str = Field(default="", max_length=128)
    voice: str = Field(default="", max_length=64)
    provider: str = Field(default="auto", max_length=32)
    style: str = Field(default="", max_length=1000)
    audio_format: str = Field(default="pcm16", max_length=32)
    cache_chapters: int = Field(default=3, ge=0, le=10)


class UserUpdate(BaseModel):
    password: str | None = Field(default=None, min_length=6, max_length=128)
    role: Literal["admin", "user"] | None = None
    is_active: bool | None = None


class UserOut(UserBase):
    model_config = ConfigDict(from_attributes=True)

    id: int
    role: str
    is_active: bool
    created_at: datetime


class SettingsOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    registration_enabled: bool
    invite_required: bool
    invite_code: str | None = None
    updated_at: datetime | None = None


class SettingsUpdate(BaseModel):
    registration_enabled: bool | None = None
    invite_required: bool | None = None
    invite_code: str | None = None


class PublicSettingsOut(BaseModel):
    registration_enabled: bool
    invite_required: bool


class BookOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    title: str
    author: str | None = None
    visibility: str
    owner_id: int | None = None
    source_filename: str | None = None
    encoding: str | None = None
    created_at: datetime

    @computed_field  # type: ignore[prop-decorator]
    @property
    def is_public(self) -> bool:
        return self.visibility == "public"


class BookCreateMeta(BaseModel):
    title: str | None = None
    author: str | None = None
    visibility: Literal["public", "private"] | None = None


class AdminBookUpdate(BaseModel):
    # Public library removed; values are accepted for compatibility but forced private.
    visibility: Literal["private"] | None = None
    is_public: bool | None = None
    title: str | None = None
    author: str | None = None


class SegmentOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    index: int
    text: str
    char_count: int


class ChapterOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    index: int
    title: str
    segments: list[SegmentOut] = []


class ChapterSummary(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    index: int
    title: str
    segment_count: int = 0


class BookDetail(BookOut):
    chapters: list[ChapterSummary] = []


class ProgressOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    book_id: int
    chapter_id: int | None = None
    segment_index: int
    position_seconds: float
    updated_at: datetime | None = None

    @computed_field  # type: ignore[prop-decorator]
    @property
    def offset_seconds(self) -> float:
        return self.position_seconds


class ProgressUpdate(BaseModel):
    chapter_id: int | None = None
    segment_index: int = 0
    position_seconds: float | None = None
    offset_seconds: float | None = None

    def resolved_position(self) -> float:
        if self.position_seconds is not None:
            return float(self.position_seconds)
        if self.offset_seconds is not None:
            return float(self.offset_seconds)
        return 0.0


class PlaybackProgressUpdate(BaseModel):
    book_id: int
    chapter_id: int | None = None
    segment_index: int = 0
    position_seconds: float | None = None
    offset_seconds: float | None = None

    def resolved_position(self) -> float:
        if self.position_seconds is not None:
            return float(self.position_seconds)
        if self.offset_seconds is not None:
            return float(self.offset_seconds)
        return 0.0


class JobOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    type: str
    status: str
    book_id: int | None = None
    message: str | None = None
    created_at: datetime
    updated_at: datetime


class TTSRequest(BaseModel):
    base_url: str = Field(max_length=512)
    api_key: str = Field(max_length=512)
    model: str = Field(max_length=128)
    voice: str | None = Field(default=None, max_length=64)
    speed: float | None = Field(default=None, ge=0.25, le=4.0)
    # auto | mimo | openai
    provider: str | None = Field(default=None, max_length=32)
    # Mimo style prompt (user message)
    style: str | None = Field(default=None, max_length=1000)
    # Mimo audio.format, default pcm16
    audio_format: str | None = Field(default=None, max_length=32)
    book_id: int
    chapter_id: int
    segment_index: int


class MessageOut(BaseModel):
    message: str


class SystemInfoOut(BaseModel):
    app_name: str
    database_url: str
    user_count: int
    book_count: int
    job_count: int
    version: str
