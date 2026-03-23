from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, DeclarativeBase

from backend.config import settings

engine = create_engine(settings.DATABASE_URL, connect_args={"check_same_thread": False} if "sqlite" in settings.DATABASE_URL else {})
SessionLocal = sessionmaker(bind=engine, autocommit=False, autoflush=False)


class Base(DeclarativeBase):
    pass


def init_db():
    """Create all tables if they don't exist."""
    # Import all models so they register with Base
    from backend.models.job import Job  # noqa
    from backend.models.pm import PM, Crew  # noqa
    from backend.models.note_log import NoteLog  # noqa
    from backend.models.schedule import SchedulePlan  # noqa
    from backend.models.settings import SystemSettings  # noqa

    Base.metadata.create_all(bind=engine)

    # Seed default settings if empty
    db = SessionLocal()
    try:
        count = db.query(SystemSettings).count()
        if count == 0:
            from backend.models.settings import seed_defaults
            seed_defaults(db)
    except Exception:
        pass
    finally:
        db.close()


# Auto-create tables on import
init_db()


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
