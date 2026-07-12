from datetime import datetime, timezone
from enum import Enum

from sqlalchemy import (
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class UserRole(str, Enum):
    admin = "admin"
    user = "user"


class BookVisibility(str, Enum):
    public = "public"
    private = "private"


class JobStatus(str, Enum):
    pending = "pending"
    running = "running"
    success = "success"
    failed = "failed"


class JobType(str, Enum):
    parse = "parse"


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    username: Mapped[str] = mapped_column(String(64), unique=True, index=True, nullable=False)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    role: Mapped[str] = mapped_column(String(16), default=UserRole.user.value, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    books: Mapped[list["Book"]] = relationship(back_populates="owner")
    progress_records: Mapped[list["PlaybackProgress"]] = relationship(back_populates="user")


class AppSettings(Base):
    __tablename__ = "settings"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    registration_enabled: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    invite_required: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    invite_code: Mapped[str | None] = mapped_column(String(128), nullable=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)


class Book(Base):
    __tablename__ = "books"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    author: Mapped[str | None] = mapped_column(String(255), nullable=True)
    visibility: Mapped[str] = mapped_column(String(16), default=BookVisibility.private.value, nullable=False)
    owner_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    source_filename: Mapped[str | None] = mapped_column(String(255), nullable=True)
    source_path: Mapped[str | None] = mapped_column(String(512), nullable=True)
    encoding: Mapped[str | None] = mapped_column(String(32), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    owner: Mapped[User | None] = relationship(back_populates="books")
    chapters: Mapped[list["Chapter"]] = relationship(
        back_populates="book", cascade="all, delete-orphan", order_by="Chapter.index"
    )


class Chapter(Base):
    __tablename__ = "chapters"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    book_id: Mapped[int] = mapped_column(ForeignKey("books.id", ondelete="CASCADE"), nullable=False, index=True)
    index: Mapped[int] = mapped_column(Integer, nullable=False)
    title: Mapped[str] = mapped_column(String(512), nullable=False)

    book: Mapped[Book] = relationship(back_populates="chapters")
    segments: Mapped[list["Segment"]] = relationship(
        back_populates="chapter", cascade="all, delete-orphan", order_by="Segment.index"
    )


class Segment(Base):
    __tablename__ = "segments"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    chapter_id: Mapped[int] = mapped_column(ForeignKey("chapters.id", ondelete="CASCADE"), nullable=False, index=True)
    index: Mapped[int] = mapped_column(Integer, nullable=False)
    text: Mapped[str] = mapped_column(Text, nullable=False)
    char_count: Mapped[int] = mapped_column(Integer, default=0)

    chapter: Mapped[Chapter] = relationship(back_populates="segments")


class PlaybackProgress(Base):
    __tablename__ = "playback_progress"
    __table_args__ = (UniqueConstraint("user_id", "book_id", name="uq_progress_user_book"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    book_id: Mapped[int] = mapped_column(ForeignKey("books.id", ondelete="CASCADE"), nullable=False, index=True)
    chapter_id: Mapped[int | None] = mapped_column(ForeignKey("chapters.id", ondelete="SET NULL"), nullable=True)
    segment_index: Mapped[int] = mapped_column(Integer, default=0)
    position_seconds: Mapped[float] = mapped_column(Float, default=0.0)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)

    user: Mapped[User] = relationship(back_populates="progress_records")
    book: Mapped[Book] = relationship()
    chapter: Mapped[Chapter | None] = relationship()


class Job(Base):
    __tablename__ = "jobs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    type: Mapped[str] = mapped_column(String(32), default=JobType.parse.value, nullable=False)
    status: Mapped[str] = mapped_column(String(32), default=JobStatus.pending.value, nullable=False)
    book_id: Mapped[int | None] = mapped_column(ForeignKey("books.id", ondelete="SET NULL"), nullable=True)
    message: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)

    book: Mapped[Book | None] = relationship()
