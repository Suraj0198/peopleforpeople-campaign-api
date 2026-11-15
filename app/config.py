"""Settings, read from environment variables (or a .env file loaded by the shell / host)."""
import os
from dataclasses import dataclass, field
from functools import lru_cache

AUTH_MODES = {"db", "remote", "dev"}


@dataclass(frozen=True)
class Settings:
    app_env: str
    database_url: str
    auth_mode: str
    auth_base_url: str
    session_cookie: str
    cors_origins: list[str] = field(default_factory=list)
    auto_create_tables: bool = True


def load_settings() -> Settings:
    settings = Settings(
        app_env=os.getenv("APP_ENV", "development").lower(),
        database_url=os.getenv("DATABASE_URL", "sqlite:///./campaigns.db"),
        # db     -> check the sid cookie against the auth service's sessions table (same Neon database)
        # remote -> forward the sid cookie to AUTH_BASE_URL/auth/me
        # dev    -> local testing only: pretend to be a user with the X-Dev-User header ("<id>:<role>")
        auth_mode=os.getenv("AUTH_MODE", "dev").lower(),
        auth_base_url=os.getenv("AUTH_BASE_URL", "https://auth-backend-lb6o.onrender.com").rstrip("/"),
        session_cookie=os.getenv("SESSION_COOKIE", "sid"),
        cors_origins=[o.strip() for o in os.getenv("CORS_ORIGINS", "http://localhost:5173").split(",") if o.strip()],
        auto_create_tables=os.getenv("AUTO_CREATE_TABLES", "true").lower() in {"1", "true", "yes"},
    )
    if settings.auth_mode not in AUTH_MODES:
        raise RuntimeError(f"AUTH_MODE must be one of {sorted(AUTH_MODES)}, got '{settings.auth_mode}'")
    if settings.auth_mode == "dev" and settings.app_env == "production":
        raise RuntimeError("AUTH_MODE=dev lets anyone act as any user. It is not allowed when APP_ENV=production.")
    return settings


@lru_cache
def get_settings() -> Settings:
    return load_settings()
