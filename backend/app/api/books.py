from typing import Annotated, Literal
from pathlib import Path
import re

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status
from sqlalchemy.orm import Session, joinedload

from app.config import get_settings
from app.db import get_db
from app.models import (
    Book,
    BookVisibility,
    Chapter,
    Job,
    JobStatus,
    JobType,
    Segment,
    User,
    UserRole,
)
from app.schemas import BookDetail, BookOut, ChapterOut, ChapterSummary, MessageOut, SegmentOut
from app.services.auth import get_current_admin, get_current_user
from app.services.books import cleanup_book_files, require_book_manage, require_book_read
from app.services.parser import (
    format_parse_job_message,
    parse_book,
    rebuild_book_text_from_parts,
    reparse_stored_text,
)
from app.services.parse_jobs import enqueue_book_parse, parse_book_from_bytes

router = APIRouter(prefix="/books", tags=["books"])
settings = get_settings()


def _chapter_summaries(book: Book) -> list[ChapterSummary]:
    return [
        ChapterSummary(
            id=ch.id,
            index=ch.index,
            title=ch.title,
            segment_count=len(ch.segments) if ch.segments is not None else 0,
        )
        for ch in sorted(book.chapters, key=lambda c: c.index)
    ]


def _book_detail(book: Book) -> BookDetail:
    return BookDetail(
        id=book.id,
        title=book.title,
        author=book.author,
        visibility=book.visibility,
        owner_id=book.owner_id,
        source_filename=book.source_filename,
        encoding=book.encoding,
        created_at=book.created_at,
        chapters=_chapter_summaries(book),
    )


def _safe_filename(name: str | None) -> str:
    """Return a basename-only, path-traversal-safe filename ending with .txt."""
    raw = (name or "book.txt").replace("\\", "/")
    base = Path(raw).name  # drop any directory components
    base = base.replace("..", "")
    base = re.sub(r"[^\w.\u4e00-\u9fff\- ]+", "_", base, flags=re.UNICODE).strip(" ._")
    if not base:
        base = "book.txt"
    if not base.lower().endswith(".txt"):
        base = f"{base}.txt"
    return base


def _resolve_source_file(book: Book) -> Path | None:
    """Resolve a book source file under data_dir. Only controlled relative paths."""
    if not book.source_path or not book.owner_id:
        return None
    rel = book.source_path.replace("\\", "/").lstrip("/")
    if ".." in rel.split("/"):
        return None
    path = (settings.data_path / rel).resolve()
    try:
        path.relative_to(settings.data_path)
    except ValueError:
        return None
    if path.is_file():
        return path
    return None


def _store_book_source(user_id: int, book_id: int, original_filename: str | None, data: bytes) -> str:
    """Persist raw upload bytes and return posix relative path under data_dir."""
    safe_name = _safe_filename(original_filename)
    book_dir = settings.book_dir(user_id, book_id)
    book_dir.mkdir(parents=True, exist_ok=True)
    dest = book_dir / safe_name
    dest.write_bytes(data)
    rel = f"{settings.book_relative_dir(user_id, book_id)}/{safe_name}"
    return rel.replace("\\", "/")




@router.get("", response_model=list[BookOut])
def list_books(
    db: Annotated[Session, Depends(get_db)],
    user: Annotated[User, Depends(get_current_user)],
    scope: Literal["public", "mine", "all"] = "mine",
) -> list[Book]:
    """List books. Public library is removed; only owner private books or admin all."""
    q = db.query(Book)
    if user.role == UserRole.admin.value and scope == "all":
        return q.order_by(Book.id.desc()).all()
    # Default and any other scope: only current user's private books.
    return q.filter(Book.owner_id == user.id).order_by(Book.id.desc()).all()


@router.post("/admin/upload", response_model=BookOut, status_code=status.HTTP_201_CREATED)
async def admin_upload_book(
    db: Annotated[Session, Depends(get_db)],
    admin: Annotated[User, Depends(get_current_admin)],
    file: UploadFile = File(...),
    title: str | None = Form(default=None),
    author: str | None = Form(default=None),
) -> Book:
    # Kept for compatibility; behaves like a normal private upload for the admin user.
    return await _upload_book_impl(db, admin, file, title, author, visibility=None)


