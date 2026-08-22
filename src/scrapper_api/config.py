"""Runtime settings for the scrapper web API, loaded from environment variables."""

from __future__ import annotations

from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Environment-driven configuration for the FastAPI backend.

    All fields can be overridden via environment variables (or a local ``.env``
    file) using the same name, e.g. ``DATA_DIR=/srv/data``.
    """

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    data_dir: Path = Path("./data")
    webapp_username: str = "admin"
    webapp_password_hash: str = ""
    session_secret: str = "insecure-development-secret-change-me"  # noqa: S105 -- dev fallback only
    token_ttl_seconds: int = 60 * 60 * 8
    cors_origins: list[str] = ["http://localhost:5173"]
    max_concurrency: int = 5
    min_delay: float = 0.2

    @property
    def sessions_dir(self) -> Path:
        """Return the directory holding one subdirectory per scrape session."""
        return self.data_dir / "sessions"

    @property
    def db_path(self) -> Path:
        """Return the path to the SQLite database file."""
        return self.data_dir / "sessions.db"


def get_settings() -> Settings:
    """Build a fresh :class:`Settings` instance from the current environment.

    Returns:
        A newly constructed settings object.
    """
    return Settings()
