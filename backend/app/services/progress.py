from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from app.models import Chapter


def validate_progress_payload(
    db: Session,
    *,
    book_id: int,
    chapter_id: int | None,
    segment_index: int,
) -> None:
    """Validate progress chapter ownership and segment_index bounds."""
    if segment_index < 0:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="segment_index 无效",
        )
    if chapter_id is None:
        return
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
