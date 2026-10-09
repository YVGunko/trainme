import logging
import os
import secrets

from fastapi import FastAPI, Header, HTTPException, Query

from app.garmin.client import (
    GarminConnectAuthenticationError,
    GarminConnectConnectionError,
    GarminConnectTooManyRequestsError,
    GarminNotConfigured,
    fetch_recent_activities,
)

logger = logging.getLogger(__name__)

app = FastAPI()


@app.get("/health")
def health() -> dict[str, bool]:
    return {"ok": True}


@app.get("/activities")
def activities(
    limit: int = Query(default=5, ge=1, le=10),
    authorization: str | None = Header(default=None),
) -> dict[str, list]:
    _require_service_secret(authorization)
    try:
        items = fetch_recent_activities(limit)
    except GarminNotConfigured:
        raise HTTPException(status_code=503, detail="Garmin credentials are not configured")
    except GarminConnectAuthenticationError:
        logger.warning("Garmin authentication failed")
        raise HTTPException(status_code=401, detail="Garmin authentication failed")
    except GarminConnectTooManyRequestsError:
        raise HTTPException(status_code=429, detail="Garmin rate limit")
    except GarminConnectConnectionError:
        logger.warning("Garmin connection failed")
        raise HTTPException(status_code=502, detail="Garmin connection failed")
    except Exception:
        logger.exception("Activity fetch failed")
        raise HTTPException(status_code=502, detail="Garmin request failed")
    return {"activities": items}


def _require_service_secret(authorization: str | None) -> None:
    expected = os.environ.get("SERVICE_SECRET", "")
    if not expected:
        raise HTTPException(status_code=503, detail="SERVICE_SECRET is not configured")
    provided = ""
    if authorization and authorization.startswith("Bearer "):
        provided = authorization.removeprefix("Bearer ").strip()
    if not provided or not secrets.compare_digest(provided, expected):
        raise HTTPException(status_code=401, detail="Unauthorized")