async def _upload_book_impl(
    db: Session,
    user: User,
    file: UploadFile,
    title: str | None,
    author: str | None,
    visibility: str | None,
) -> Book:
    if not file.filename or not file.filename.lower().endswith(".txt"):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="仅支持 txt 文件")

    chunks: list[bytes] = []
    total = 0
    while True:
        chunk = await file.read(1024 * 1024)
        if not chunk:
            break
        total += len(chunk)
        if total > settings.max_upload_bytes:
            raise HTTPException(
                status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                detail=f"文件过大，上限 {settings.max_upload_size_mb}MB",
            )
        chunks.append(chunk)
    data = b"".join(chunks)

    # Public library removed: all uploads are private to the owner.
    vis = BookVisibility.private.value

    original_name = file.filename
    book_title = title or (original_name.rsplit(".", 1)[0] if original_name else "未命名")

    book = Book(
        title=book_title,
        author=author,
        visibility=vis,
        owner_id=user.id,
        source_filename=original_name,
        source_path=None,
        encoding=None,
    )
    db.add(book)
    db.flush()

    # Persist source after we have a stable book.id.
    try:
        book.source_path = _store_book_source(user.id, book.id, original_name, data)
    except OSError as exc:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="书籍文件保存失败",
        ) from exc

    # Default: parse asynchronously so large uploads do not block workers.
    # Tests / small deployments may set parse_inline=true to finish in-request.
    job = Job(type=JobType.parse.value, status=JobStatus.pending.value, book_id=book.id, message="排队解析中")
    db.add(job)
    if settings.parse_inline:
        try:
            parse_book_from_bytes(db, book, job, data)
        except Exception as exc:  # noqa: BLE001
            job.status = JobStatus.failed.value
            job.message = f"解析失败: {exc}"
            db.commit()
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="书籍解析失败",
            ) from exc
        db.commit()
        db.refresh(book)
        return book

    db.commit()
    db.refresh(book)
    db.refresh(job)
    enqueue_book_parse(book.id, job.id, book.source_path)
    return book


@router.post("", response_model=BookOut, status_code=status.HTTP_201_CREATED)
@router.post("/upload", response_model=BookOut, status_code=status.HTTP_201_CREATED)
async def upload_book(
    db: Annotated[Session, Depends(get_db)],
    user: Annotated[User, Depends(get_current_user)],
    file: UploadFile = File(...),
    title: str | None = Form(default=None),
    author: str | None = Form(default=None),
    visibility: str | None = Form(default=None),
) -> Book:
    return await _upload_book_impl(db, user, file, title, author, visibility)


@router.get("/{book_id}", response_model=BookDetail)
def get_book(
    book_id: int,
    db: Annotated[Session, Depends(get_db)],
    user: Annotated[User, Depends(get_current_user)],
) -> BookDetail:
    book = (
        db.query(Book)
        .options(joinedload(Book.chapters).joinedload(Chapter.segments))
        .filter(Book.id == book_id)
        .first()
    )
    if not book:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="书籍不存在")
    if not (user.role == UserRole.admin.value or book.owner_id == user.id):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="无权访问该书籍")
    return _book_detail(book)


@router.get("/{book_id}/chapters", response_model=list[ChapterSummary])
def list_chapters(
    book_id: int,
    db: Annotated[Session, Depends(get_db)],
    user: Annotated[User, Depends(get_current_user)],
) -> list[ChapterSummary]:
    book = (
        db.query(Book)
        .options(joinedload(Book.chapters).joinedload(Chapter.segments))
        .filter(Book.id == book_id)
        .first()
    )
    if not book:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="书籍不存在")
    if not (user.role == UserRole.admin.value or book.owner_id == user.id):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="无权访问该书籍")
    return _chapter_summaries(book)


@router.get("/{book_id}/chapters/{chapter_id}", response_model=ChapterOut)
def get_chapter(
    book_id: int,
    chapter_id: int,
    db: Annotated[Session, Depends(get_db)],
    user: Annotated[User, Depends(get_current_user)],
) -> ChapterOut:
    require_book_read(db, book_id, user)
    chapter = (
        db.query(Chapter)
        .options(joinedload(Chapter.segments))
        .filter(Chapter.id == chapter_id, Chapter.book_id == book_id)
        .first()
    )
    if not chapter:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="章节不存在")
    segs = [
        SegmentOut(id=s.id, index=s.index, text=s.text, char_count=s.char_count)
        for s in sorted(chapter.segments, key=lambda x: x.index)
    ]
    return ChapterOut(id=chapter.id, index=chapter.index, title=chapter.title, segments=segs)


