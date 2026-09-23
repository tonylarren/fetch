from fastapi import APIRouter

from app.services.jobs import redis_conn

router = APIRouter(tags=["health"])


@router.get("/healthz")
async def healthz():
    return {"status": "ok"}


@router.get("/readyz")
async def readyz():
    checks = {"redis": False, "drive": False}
    try:
        redis_conn.ping()
        checks["redis"] = True
    except Exception:  # noqa: BLE001
        pass
    try:
        from app.services.drive import DriveClient

        DriveClient()
        checks["drive"] = True
    except Exception:  # noqa: BLE001
        pass
    return {"status": "ok" if all(checks.values()) else "degraded", "checks": checks}
