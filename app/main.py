import json
import logging
import os
import secrets
from datetime import date

from fastapi import Body, FastAPI, Header, HTTPException, Query
from fastapi.responses import Response

from app.garmin.archive import (
    ArchiveError,
    DatabaseNotConfigured,
    EncryptionKeyMissing,
    PeriodError,
    archive_latest,
    archive_period,
)
from app.garmin.client import (
    GarminConnectAuthenticationError,
    GarminConnectConnectionError,
    GarminConnectTooManyRequestsError,
    GarminNotConfigured,
    fetch_recent_activities,
)
from app.garmin.device import WorkoutDeviceError, WorkoutRateLimited
from app.garmin.probe import probe_unused
from app.garmin.history import HistoryPeriodError, import_history
from app.profile import ProfileError
from app.athlete import read_profile, write_profile
from app.garmin.workout import (
    WorkoutDateError,
    WorkoutFitFileError,
    WorkoutNotPushed,
    WorkoutNotScheduled,
    WorkoutSpecError,
    import_workout_fit,
    list_workout_devices,
    schedule_test_strength_workout,
    upload_workout,
)
from app.garmin.workout_probe import probe_workout_device
from app.normalize.fit import NormalizeError
from app.normalize.load import normalize_activity, normalize_latest
from app.storage.blob import BlobNotConfigured, BlobReadError, BlobUploadError

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


@app.post("/archive")
def archive(authorization: str | None = Header(default=None)) -> dict:
    _require_service_secret(authorization)
    try:
        return archive_latest()
    except (GarminNotConfigured, DatabaseNotConfigured, EncryptionKeyMissing, BlobNotConfigured):
        raise HTTPException(status_code=503, detail="Archive storage is not configured")
    except GarminConnectAuthenticationError:
        logger.warning("Garmin authentication failed")
        raise HTTPException(status_code=401, detail="Garmin authentication failed")
    except GarminConnectTooManyRequestsError:
        raise HTTPException(status_code=429, detail="Garmin rate limit")
    except (GarminConnectConnectionError, ArchiveError, BlobUploadError):
        logger.warning("Archive failed")
        raise HTTPException(status_code=502, detail="Archive failed")
    except Exception as error:
        logger.warning("Archive failed: %s", type(error).__name__)
        raise HTTPException(status_code=502, detail="Archive failed")


@app.post("/archive/period")
def archive_for_period(
    body: dict | None = Body(default=None),
    authorization: str | None = Header(default=None),
) -> dict:
    _require_service_secret(authorization)
    payload = body if isinstance(body, dict) else {}
    start = payload.get("start")
    end = payload.get("end")
    if not isinstance(start, str) or not isinstance(end, str):
        raise HTTPException(status_code=400, detail="Period dates must be YYYY-MM-DD")
    try:
        return archive_period(start, end)
    except PeriodError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error
    except (GarminNotConfigured, DatabaseNotConfigured, EncryptionKeyMissing, BlobNotConfigured):
        raise HTTPException(status_code=503, detail="Archive storage is not configured")
    except GarminConnectAuthenticationError:
        logger.warning("Garmin authentication failed")
        raise HTTPException(status_code=401, detail="Garmin authentication failed")
    except GarminConnectTooManyRequestsError:
        raise HTTPException(status_code=429, detail="Garmin rate limit")
    except (GarminConnectConnectionError, ArchiveError, BlobUploadError):
        logger.warning("Archive failed")
        raise HTTPException(status_code=502, detail="Archive failed")
    except Exception as error:
        logger.warning("Archive failed: %s", type(error).__name__)
        raise HTTPException(status_code=502, detail="Archive failed")


@app.post("/workouts/strength-test")
def strength_test_workout(
    body: dict | None = Body(default=None),
    authorization: str | None = Header(default=None),
) -> dict:
    _require_service_secret(authorization)
    payload = body if isinstance(body, dict) else {}
    day = payload.get("date")
    if not isinstance(day, str):
        raise HTTPException(status_code=400, detail="Date must be YYYY-MM-DD")
    try:
        return schedule_test_strength_workout(day)
    except WorkoutDateError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error
    except WorkoutNotScheduled as error:
        logger.warning(
            "Workout %s uploaded but not scheduled: %s",
            error.workout_id,
            type(error.__cause__).__name__,
        )
        status = 429 if isinstance(error.__cause__, GarminConnectTooManyRequestsError) else 502
        raise HTTPException(
            status_code=status,
            detail=f"Workout {error.workout_id} was uploaded but not scheduled",
        ) from error
    except (GarminNotConfigured, DatabaseNotConfigured, EncryptionKeyMissing):
        raise HTTPException(status_code=503, detail="Garmin upload is not configured")
    except GarminConnectAuthenticationError:
        logger.warning("Garmin authentication failed")
        raise HTTPException(status_code=401, detail="Garmin authentication failed")
    except GarminConnectTooManyRequestsError:
        raise HTTPException(status_code=429, detail="Garmin rate limit")
    except GarminConnectConnectionError:
        logger.warning("Workout upload failed")
        raise HTTPException(status_code=502, detail="Workout upload failed")
    except Exception as error:
        logger.warning("Workout upload failed: %s", type(error).__name__)
        raise HTTPException(status_code=502, detail="Workout upload failed")


