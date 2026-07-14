from collections.abc import Generator

from sqlalchemy import create_engine, event, inspect, text
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from app.config import get_settings

settings = get_settings()

connect_args = {"check_same_thread": False} if settings.database_url.startswith("sqlite") else {}
engine = create_engine(settings.database_url, connect_args=connect_args, pool_pre_ping=True)


if settings.database_url.startswith("sqlite"):

    @event.listens_for(engine, "connect")
    def set_sqlite_pragma(dbapi_connection, connection_record):  # noqa: ARG001
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()


SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


class Base(DeclarativeBase):
    pass


def get_db() -> Generator[Session, None, None]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def _ensure_sqlite_columns() -> None:
    """Lightweight SQLite schema upgrades for existing deployments."""
    if not settings.database_url.startswith("sqlite"):
        return
    try:
        inspector = inspect(engine)
        tables = set(inspector.get_table_names())
    except Exception:  # noqa: BLE001
        return
    if "books" in tables:
        columns = {col["name"] for col in inspector.get_columns("books")}
        if "source_path" not in columns:
            with engine.begin() as conn:
                conn.execute(text("ALTER TABLE books ADD COLUMN source_path VARCHAR(512)"))
    if "users" in tables:
        columns = {col["name"] for col in inspector.get_columns("users")}
        if "tts_settings_json" not in columns:
            with engine.begin() as conn:
                conn.execute(text("ALTER TABLE users ADD COLUMN tts_settings_json TEXT"))
    if "playback_progress" in tables:
        _migrate_playback_progress_to_per_chapter(inspector)


def _migrate_playback_progress_to_per_chapter(inspector) -> None:
    """Upgrade book-level progress uniqueness to per-chapter rows.

    Old schema: UNIQUE(user_id, book_id)
    New schema: UNIQUE(user_id, book_id, chapter_id) with non-null chapter_id
    """
    try:
        uniques = inspector.get_unique_constraints("playback_progress")
        indexes = inspector.get_indexes("playback_progress")
    except Exception:  # noqa: BLE001
        return

    names = {u.get("name") for u in uniques} | {i.get("name") for i in indexes}
    try:
        with engine.connect() as conn:
            pragma_rows = conn.execute(text("PRAGMA index_list('playback_progress')")).fetchall()
            names |= {r[1] for r in pragma_rows}
    except Exception:  # noqa: BLE001
        pass

    # Already migrated / created with new unique constraint.
    if "uq_progress_user_book_chapter" in names and "uq_progress_user_book" not in names:
        return

    column_sets = {tuple(u.get("column_names") or []) for u in uniques}
    if ("user_id", "book_id", "chapter_id") in column_sets and "uq_progress_user_book" not in names:
        return

    # Only rebuild when the legacy book-level unique is still present.
    needs_rebuild = "uq_progress_user_book" in names or ("user_id", "book_id") in column_sets
    if not needs_rebuild:
        return

    with engine.begin() as conn:
        conn.execute(text("PRAGMA foreign_keys=OFF"))
        conn.execute(text(
            """
            CREATE TABLE IF NOT EXISTS playback_progress_v2 (
                id INTEGER NOT NULL PRIMARY KEY,
                user_id INTEGER NOT NULL,
                book_id INTEGER NOT NULL,
                chapter_id INTEGER NOT NULL,
                segment_index INTEGER NOT NULL DEFAULT 0,
                position_seconds FLOAT NOT NULL DEFAULT 0.0,
                updated_at DATETIME,
                CONSTRAINT uq_progress_user_book_chapter UNIQUE (user_id, book_id, chapter_id),
                FOREIGN KEY(user_id) REFERENCES users (id) ON DELETE CASCADE,
                FOREIGN KEY(book_id) REFERENCES books (id) ON DELETE CASCADE,
                FOREIGN KEY(chapter_id) REFERENCES chapters (id) ON DELETE CASCADE
            )
            """
        ))
        # Keep only rows with a real chapter_id; for duplicates take the newest by updated_at/id.
        conn.execute(text(
            """
            INSERT INTO playback_progress_v2 (
                id, user_id, book_id, chapter_id, segment_index, position_seconds, updated_at
            )
            SELECT
                p.id,
                p.user_id,
                p.book_id,
                p.chapter_id,
                COALESCE(p.segment_index, 0),
                COALESCE(p.position_seconds, 0.0),
                p.updated_at
            FROM playback_progress p
            INNER JOIN (
                SELECT user_id, book_id, chapter_id, MAX(id) AS max_id
                FROM playback_progress
                WHERE chapter_id IS NOT NULL
                GROUP BY user_id, book_id, chapter_id
            ) latest
              ON p.id = latest.max_id
            """
        ))
        conn.execute(text("DROP TABLE playback_progress"))
        conn.execute(text("ALTER TABLE playback_progress_v2 RENAME TO playback_progress"))
        conn.execute(text(
            "CREATE INDEX IF NOT EXISTS ix_playback_progress_user_id ON playback_progress (user_id)"
        ))
        conn.execute(text(
            "CREATE INDEX IF NOT EXISTS ix_playback_progress_book_id ON playback_progress (book_id)"
        ))
        conn.execute(text(
            "CREATE INDEX IF NOT EXISTS ix_playback_progress_chapter_id ON playback_progress (chapter_id)"
        ))
        conn.execute(text("PRAGMA foreign_keys=ON"))


def init_db() -> None:
    from app import models  # noqa: F401

    Base.metadata.create_all(bind=engine)
    _ensure_sqlite_columns()
