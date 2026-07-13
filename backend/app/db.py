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


def init_db() -> None:
    from app import models  # noqa: F401

    Base.metadata.create_all(bind=engine)
    _ensure_sqlite_columns()