@app.post("/workouts/devices")
def workout_devices(authorization: str | None = Header(default=None)) -> dict:
    _require_service_secret(authorization)
    try:
        return list_workout_devices()
    except WorkoutDeviceError as error:
        logger.warning("Garmin device list failed: %s", type(error).__name__)
        raise HTTPException(status_code=502, detail=str(error)) from error
    except (GarminNotConfigured, DatabaseNotConfigured, EncryptionKeyMissing):
        raise HTTPException(status_code=503, detail="Garmin upload is not configured")
    except GarminConnectAuthenticationError:
        logger.warning("Garmin authentication failed")
        raise HTTPException(status_code=401, detail="Garmin authentication failed")
    except GarminConnectTooManyRequestsError:
        raise HTTPException(status_code=429, detail="Garmin rate limit")
    except GarminConnectConnectionError:
        logger.warning("Garmin device list failed")
        raise HTTPException(status_code=502, detail="Garmin device list failed")
    except Exception as error:
        logger.warning("Garmin device list failed: %s", type(error).__name__)
        raise HTTPException(status_code=502, detail="Garmin device list failed")


@app.post("/workouts")
def send_workout(
    body: dict | None = Body(default=None),
    authorization: str | None = Header(default=None),
) -> dict:
    _require_service_secret(authorization)
    payload = body if isinstance(body, dict) else {}
    workout = payload.get("workout")
    if not isinstance(workout, dict):
        raise HTTPException(status_code=400, detail="workout must be an object")
    spec = dict(workout)
    for key in ("date", "device_id", "push"):
        if payload.get(key) is not None:
            spec[key] = payload[key]
    try:
        return upload_workout(spec)
    except (WorkoutSpecError, WorkoutDeviceError, WorkoutDateError) as error:
        raise HTTPException(status_code=400, detail=str(error)) from error
    except WorkoutNotPushed as error:
        logger.warning(
            "Workout %s uploaded but not pushed to device %s: %s",
            error.workout_id,
            error.device_id,
            type(error.__cause__).__name__,
        )
        status = 429 if isinstance(error.__cause__, WorkoutRateLimited) else 502
        raise HTTPException(
            status_code=status,
            detail=f"Workout {error.workout_id} was uploaded but not sent to a device",
        ) from error
    except WorkoutNotScheduled as error:
        logger.warning(
            "Workout %s uploaded but not scheduled: %s",
            error.workout_id,
            type(error.__cause__).__name__,
        )
        status = 429 if isinstance(error.__cause__, GarminConnectTooManyRequestsError) else 502
        raise HTTPException(
            status_code=status,
            detail=f"Workout {error.workout_id} was uploaded but not scheduled",
        ) from error
    except (GarminNotConfigured, DatabaseNotConfigured, EncryptionKeyMissing):
        raise HTTPException(status_code=503, detail="Garmin upload is not configured")
    except GarminConnectAuthenticationError:
        logger.warning("Garmin authentication failed")
        raise HTTPException(status_code=401, detail="Garmin authentication failed")
    except GarminConnectTooManyRequestsError:
        raise HTTPException(status_code=429, detail="Garmin rate limit")
    except GarminConnectConnectionError:
        logger.warning("Workout upload failed")
        raise HTTPException(status_code=502, detail="Workout upload failed")
    except Exception as error:
        logger.warning("Workout upload failed: %s", type(error).__name__)
        raise HTTPException(status_code=502, detail="Workout upload failed")


