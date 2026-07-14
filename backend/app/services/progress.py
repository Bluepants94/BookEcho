from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from app.models import Chapter, PlaybackProgress


def validate_progress_payload(
    db: Session,
    *,
    book_id: int,
    chapter_id: int | None,
    segment_index: int,
) -> Chapter:
    """Validate progress chapter ownership and segment_index bounds.

    chapter_id is required for per-chapter progress storage.
    Returns the validated Chapter row.
    """
    if segment_index < 0:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="segment_index 无效",
        )
    if chapter_id is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="chapter_id 必填",
        )
    chapter = (
        db.query(Chapter)
        .filter(Chapter.id == chapter_id, Chapter.book_id == book_id)
        .first()
    )
    if not chapter:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="章节不存在",
        )
    return chapter


def get_chapter_progress(
    db: Session,
    *,
    user_id: int,
    book_id: int,
    chapter_id: int,
) -> PlaybackProgress | None:
    return (
        db.query(PlaybackProgress)
        .filter(
            PlaybackProgress.user_id == user_id,
            PlaybackProgress.book_id == book_id,
            PlaybackProgress.chapter_id == chapter_id,
        )
        .first()
    )


def get_latest_book_progress(
    db: Session,
    *,
    user_id: int,
    book_id: int,
) -> PlaybackProgress | None:
    return (
        db.query(PlaybackProgress)
        .filter(
            PlaybackProgress.user_id == user_id,
            PlaybackProgress.book_id == book_id,
        )
        .order_by(PlaybackProgress.updated_at.desc(), PlaybackProgress.id.desc())
        .first()
    )


def list_book_progress(
    db: Session,
    *,
    user_id: int,
    book_id: int,
) -> list[PlaybackProgress]:
    return (
        db.query(PlaybackProgress)
        .filter(
            PlaybackProgress.user_id == user_id,
            PlaybackProgress.book_id == book_id,
        )
        .order_by(PlaybackProgress.updated_at.desc(), PlaybackProgress.id.desc())
        .all()
    )


def upsert_chapter_progress(
    db: Session,
    *,
    user_id: int,
    book_id: int,
    chapter_id: int,
    segment_index: int,
    position_seconds: float,
) -> PlaybackProgress:
    row = get_chapter_progress(db, user_id=user_id, book_id=book_id, chapter_id=chapter_id)
    if not row:
        row = PlaybackProgress(user_id=user_id, book_id=book_id, chapter_id=chapter_id)
        db.add(row)
    row.segment_index = segment_index
    row.position_seconds = position_seconds
    db.commit()
    db.refresh(row)
    return row
