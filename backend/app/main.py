"""Football-IQ backend — FastAPI application entrypoint."""

from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

import structlog
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import get_settings
from app.logging import configure_logging
from app.routers import health
from app.routers.auth import router as auth_router
from app.routers.calibrations import router as calibrations_router
from app.routers.clips import router as clips_router
from app.routers.correction_analytics import (
    router as correction_analytics_router,
)
from app.routers.corrections import router as corrections_router
from app.routers.events import router as events_router
from app.routers.jobs import router as jobs_router
from app.routers.labels import router as labels_router
from app.routers.metrics import router as metrics_router
from app.routers.mlops import router as mlops_router
from app.routers.pose import router as pose_router
from app.routers.self_scout import router as self_scout_router
from app.routers.tracklets import router as tracklets_router
from app.routers.videos import router as videos_router

settings = get_settings()
configure_logging(settings.log_level)
log = structlog.get_logger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    log.info("startup", environment=settings.environment)
    yield
    log.info("shutdown")


app = FastAPI(
    title="Football-IQ API",
    description="Backend API for the Toledo Football Computer Vision platform.",
    version="0.1.0",
    lifespan=lifespan,
    # Disable automatic docs in production to reduce attack surface
    docs_url="/docs" if settings.environment != "production" else None,
    redoc_url="/redoc" if settings.environment != "production" else None,
)

# ── CORS ─────────────────────────────────────────────────────────────────────
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── Routers ───────────────────────────────────────────────────────────────────
app.include_router(health.router)
app.include_router(auth_router)
app.include_router(videos_router)
app.include_router(clips_router)
app.include_router(jobs_router)
app.include_router(calibrations_router)
app.include_router(tracklets_router)
app.include_router(corrections_router)
app.include_router(events_router)
app.include_router(labels_router)
app.include_router(metrics_router)
app.include_router(mlops_router)
app.include_router(self_scout_router)
app.include_router(correction_analytics_router)
app.include_router(pose_router)
