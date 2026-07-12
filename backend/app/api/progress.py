from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.db import get_db
from app.models import PlaybackProgress, User
from app.schemas import ProgressOut, ProgressUpdate
from app.services.auth import get_current_user
from app.services.books import require_book_read
from app.services.progress import validate_progress_payload

router = APIRouter(prefix="/progress", tags=["progress"])


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


@router.get("/{book_id}", response_model=ProgressOut)
def get_progress(
    book_id: int,
    db: Annotated[Session, Depends(get_db)],
    user: Annotated[User, Depends(get_current_user)],
) -> ProgressOut:
    require_book_read(db, book_id, user)
    row = (
        db.query(PlaybackProgress)
        .filter(PlaybackProgress.user_id == user.id, PlaybackProgress.book_id == book_id)
        .first()
    )
    return _progress_out(row, book_id)


@router.put("/{book_id}", response_model=ProgressOut)
def put_progress(
    book_id: int,
    payload: ProgressUpdate,
    db: Annotated[Session, Depends(get_db)],
    user: Annotated[User, Depends(get_current_user)],
) -> ProgressOut:
    require_book_read(db, book_id, user)
    validate_progress_payload(
        db,
        book_id=book_id,
        chapter_id=payload.chapter_id,
        segment_index=payload.segment_index,
    )
    row = (
        db.query(PlaybackProgress)
        .filter(PlaybackProgress.user_id == user.id, PlaybackProgress.book_id == book_id)
        .first()
    )
    if not row:
        row = PlaybackProgress(user_id=user.id, book_id=book_id)
        db.add(row)
    row.chapter_id = payload.chapter_id
    row.segment_index = payload.segment_index
    row.position_seconds = payload.resolved_position()
    db.commit()
    db.refresh(row)
    return _progress_out(row, book_id)
