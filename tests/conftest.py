"""Test setup: never touch a real database file or a real secret."""
import os

# Must be set before backend.database is imported (it builds the engine at import time)
os.environ.setdefault("DATABASE_URL", "sqlite://")
os.environ.setdefault("EMAIL_UNSUBSCRIBE_SECRET", "test-secret")
os.environ.pop("EMAIL_MODE", None)


import pytest


@pytest.fixture(autouse=True)
def _no_address_lookups(monkeypatch):
    """Tests never call the real address lookups; tests that need one put in their own."""
    from backend.services import geocoding
    monkeypatch.setattr(geocoding, "LOOKUPS", ())


@pytest.fixture(autouse=True)
def _clear_email_caches():
    from backend.emails import runner
    runner._details_cache.clear()
    yield
    runner._details_cache.clear()