@app.post("/workouts/fit")
def send_workout_fit(
    body: dict | None = Body(default=None),
    authorization: str | None = Header(default=None),
) -> dict:
    _require_service_secret(authorization)
    payload = body if isinstance(body, dict) else {}
    try:
        return import_workout_fit(payload)
    except WorkoutFitFileError as error:
        # The reason travels as its own field so the browser can say what is
        # wrong with the file instead of a single generic sentence.
        raise HTTPException(
            status_code=400,
            detail={"reason": error.reason, "message": str(error)},
        ) from error
    except (WorkoutSpecError, WorkoutDeviceError, WorkoutDateError) as error:
        raise HTTPException(status_code=400, detail=str(error)) from error
    except WorkoutNotPushed as error:
        logger.warning(
            "Fit workout %s uploaded but not pushed to device %s: %s",
            error.workout_id,
            error.device_id,
            type(error.__cause__).__name__,
        )
        status = 429 if isinstance(error.__cause__, WorkoutRateLimited) else 502
        raise HTTPException(
            status_code=status,
            detail=f"Workout {error.workout_id} was uploaded but not sent to a device",
        ) from error
    except WorkoutNotScheduled as error:
        logger.warning(
            "Fit workout %s uploaded but not scheduled: %s",
            error.workout_id,
            type(error.__cause__).__name__,
        )
        status = 429 if isinstance(error.__cause__, GarminConnectTooManyRequestsError) else 502
        raise HTTPException(
            status_code=status,
            detail=f"Workout {error.workout_id} was uploaded but not scheduled",
        ) from error
    except (GarminNotConfigured, DatabaseNotConfigured, EncryptionKeyMissing):
        raise HTTPException(status_code=503, detail="Garmin upload is not configured")
    except GarminConnectAuthenticationError:
        logger.warning("Garmin authentication failed")
        raise HTTPException(status_code=401, detail="Garmin authentication failed")
    except GarminConnectTooManyRequestsError:
        raise HTTPException(status_code=429, detail="Garmin rate limit")
    except GarminConnectConnectionError:
        logger.warning("Fit workout upload failed")
        raise HTTPException(status_code=502, detail="Fit workout upload failed")
    except Exception as error:
        logger.warning("Fit workout upload failed: %s", type(error).__name__)
        raise HTTPException(status_code=502, detail="Fit workout upload failed")


@app.get("/profile")
def get_profile(authorization: str | None = Header(default=None)) -> dict:
    _require_service_secret(authorization)
    try:
        return read_profile()
    except DatabaseNotConfigured:
        raise HTTPException(status_code=503, detail="Profile storage is not configured")
    except Exception as error:
        logger.warning("Profile read failed: %s", type(error).__name__)
        raise HTTPException(status_code=502, detail="Profile read failed")


@app.post("/profile")
def put_profile(
    body: dict | None = Body(default=None),
    authorization: str | None = Header(default=None),
) -> dict:
    _require_service_secret(authorization)
    try:
        return write_profile(body if isinstance(body, dict) else None)
    except ProfileError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error
    except DatabaseNotConfigured:
        raise HTTPException(status_code=503, detail="Profile storage is not configured")
    except Exception as error:
        logger.warning("Profile write failed: %s", type(error).__name__)
        raise HTTPException(status_code=502, detail="Profile write failed")


@app.post("/history")
def import_activity_history(
    body: dict | None = Body(default=None),
    authorization: str | None = Header(default=None),
) -> dict:
    _require_service_secret(authorization)
    payload = body if isinstance(body, dict) else {}
    start = payload.get("start")
    end = payload.get("end")
    if not isinstance(start, str) or not isinstance(end, str):
        raise HTTPException(status_code=400, detail="Period dates must be YYYY-MM-DD")
    try:
        return import_history(start, end)
    except HistoryPeriodError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error
    except (GarminNotConfigured, DatabaseNotConfigured, EncryptionKeyMissing):
        raise HTTPException(status_code=503, detail="History import is not configured")
    except GarminConnectAuthenticationError:
        logger.warning("Garmin authentication failed")
        raise HTTPException(status_code=401, detail="Garmin authentication failed")
    except GarminConnectTooManyRequestsError:
        raise HTTPException(status_code=429, detail="Garmin rate limit")
    except (GarminConnectConnectionError, ArchiveError):
        logger.warning("History import failed")
        raise HTTPException(status_code=502, detail="History import failed")
    except Exception as error:
        logger.warning("History import failed: %s", type(error).__name__)
        raise HTTPException(status_code=502, detail="History import failed")


