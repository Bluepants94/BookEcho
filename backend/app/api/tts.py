from typing import Annotated, AsyncIterator

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session, joinedload

from app.db import get_db
from app.models import Chapter, User
from app.schemas import TTSRequest
from app.services.auth import get_current_user
from app.services.books import require_book_read
from app.services.tts import synthesize_speech

router = APIRouter(prefix="/tts", tags=["tts"])


@router.post("/synthesize")
async def synthesize(
    payload: TTSRequest,
    db: Annotated[Session, Depends(get_db)],
    user: Annotated[User, Depends(get_current_user)],
):
    require_book_read(db, payload.book_id, user)
    chapter = (
        db.query(Chapter)
        .options(joinedload(Chapter.segments))
        .filter(Chapter.id == payload.chapter_id, Chapter.book_id == payload.book_id)
        .first()
    )
    if not chapter:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="章节不存在")

    segment = next((s for s in chapter.segments if s.index == payload.segment_index), None)
    if segment is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="段落不存在")

    if not segment.text.strip():
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="段落内容为空")

    audio, content_type = await synthesize_speech(
        user_id=user.id,
        base_url=payload.base_url,
        api_key=payload.api_key,
        model=payload.model,
        text=segment.text,
        voice=payload.voice,
        speed=payload.speed,
        provider=payload.provider,
        style=payload.style,
        audio_format=payload.audio_format,
    )

    async def audio_iter() -> AsyncIterator[bytes]:
        chunk_size = 64 * 1024
        for i in range(0, len(audio), chunk_size):
            yield audio[i : i + chunk_size]

    return StreamingResponse(
        audio_iter(),
        media_type=content_type,
        headers={"Cache-Control": "no-store"},
    )

