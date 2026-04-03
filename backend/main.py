import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from backend.database import engine, Base, SessionLocal
from backend.routers import jobs, scoring, schedule, settings, weather

logger = logging.getLogger("scheduler")


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup: create tables and seed default settings.
    JN sync is manual only (user clicks 'Sync JN') to avoid
    burning Claude API tokens on every server restart during development."""
    Base.metadata.create_all(bind=engine)
    _seed_default_settings()
    yield


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


@app.get("/health")
def health():
    return {"status": "ok", "service": "indy-roof-scheduler"}
