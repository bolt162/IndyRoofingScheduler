import logging
import os
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse

from backend.database import engine, Base, SessionLocal
from backend.routers import jobs, scoring, schedule, settings, weather

logger = logging.getLogger("scheduler")


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup: create tables, seed settings, start weather scheduler."""
    # Import all models so they register with Base before create_all
    from backend.models.job import Job  # noqa
    from backend.models.pm import PM, Crew  # noqa
    from backend.models.note_log import NoteLog  # noqa
    from backend.models.schedule import SchedulePlan  # noqa
    from backend.models.settings import SystemSettings  # noqa

    Base.metadata.create_all(bind=engine)
    _seed_default_settings()

    # Start APScheduler for weather checks + JN sync polling
    scheduler = _start_scheduler()
    yield
    # Shutdown scheduler gracefully
    if scheduler:
        scheduler.shutdown(wait=False)


app = FastAPI(
    title="Indy Roof Scheduling Intelligence System",
    version="1.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(jobs.router, prefix="/api/jobs", tags=["jobs"])
app.include_router(scoring.router, prefix="/api/scoring", tags=["scoring"])
app.include_router(schedule.router, prefix="/api/schedule", tags=["schedule"])
app.include_router(settings.router, prefix="/api/settings", tags=["settings"])
app.include_router(weather.router, prefix="/api/weather", tags=["weather"])


# Serve React frontend static files in production
# In dev, Vite's dev server handles this via proxy
_FRONTEND_DIR = Path(__file__).resolve().parent.parent / "frontend-react" / "dist"
if _FRONTEND_DIR.is_dir():
    # Mount the entire dist directory as static files at root
    # This MUST come after all API routers so /api/* routes take priority
    # StaticFiles with html=True serves index.html for directory requests (SPA fallback)
    app.mount("/", StaticFiles(directory=str(_FRONTEND_DIR), html=True), name="spa")


def _seed_default_settings():
    from backend.models.settings import SystemSettings, DEFAULT_SETTINGS

    db = SessionLocal()
    try:
        for key, info in DEFAULT_SETTINGS.items():
            existing = db.query(SystemSettings).filter(SystemSettings.key == key).first()
            if not existing:
                db.add(SystemSettings(key=key, value=info["value"], description=info["description"]))
        db.commit()
    finally:
        db.close()


def _jn_sync_job():
    """Background JN sync — fetches jobs only, NO AI scanning."""
    db = SessionLocal()
    try:
        from backend.services.jobnimbus import sync_jobs_from_jn
        result = sync_jobs_from_jn(db)
        logger.info(
            f"JN auto-sync: {result['created']} new, {result['updated']} updated, "
            f"{len(result['errors'])} errors"
        )
    except Exception as e:
        logger.error(f"JN auto-sync failed: {e}")
    finally:
        db.close()


def _start_scheduler():
    """Start APScheduler for weather checks (spec §6.2, §6.4) and JN sync polling."""
    try:
        from apscheduler.schedulers.asyncio import AsyncIOScheduler
        from apscheduler.triggers.cron import CronTrigger
        from apscheduler.triggers.interval import IntervalTrigger
        from backend.services.weather_scheduler import (
            morning_weather_check, night_before_check, five_am_spot_check,
        )

        # Read configurable times from DB
        db = SessionLocal()
        try:
            from backend.models.settings import SystemSettings
            morning_s = db.query(SystemSettings).filter(
                SystemSettings.key == "weather_morning_check_time"
            ).first()
            night_s = db.query(SystemSettings).filter(
                SystemSettings.key == "bamwx_check_time"
            ).first()
            sync_s = db.query(SystemSettings).filter(
                SystemSettings.key == "jn_sync_interval_minutes"
            ).first()
            morning_time = morning_s.value if morning_s else "06:00"
            night_time = night_s.value if night_s else "20:00"
            sync_interval = int(sync_s.value) if sync_s and sync_s.value else 30
        finally:
            db.close()

        morning_h, morning_m = morning_time.split(":")
        night_h, night_m = night_time.split(":")

        scheduler = AsyncIOScheduler(timezone="America/Indiana/Indianapolis")

        # --- JN Sync (interval-based) ---
        scheduler.add_job(
            _jn_sync_job,
            IntervalTrigger(minutes=sync_interval),
            id="jn_sync", name="JN Auto-Sync",
            misfire_grace_time=300,  # Run if missed within 5 minutes
        )

        # --- Weather checks (cron-based) ---
        # Morning check (default 6:00 AM)
        scheduler.add_job(
            morning_weather_check, CronTrigger(hour=int(morning_h), minute=int(morning_m)),
            id="morning_weather", name="Morning Weather Check",
            misfire_grace_time=3600,
        )
        # Night-before check (default 8:00 PM — spec §6.4)
        scheduler.add_job(
            night_before_check, CronTrigger(hour=int(night_h), minute=int(night_m)),
            id="night_before_weather", name="Night-Before Weather Check",
            misfire_grace_time=3600,
        )
        # 5am spot check (spec §6.2 line 255)
        scheduler.add_job(
            five_am_spot_check, CronTrigger(hour=5, minute=0),
            id="five_am_weather", name="5am Spot Check",
            misfire_grace_time=3600,
        )

        scheduler.start()
        logger.info(
            f"Scheduler started: JN sync every {sync_interval}min, "
            f"weather morning={morning_time}, night-before={night_time}, 5am spot check"
        )
        return scheduler
    except ImportError:
        logger.warning("APScheduler not installed — automated checks disabled")
        return None
    except Exception as e:
        logger.error(f"Failed to start scheduler: {e}")
        return None


@app.get("/health")
def health():
    return {"status": "ok", "service": "indy-roof-scheduler"}
