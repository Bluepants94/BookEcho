from typing import Annotated

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.db import get_db
from app.models import PlaybackProgress, User
from app.schemas import PlaybackProgressUpdate, ProgressOut
from app.services.auth import get_current_user
from app.services.books import require_book_read
from app.services.progress import validate_progress_payload

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
    require_book_read(db, book_id, user)
    query = db.query(PlaybackProgress).filter(
        PlaybackProgress.user_id == user.id,
        PlaybackProgress.book_id == book_id,
    )
    if chapter_id is not None:
        query = query.filter(PlaybackProgress.chapter_id == chapter_id)
    row = query.first()
    # If filtered by chapter and no row, still return empty progress for that book.
    if not row and chapter_id is not None:
        # fall back to book-level progress if chapter filter misses
        row = (
            db.query(PlaybackProgress)
            .filter(PlaybackProgress.user_id == user.id, PlaybackProgress.book_id == book_id)
            .first()
        )
    return _progress_out(row, book_id)


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
    row = (
        db.query(PlaybackProgress)
        .filter(PlaybackProgress.user_id == user.id, PlaybackProgress.book_id == payload.book_id)
        .first()
    )
    if not row:
        row = PlaybackProgress(user_id=user.id, book_id=payload.book_id)
        db.add(row)
    row.chapter_id = payload.chapter_id
    row.segment_index = payload.segment_index
    row.position_seconds = payload.resolved_position()
    db.commit()
    db.refresh(row)
    return _progress_out(row, payload.book_id)
