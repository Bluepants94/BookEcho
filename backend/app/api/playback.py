from typing import Annotated

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.db import get_db
from app.models import PlaybackProgress, User
from app.schemas import PlaybackProgressUpdate, ProgressOut
from app.services.auth import get_current_user
from app.services.books import require_book_read
from app.services.progress import (
    get_chapter_progress,
    get_latest_book_progress,
    list_book_progress,
    upsert_chapter_progress,
    validate_progress_payload,
)

router = APIRouter(prefix="/playback", tags=["playback"])


def _progress_out(row: PlaybackProgress | None, book_id: int) -> ProgressOut:
    if not row:
        return ProgressOut(book_id=book_id, chapter_id=None, segment_index=0, position_seconds=0.0)
    return ProgressOut(
        book_id=row.book_id,
        chapter_id=row.chapter_id,
        segment_index=row.segment_index,
        position_seconds=row.position_seconds,
        updated_at=row.updated_at,
    )


@router.get("/progress", response_model=ProgressOut)
def get_playback_progress(
    db: Annotated[Session, Depends(get_db)],
    user: Annotated[User, Depends(get_current_user)],
    book_id: int = Query(...),
    chapter_id: int | None = Query(default=None),
) -> ProgressOut:
    """Return chapter progress when chapter_id is given; otherwise latest book progress."""
    require_book_read(db, book_id, user)
    if chapter_id is not None:
        row = get_chapter_progress(db, user_id=user.id, book_id=book_id, chapter_id=chapter_id)
        return _progress_out(row, book_id)
    row = get_latest_book_progress(db, user_id=user.id, book_id=book_id)
    return _progress_out(row, book_id)


@router.get("/progress/all", response_model=list[ProgressOut])
def list_playback_progress(
    db: Annotated[Session, Depends(get_db)],
    user: Annotated[User, Depends(get_current_user)],
    book_id: int = Query(...),
) -> list[ProgressOut]:
    """List per-chapter progress for a book (used by book detail progress bars)."""
    require_book_read(db, book_id, user)
    rows = list_book_progress(db, user_id=user.id, book_id=book_id)
    return [_progress_out(row, book_id) for row in rows]


@router.put("/progress", response_model=ProgressOut)
def put_playback_progress(
    payload: PlaybackProgressUpdate,
    db: Annotated[Session, Depends(get_db)],
    user: Annotated[User, Depends(get_current_user)],
) -> ProgressOut:
    require_book_read(db, payload.book_id, user)
    validate_progress_payload(
        db,
        book_id=payload.book_id,
        chapter_id=payload.chapter_id,
        segment_index=payload.segment_index,
    )
    row = upsert_chapter_progress(
        db,
        user_id=user.id,
        book_id=payload.book_id,
        chapter_id=payload.chapter_id,
        segment_index=payload.segment_index,
        position_seconds=payload.resolved_position(),
    )
    return _progress_out(row, payload.book_id)
