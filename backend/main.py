import asyncio
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from backend.database import engine, Base, SessionLocal
from backend.routers import jobs, scoring, schedule, settings, weather

logger = logging.getLogger("scheduler")

# Global sync status — tracks whether a background sync is in progress
_sync_status = {"running": False, "last_result": None, "error": None}


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup: seed settings, start background polling. Initial sync runs in background."""
    Base.metadata.create_all(bind=engine)
    _seed_default_settings()
    # Run initial sync in background thread so it doesn't block server startup
    # (sync now includes AI note scanning which can take minutes)
    sync_task = asyncio.create_task(asyncio.to_thread(_run_initial_sync))
    poll_task = asyncio.create_task(_poll_jn_sync())
    yield
    sync_task.cancel()
    poll_task.cancel()
    try:
        await poll_task
    except asyncio.CancelledError:
        pass


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


def _run_initial_sync():
    """Run a JN sync on startup so the DB is populated when the app loads."""
    from backend.services.jobnimbus import sync_jobs_from_jn

    _sync_status["running"] = True
    _sync_status["error"] = None
    db = SessionLocal()
    try:
        result = sync_jobs_from_jn(db)
        _sync_status["last_result"] = result
        logger.info(f"[JN Initial Sync] {result}")
    except Exception as e:
        _sync_status["error"] = str(e)
        logger.warning(f"[JN Initial Sync] Failed: {e}")
    finally:
        _sync_status["running"] = False
        db.close()


async def _poll_jn_sync():
    """Background task: sync JN on configurable interval from settings."""
    from backend.models.settings import SystemSettings
    from backend.services.jobnimbus import sync_jobs_from_jn

    while True:
        # Read interval from DB each cycle so settings changes take effect without restart
        db = SessionLocal()
        try:
            setting = db.query(SystemSettings).filter(
                SystemSettings.key == "jn_sync_interval_minutes"
            ).first()
            interval = int(setting.value) if setting else 15
        except Exception:
            interval = 15
        finally:
            db.close()

        await asyncio.sleep(interval * 60)

        # Run sync
        db = SessionLocal()
        try:
            result = sync_jobs_from_jn(db)
            logger.info(f"[JN Auto-Sync] {result}")
        except Exception as e:
            logger.warning(f"[JN Auto-Sync] Error: {e}")
        finally:
            db.close()


@app.get("/health")
def health():
    return {"status": "ok", "service": "indy-roof-scheduler"}


@app.get("/api/sync-status")
def sync_status():
    """Returns whether a background JN sync (with AI scanning) is currently running."""
    return _sync_status