@router.get("/{book_id}/chapters/{chapter_id}/segments", response_model=list[SegmentOut])
def list_segments(
    book_id: int,
    chapter_id: int,
    db: Annotated[Session, Depends(get_db)],
    user: Annotated[User, Depends(get_current_user)],
) -> list[SegmentOut]:
    require_book_read(db, book_id, user)
    chapter = (
        db.query(Chapter)
        .options(joinedload(Chapter.segments))
        .filter(Chapter.id == chapter_id, Chapter.book_id == book_id)
        .first()
    )
    if not chapter:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="章节不存在")
    return [
        SegmentOut(id=s.id, index=s.index, text=s.text, char_count=s.char_count)
        for s in sorted(chapter.segments, key=lambda x: x.index)
    ]


@router.post("/{book_id}/reparse", response_model=BookDetail)
def reparse_book(
    book_id: int,
    db: Annotated[Session, Depends(get_db)],
    user: Annotated[User, Depends(get_current_user)],
) -> BookDetail:
    """Rebuild chapter/segment structure, preferring on-disk source when available."""
    book = (
        db.query(Book)
        .options(joinedload(Book.chapters).joinedload(Chapter.segments))
        .filter(Book.id == book_id)
        .first()
    )
    if not book:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="书籍不存在")
    if not (user.role == UserRole.admin.value or book.owner_id == user.id):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="无权管理该书籍")

    source_file = _resolve_source_file(book)
    disk_bytes: bytes | None = None
    if source_file is not None:
        try:
            disk_bytes = source_file.read_bytes()
        except OSError:
            disk_bytes = None

    job = Job(
        type=JobType.parse.value,
        status=JobStatus.running.value,
        book_id=book.id,
        message="重解析中",
    )
    db.add(job)
    db.flush()

    try:
        if disk_bytes is not None:
            result = parse_book(disk_bytes)
        else:
            ordered_chapters = sorted(book.chapters, key=lambda c: c.index)
            parts: list[tuple[str, list[str]]] = []
            for ch in ordered_chapters:
                segs = [
                    s.text
                    for s in sorted(ch.segments, key=lambda x: x.index)
                ]
                parts.append((ch.title, segs))

            if not parts:
                raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="书籍无正文可重解析")

            raw_text = rebuild_book_text_from_parts(parts)
            if not raw_text.strip():
                raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="书籍无正文可重解析")

            result = reparse_stored_text(raw_text, stored_encoding=book.encoding)

        # Replace old chapters/segments in-transaction via ORM cascade.
        book.chapters.clear()
        db.flush()

        for idx, ch in enumerate(result.chapters):
            chapter = Chapter(book_id=book.id, index=idx, title=ch.title)
            db.add(chapter)
            db.flush()
            for sidx, seg_text in enumerate(ch.segments):
                db.add(
                    Segment(
                        chapter_id=chapter.id,
                        index=sidx,
                        text=seg_text,
                        char_count=len(seg_text),
                    )
                )

        book.encoding = result.encoding
        job.status = JobStatus.success.value
        job.message = f"重解析完成：{format_parse_job_message(result)}"
    except HTTPException as exc:
        job.status = JobStatus.failed.value
        job.message = f"重解析失败: {exc.detail}"
        db.commit()
        raise
    except Exception as exc:  # noqa: BLE001
        job.status = JobStatus.failed.value
        job.message = f"重解析失败: {exc}"
        db.commit()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="书籍重解析失败",
        ) from exc

    db.commit()

    book = (
        db.query(Book)
        .options(joinedload(Book.chapters).joinedload(Chapter.segments))
        .filter(Book.id == book_id)
        .first()
    )
    assert book is not None
    return _book_detail(book)


@router.delete("/{book_id}", response_model=MessageOut)
def delete_book(
    book_id: int,
    db: Annotated[Session, Depends(get_db)],
    user: Annotated[User, Depends(get_current_user)],
) -> MessageOut:
    book = require_book_manage(db, book_id, user)
    cleanup_book_files(book)
    db.delete(book)
    db.commit()
    return MessageOut(message="已删除")

