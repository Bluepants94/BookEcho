from __future__ import annotations

import logging
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from sqlalchemy.orm import Session, joinedload

from app.config import get_settings
from app.db import SessionLocal
from app.models import Book, Chapter, Job, JobStatus, Segment
from app.services.parser import format_parse_job_message, parse_book

logger = logging.getLogger("bookecho.parse")
settings = get_settings()
_executor = ThreadPoolExecutor(max_workers=max(1, int(settings.parse_max_workers or 2)))


def _safe_under_data(path: Path) -> bool:
    try:
        path.resolve().relative_to(settings.data_path.resolve())
        return True
    except Exception:
        return False


def enqueue_book_parse(book_id: int, job_id: int, source_path: str | None) -> None:
    cfg = get_settings()
    if cfg.parse_inline:
        _run_parse_job(book_id, job_id, source_path)
        return
    _executor.submit(_run_parse_job, book_id, job_id, source_path)


def parse_book_from_bytes(db: Session, book: Book, job: Job, data: bytes) -> None:
    """Run parse against the caller's DB session (used by inline/test path)."""
    job.status = JobStatus.running.value
    job.message = "解析中"
    db.flush()
    result = parse_book(data)
    book.chapters.clear()
    db.flush()
    book.encoding = result.encoding
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
    job.status = JobStatus.success.value
    job.message = format_parse_job_message(result)


def _run_parse_job(book_id: int, job_id: int, source_path: str | None) -> None:
    db: Session = SessionLocal()
    try:
        job = db.query(Job).filter(Job.id == job_id).first()
        book = (
            db.query(Book)
            .options(joinedload(Book.chapters).joinedload(Chapter.segments))
            .filter(Book.id == book_id)
            .first()
        )
        if not job or not book:
            return

        if not source_path:
            job.status = JobStatus.failed.value
            job.message = "解析失败: 缺少源文件"
            db.commit()
            return

        rel = source_path.replace("\\", "/").lstrip("/")
        if ".." in rel.split("/"):
            job.status = JobStatus.failed.value
            job.message = "解析失败: 源路径非法"
            db.commit()
            return
        path = (get_settings().data_path / rel).resolve()
        if not _safe_under_data(path) or not path.is_file():
            job.status = JobStatus.failed.value
            job.message = "解析失败: 源文件不存在"
            db.commit()
            return

        data = path.read_bytes()
        parse_book_from_bytes(db, book, job, data)
        db.commit()
    except Exception as exc:  # noqa: BLE001
        logger.exception("async parse failed book_id=%s job_id=%s", book_id, job_id)
        try:
            db.rollback()
            job = db.query(Job).filter(Job.id == job_id).first()
            if job:
                job.status = JobStatus.failed.value
                job.message = f"解析失败: {exc}"
                db.commit()
        except Exception:  # noqa: BLE001
            db.rollback()
    finally:
        db.close()
