"""Test setup: never touch a real database file or a real secret."""
import os

# Must be set before backend.database is imported (it builds the engine at import time)
os.environ.setdefault("DATABASE_URL", "sqlite://")
os.environ.setdefault("EMAIL_UNSUBSCRIBE_SECRET", "test-secret")
os.environ.pop("EMAIL_MODE", None)
