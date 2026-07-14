from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


_DEFAULT_DATA_DIR = (Path(__file__).resolve().parent.parent / "data").resolve()


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    app_name: str = "BookEcho"
    api_prefix: str = "/api"
    data_dir: str = str(_DEFAULT_DATA_DIR)
    database_url: str = f"sqlite:///{(_DEFAULT_DATA_DIR / 'bookecho.db').as_posix()}"
    secret_key: str = "change-me-in-production-bookecho-secret"
    access_token_expire_minutes: int = 60 * 24 * 7
    algorithm: str = "HS256"
    cors_origins: str = "*"
    max_upload_size_mb: int = 20
    tts_max_concurrent_per_user: int = 3
    tts_allow_private_urls: bool = False
    bootstrap_admin_username: str | None = None
    bootstrap_admin_password: str | None = None
    # Process-local sliding windows. Tune via env if needed.
    auth_rate_limit_per_minute: int = 30
    tts_rate_limit_per_minute: int = 120
    parse_max_workers: int = 2
    # When true, parse runs in-process immediately (useful for tests).
    parse_inline: bool = False

    @property
    def data_path(self) -> Path:
        return Path(self.data_dir).expanduser().resolve()

    def user_dir(self, user_id: int) -> Path:
        return self.data_path / "users" / str(user_id)

    def book_dir(self, user_id: int, book_id: int) -> Path:
        return self.user_dir(user_id) / "books" / str(book_id)

    def book_relative_dir(self, user_id: int, book_id: int) -> str:
        return f"users/{user_id}/books/{book_id}"

    @property
    def cors_origin_list(self) -> list[str]:
        if not self.cors_origins or self.cors_origins.strip() == "*":
            return ["*"]
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]

    @property
    def max_upload_bytes(self) -> int:
        return self.max_upload_size_mb * 1024 * 1024


@lru_cache
def get_settings() -> Settings:
    return Settings()
