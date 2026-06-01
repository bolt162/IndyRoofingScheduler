import logging
import os
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse

from backend.database import engine, Base, SessionLocal
from backend.routers import jobs, scoring, schedule, settings, weather, auth as auth_router
from backend.services.auth import get_approved_user
from fastapi import Depends

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
    # No User model — Clerk owns user identity & approval state

    Base.metadata.create_all(bind=engine)
    _seed_default_settings()
    _cleanup_siding_material()
    _migrate_note_log_columns()
    _migrate_crew_columns()
    _migrate_job_columns()

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

# Auth router is mounted without router-level guard. Its /me endpoint has its
# own get_current_user dependency (no approval check) so pending users can call
# it to discover they're pending.
app.include_router(auth_router.router, prefix="/api/auth", tags=["auth"])

# All other API routers REQUIRE a valid Clerk JWT AND approved=true claim.
# get_approved_user verifies signature + issuer + expiry, then 403s pending users.
_protected = [Depends(get_approved_user)]
app.include_router(jobs.router, prefix="/api/jobs", tags=["jobs"], dependencies=_protected)
app.include_router(scoring.router, prefix="/api/scoring", tags=["scoring"], dependencies=_protected)
app.include_router(schedule.router, prefix="/api/schedule", tags=["schedule"], dependencies=_protected)
app.include_router(settings.router, prefix="/api/settings", tags=["settings"], dependencies=_protected)
app.include_router(weather.router, prefix="/api/weather", tags=["weather"], dependencies=_protected)


# Health check — must be defined before any catch-all
@app.get("/api/health")
def health():
    return {"status": "ok", "service": "indy-roof-scheduler"}


# Serve React frontend static files in production
# In dev, Vite's dev server handles this via proxy
_FRONTEND_DIR = Path(__file__).resolve().parent.parent / "frontend-react" / "dist"
if _FRONTEND_DIR.is_dir():
    from starlette.responses import HTMLResponse

    # Serve /assets/* directly (JS, CSS, fonts, images)
    _ASSETS_DIR = _FRONTEND_DIR / "assets"
    if _ASSETS_DIR.is_dir():
        app.mount("/assets", StaticFiles(directory=str(_ASSETS_DIR)), name="assets")

    # Read index.html once at startup
    _INDEX_HTML = (_FRONTEND_DIR / "index.html").read_text()

    # Serve static files (favicon, icons, etc.) and SPA fallback
    @app.middleware("http")
    async def spa_middleware(request: Request, call_next):
        # Let /api/* routes pass through to FastAPI routers
        if request.url.path.startswith("/api"):
            return await call_next(request)

        # Try to serve exact static file from dist/
        file_path = _FRONTEND_DIR / request.url.path.lstrip("/")
        if file_path.is_file() and ".." not in request.url.path:
            return FileResponse(str(file_path))

        # SPA fallback: serve index.html for all other routes
        return HTMLResponse(_INDEX_HTML)


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


def _cleanup_siding_material():
    """One-time cleanup: clear material_type='siding' on existing jobs.
    Siding is a TRADE, not a material — it should be in primary_trade only.
    Safe to run on every startup (no-op if no siding material rows exist)."""
    from backend.models.job import Job
    from sqlalchemy import update
    db = SessionLocal()
    try:
        result = db.execute(
            update(Job).where(Job.material_type == "siding").values(material_type="")
        )
        if result.rowcount > 0:
            logger.info(f"Cleanup: cleared material_type='siding' on {result.rowcount} jobs (siding moved to primary_trade)")
        db.commit()
    except Exception as e:
        logger.warning(f"Siding cleanup failed: {e}")
    finally:
        db.close()


def _migrate_job_columns():
    """Add last_ai_analyzed_at column to jobs table if missing.
    Safe to run on every startup."""
    from sqlalchemy import inspect, text
    db = SessionLocal()
    try:
        insp = inspect(engine)
        if "jobs" not in insp.get_table_names():
            return
        existing = {col["name"] for col in insp.get_columns("jobs")}
        if "last_ai_analyzed_at" not in existing:
            try:
                db.execute(text("ALTER TABLE jobs ADD COLUMN last_ai_analyzed_at TIMESTAMP"))
                db.commit()
                logger.info("Migration: ALTER TABLE jobs ADD COLUMN last_ai_analyzed_at TIMESTAMP")
            except Exception as e:
                logger.warning(f"Migration skip (last_ai_analyzed_at): {e}")
                db.rollback()
    except Exception as e:
        logger.warning(f"Job column migration failed: {e}")
    finally:
        db.close()


