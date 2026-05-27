"""Health-check router — /health, /ready, and /live."""

import os
import time

import structlog
from fastapi import APIRouter, Depends
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db

router = APIRouter(tags=["health"])
log = structlog.get_logger(__name__)

_BOOT_TIME = time.time()


@router.get("/health")
async def health() -> dict[str, object]:
    """Liveness probe — returns 200 if the process is running."""
    return {
        "status": "ok",
        "service": "football-iq-backend",
        "environment": os.environ.get("ENVIRONMENT", "development"),
        "uptime_seconds": round(time.time() - _BOOT_TIME, 1),
    }


@router.get("/live")
async def live() -> dict[str, str]:
    """Lightweight liveness probe (alias for container orchestrators)."""
    return {"status": "ok"}


@router.get("/ready")
async def ready(db: AsyncSession = Depends(get_db)) -> dict[str, object]:
    """Readiness probe — returns 200 only when critical dependencies are reachable."""
    checks: dict[str, str] = {}
    all_ok = True

    # Database check
    try:
        await db.execute(text("SELECT 1"))
        checks["database"] = "ok"
    except Exception as exc:
        log.error("readiness_check_failed", component="database", error=str(exc))
        checks["database"] = "unavailable"
        all_ok = False

    if not all_ok:
        from fastapi import HTTPException

        raise HTTPException(status_code=503, detail={"status": "not_ready", "checks": checks})

    return {"status": "ready", "checks": checks}