@app.post("/probe/unused-garmin")
def probe_unused_garmin(
    body: dict | None = Body(default=None),
    authorization: str | None = Header(default=None),
) -> Response:
    _require_service_secret(authorization)
    payload = body if isinstance(body, dict) else {}
    raw = payload.get("date")
    if not isinstance(raw, str) or len(raw) != 10 or raw[4] != "-" or raw[7] != "-":
        raise HTTPException(status_code=400, detail="Date must be YYYY-MM-DD")
    try:
        day = date.fromisoformat(raw)
    except ValueError as error:
        raise HTTPException(status_code=400, detail="Date must be YYYY-MM-DD") from error
    try:
        report = probe_unused(day)
    except (GarminNotConfigured, DatabaseNotConfigured, EncryptionKeyMissing):
        raise HTTPException(status_code=503, detail="Garmin probe is not configured")
    except GarminConnectAuthenticationError:
        logger.warning("Garmin authentication failed")
        raise HTTPException(status_code=401, detail="Garmin authentication failed")
    except GarminConnectTooManyRequestsError:
        raise HTTPException(status_code=429, detail="Garmin rate limit")
    except GarminConnectConnectionError:
        logger.warning("Garmin probe failed")
        raise HTTPException(status_code=502, detail="Garmin probe failed")
    except Exception as error:
        logger.warning("Garmin probe failed: %s", type(error).__name__)
        raise HTTPException(status_code=502, detail="Garmin probe failed")
    return Response(
        content=json.dumps(report, ensure_ascii=False, default=str),
        media_type="application/json",
    )


@app.post("/probe/workout-device")
def probe_workout_device_route(
    body: dict | None = Body(default=None),
    authorization: str | None = Header(default=None),
) -> Response:
    _require_service_secret(authorization)
    payload = body if isinstance(body, dict) else {}
    try:
        report = probe_workout_device(
            _probe_workout_id(payload, "push_workout_id"),
            _probe_workout_id(payload, "download_workout_id"),
        )
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error
    except (GarminNotConfigured, DatabaseNotConfigured, EncryptionKeyMissing):
        raise HTTPException(status_code=503, detail="Garmin probe is not configured")
    except GarminConnectAuthenticationError:
        logger.warning("Garmin authentication failed")
        raise HTTPException(status_code=401, detail="Garmin authentication failed")
    except GarminConnectTooManyRequestsError:
        raise HTTPException(status_code=429, detail="Garmin rate limit")
    except GarminConnectConnectionError:
        logger.warning("Garmin workout probe failed")
        raise HTTPException(status_code=502, detail="Garmin workout probe failed")
    except Exception as error:
        logger.warning("Garmin workout probe failed: %s", type(error).__name__)
        raise HTTPException(status_code=502, detail="Garmin workout probe failed")
    return Response(
        content=json.dumps(report, ensure_ascii=False, default=str),
        media_type="application/json",
    )


def _probe_workout_id(payload: dict, name: str) -> int | None:
    value = payload.get(name)
    if value is None:
        return None
    if isinstance(value, str) and value.isdigit():
        value = int(value)
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise ValueError(f"{name} must be a positive integer")
    return value


@app.post("/normalize")
def normalize(
    body: dict | None = Body(default=None),
    authorization: str | None = Header(default=None),
) -> dict:
    _require_service_secret(authorization)
    try:
        payload = body if isinstance(body, dict) else {}
        activity_id = payload.get("garmin_activity_id")
        if activity_id is None:
            return normalize_latest()
        if isinstance(activity_id, str) and activity_id.isdigit():
            activity_id = int(activity_id)
        if isinstance(activity_id, bool) or not isinstance(activity_id, int):
            raise HTTPException(status_code=400, detail="garmin_activity_id is required")
        return normalize_activity(activity_id)
    except (DatabaseNotConfigured, BlobNotConfigured):
        raise HTTPException(status_code=503, detail="Archive storage is not configured")
    except NormalizeError as error:
        detail = "No archived file" if error.status_code == 404 else "Normalize failed"
        raise HTTPException(status_code=error.status_code, detail=detail)
    except BlobReadError:
        logger.warning("Normalize failed: BlobReadError")
        raise HTTPException(status_code=502, detail="Normalize failed: BlobReadError")
    except Exception as error:
        name = type(error).__name__
        logger.warning("Normalize failed: %s", name)
        raise HTTPException(status_code=502, detail=f"Normalize failed: {name}")


def _require_service_secret(authorization: str | None) -> None:
    expected = os.environ.get("SERVICE_SECRET", "")
    if not expected:
        raise HTTPException(status_code=503, detail="SERVICE_SECRET is not configured")
    provided = ""
    if authorization and authorization.startswith("Bearer "):
        provided = authorization.removeprefix("Bearer ").strip()
    if not provided or not secrets.compare_digest(provided, expected):
        raise HTTPException(status_code=401, detail="Unauthorized")
