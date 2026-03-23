import os
from dotenv import load_dotenv

load_dotenv(override=True)


class Settings:
    DATABASE_URL: str = os.getenv("DATABASE_URL", "sqlite:///roofing_scheduler.db")
    JOBNIMBUS_API_KEY: str = os.getenv("JOBNIMBUS_API_KEY", "")
    JOBNIMBUS_BASE_URL: str = os.getenv("JOBNIMBUS_BASE_URL", "https://app.jobnimbus.com/api1")
    ANTHROPIC_API_KEY: str = os.getenv("ANTHROPIC_API_KEY", "")
    GOOGLE_MAPS_API_KEY: str = os.getenv("GOOGLE_MAPS_API_KEY", "")
    BAMWX_API_KEY: str = os.getenv("BAMWX_API_KEY", "")
    BAMWX_BASE_URL: str = os.getenv("BAMWX_BASE_URL", "")


settings = Settings()
