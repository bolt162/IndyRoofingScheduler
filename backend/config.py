import os
from dotenv import load_dotenv

load_dotenv(override=True)


def _get_secret(key: str, default: str = "") -> str:
    """Read from env vars."""
    return os.getenv(key, default)


def _fix_database_url(url: str) -> str:
    """Fix Railway's postgres:// to postgresql:// (SQLAlchemy requires the latter)."""
    if url.startswith("postgres://"):
        return url.replace("postgres://", "postgresql://", 1)
    return url


class Settings:
    DATABASE_URL: str = _fix_database_url(_get_secret("DATABASE_URL", "sqlite:///roofing_scheduler.db"))
    JOBNIMBUS_API_KEY: str = _get_secret("JOBNIMBUS_API_KEY")
    JOBNIMBUS_BASE_URL: str = _get_secret("JOBNIMBUS_BASE_URL", "https://app.jobnimbus.com/api1")
    ANTHROPIC_API_KEY: str = _get_secret("ANTHROPIC_API_KEY")
    GOOGLE_MAPS_API_KEY: str = _get_secret("GOOGLE_MAPS_API_KEY")
    BAMWX_API_KEY: str = _get_secret("BAMWX_API_KEY")
    BAMWX_API_SECRET: str = _get_secret("BAMWX_API_SECRET")
    BAMWX_BASE_URL: str = _get_secret("BAMWX_BASE_URL", "https://api.claritywx.com")


settings = Settings()
