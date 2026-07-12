from fastapi import HTTPException, status
from sqlalchemy.orm import Session
import shutil

from app.config import get_settings
from app.models import Book, User, UserRole


def user_can_read_book(user: User | None, book: Book) -> bool:
    if user is None:
        return False
    if user.role == UserRole.admin.value:
        return True
    return book.owner_id == user.id


def get_book_or_404(db: Session, book_id: int) -> Book:
    book = db.query(Book).filter(Book.id == book_id).first()
    if not book:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="书籍不存在")
    return book


def require_book_read(db: Session, book_id: int, user: User) -> Book:
    book = get_book_or_404(db, book_id)
    if not user_can_read_book(user, book):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="无权访问该书籍")
    return book


def require_book_manage(db: Session, book_id: int, user: User) -> Book:
    book = get_book_or_404(db, book_id)
    if user.role == UserRole.admin.value:
        return book
    if book.owner_id == user.id:
        return book
    raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="无权管理该书籍")


def cleanup_book_files(book: Book) -> None:
    """Remove on-disk directory for a book if present."""
    owner_id = book.owner_id
    if not owner_id:
        return
    settings = get_settings()
    book_dir = settings.book_dir(owner_id, book.id)
    if book_dir.exists():
        shutil.rmtree(book_dir, ignore_errors=True)