def _migrate_crew_columns():
    """Add rank, notes, and trades columns to crews table if missing.
    Also backfills 'trades' for legacy crews where specialties contains trade names.
    Safe to run on every startup."""
    from sqlalchemy import inspect, text
    from backend.models.pm import Crew

    db = SessionLocal()
    try:
        insp = inspect(engine)
        if "crews" not in insp.get_table_names():
            return
        existing_cols = insp.get_columns("crews")
        existing = {col["name"] for col in existing_cols}
        is_postgres = "postgres" in str(engine.url).lower()

        additions = []
        if "rank" not in existing:
            additions.append("ADD COLUMN rank INTEGER DEFAULT 999")
        if "notes" not in existing:
            additions.append("ADD COLUMN notes TEXT")
        # CRITICAL: trades must be JSON type on Postgres so SQLAlchemy round-trips
        # the list correctly. TEXT works on SQLite (its JSON is stored as TEXT).
        if "trades" not in existing:
            col_type = "JSON" if is_postgres else "TEXT"
            additions.append(f"ADD COLUMN trades {col_type}")
        for stmt in additions:
            try:
                db.execute(text(f"ALTER TABLE crews {stmt}"))
                db.commit()
                logger.info(f"Migration: ALTER TABLE crews {stmt}")
            except Exception as e:
                logger.warning(f"Migration skip ({stmt}): {e}")
                db.rollback()

        # --- Repair: if 'trades' exists but is TEXT (from earlier bad migration on Postgres),
        # convert it to JSON so SQLAlchemy can deserialize it correctly ---
        if is_postgres and "trades" in existing:
            trades_col = next((c for c in existing_cols if c["name"] == "trades"), None)
            # SQLAlchemy reports the column's actual type. We check if it's text.
            col_type_str = str(trades_col["type"]).upper() if trades_col else ""
            if "TEXT" in col_type_str or "VARCHAR" in col_type_str:
                try:
                    # Cast existing TEXT values to JSON. Values like '["roofing"]' become arrays.
                    db.execute(text(
                        "ALTER TABLE crews ALTER COLUMN trades TYPE JSON USING "
                        "CASE WHEN trades IS NULL OR trades = '' THEN NULL "
                        "ELSE trades::json END"
                    ))
                    db.commit()
                    logger.info("Migration: converted crews.trades from TEXT to JSON")
                except Exception as e:
                    logger.warning(f"Migration repair (trades TEXT→JSON) skipped: {e}")
                    db.rollback()

        # --- Backfill: split trade names out of legacy `specialties` into `trades` ---
        TRADE_NAMES = {"roofing", "roofing_repair", "siding", "siding_repair", "gutters", "windows", "paint", "interior", "other"}
        crews = db.query(Crew).all()
        backfilled = 0
        for crew in crews:
            # Only backfill if trades is empty/None — don't overwrite manual edits
            if crew.trades:
                continue
            existing_specialties = list(crew.specialties or [])
            extracted_trades = [s for s in existing_specialties if s and s.lower() in TRADE_NAMES]
            remaining_specialties = [s for s in existing_specialties if s and s.lower() not in TRADE_NAMES]
            if extracted_trades or not crew.trades:
                # Default to roofing if nothing identifiable in specialties — preserves backward compatibility
                crew.trades = extracted_trades if extracted_trades else ["roofing"]
                crew.specialties = remaining_specialties
                backfilled += 1
        if backfilled > 0:
            db.commit()
            logger.info(f"Migration: backfilled trades on {backfilled} crew(s)")
    except Exception as e:
        logger.warning(f"Crew column migration failed: {e}")
    finally:
        db.close()


def _migrate_note_log_columns():
    """Add new columns to note_logs table if they don't exist.
    This is a lightweight migration for production DBs that don't use Alembic.
    Safe to run on every startup."""
    from sqlalchemy import inspect, text
    db = SessionLocal()
    try:
        insp = inspect(engine)
        if "note_logs" not in insp.get_table_names():
            return  # Table not yet created; create_all will handle it
        existing = {col["name"] for col in insp.get_columns("note_logs")}

        is_sqlite = "sqlite" in str(engine.url)
        additions = []
        if "pushed_at" not in existing:
            additions.append("ADD COLUMN pushed_at TIMESTAMP")
        if "jn_note_id" not in existing:
            additions.append("ADD COLUMN jn_note_id VARCHAR(255)")
        if "push_error" not in existing:
            additions.append("ADD COLUMN push_error TEXT")

        for stmt in additions:
            try:
                db.execute(text(f"ALTER TABLE note_logs {stmt}"))
                db.commit()
                logger.info(f"Migration: ALTER TABLE note_logs {stmt}")
            except Exception as e:
                logger.warning(f"Migration skip ({stmt}): {e}")
                db.rollback()
    except Exception as e:
        logger.warning(f"NoteLog column migration failed: {e}")
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

        # --- Secondary trade aging check (8am daily) ---
        # Client requirement: secondary trades due within 7 days of primary complete,
        # escalate higher at 10 days. Generates warning/escalation notes once per job per level.
        from backend.services.secondary_trade_escalation import run_daily_escalation_check
        scheduler.add_job(
            run_daily_escalation_check, CronTrigger(hour=8, minute=0),
            id="secondary_trade_escalation", name="Secondary Trade Escalation",
            misfire_grace_time=3600,
        )

        scheduler.start()
        logger.info(
            f"Scheduler started: JN sync every {sync_interval}min, "
            f"weather morning={morning_time}, night-before={night_time}, 5am spot check, "
            f"secondary trade escalation 8am daily"
        )
        return scheduler
    except ImportError:
        logger.warning("APScheduler not installed — automated checks disabled")
        return None
    except Exception as e:
        logger.error(f"Failed to start scheduler: {e}")
        return None
