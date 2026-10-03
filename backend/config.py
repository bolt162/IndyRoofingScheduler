import os
from dotenv import load_dotenv

load_dotenv(override=True)


def _get_secret(key: str, default: str = "") -> str:
    """Read from env vars."""
    return os.getenv(key, default)


def _fix_database_url(url: str) -> str:
    """Point Postgres URLs at the psycopg2 driver.

    Railway hands out postgres:// (SQLAlchemy requires postgresql://), and SQLAlchemy 2.1+
    defaults a bare postgresql:// to psycopg v3, which isn't installed — only
    psycopg2-binary is. URLs that already name a driver are left alone.
    """
    for prefix in ("postgres://", "postgresql://"):
        if url.startswith(prefix):
            return "postgresql+psycopg2://" + url[len(prefix):]
    return url


class Settings:
    DATABASE_URL: str = _fix_database_url(_get_secret("DATABASE_URL", "sqlite:///roofing_scheduler.db"))
    JOBNIMBUS_API_KEY: str = _get_secret("JOBNIMBUS_API_KEY")
    JOBNIMBUS_BASE_URL: str = _get_secret("JOBNIMBUS_BASE_URL", "https://app.jobnimbus.com/api1")
    ANTHROPIC_API_KEY: str = _get_secret("ANTHROPIC_API_KEY")
    # Claude model ID used by scoring + note scanning. Override per-env without a code change.
    ANTHROPIC_MODEL: str = _get_secret("ANTHROPIC_MODEL", "claude-sonnet-5")
    GOOGLE_MAPS_API_KEY: str = _get_secret("GOOGLE_MAPS_API_KEY")
    BAMWX_API_KEY: str = _get_secret("BAMWX_API_KEY")
    BAMWX_API_SECRET: str = _get_secret("BAMWX_API_SECRET")
    BAMWX_BASE_URL: str = _get_secret("BAMWX_BASE_URL", "https://api.claritywx.com")

    # Auth — Clerk handles user identity and approval state.
    # CLERK_JWKS_URL: Clerk dashboard → API Keys → "Show JWT public key" / JWKS endpoint
    # CLERK_JWT_ISSUER: the URL the JWT claims as 'iss' — Clerk dashboard shows it
    # (Typically https://<your-instance>.clerk.accounts.dev)
    CLERK_JWKS_URL: str = _get_secret("CLERK_JWKS_URL", "")
    CLERK_JWT_ISSUER: str = _get_secret("CLERK_JWT_ISSUER", "")


settings = Settings()
