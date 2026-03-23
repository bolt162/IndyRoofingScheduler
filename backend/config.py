import os
from dotenv import load_dotenv

load_dotenv(override=True)


def _get_secret(key: str, default: str = "") -> str:
    """Read from Streamlit secrets (Cloud) first, then env vars (local)."""
    try:
        import streamlit as st
        if hasattr(st, "secrets") and key in st.secrets:
            return st.secrets[key]
    except Exception:
        pass
    return os.getenv(key, default)


class Settings:
    DATABASE_URL: str = _get_secret("DATABASE_URL", "sqlite:///roofing_scheduler.db")
    JOBNIMBUS_API_KEY: str = _get_secret("JOBNIMBUS_API_KEY")
    JOBNIMBUS_BASE_URL: str = _get_secret("JOBNIMBUS_BASE_URL", "https://app.jobnimbus.com/api1")
    ANTHROPIC_API_KEY: str = _get_secret("ANTHROPIC_API_KEY")
    GOOGLE_MAPS_API_KEY: str = _get_secret("GOOGLE_MAPS_API_KEY")
    BAMWX_API_KEY: str = _get_secret("BAMWX_API_KEY")
    BAMWX_BASE_URL: str = _get_secret("BAMWX_BASE_URL")


settings = Settings()
