"""Read the Garmin device calls a workout upload depends on.

Nothing is uploaded or pushed unless the caller names a workout id, so a plain
run only reads. Token JSON is never returned.

The point of this report is to record the shape Garmin actually answers with,
because the pinned library documents neither the device list nor the device
message response.
"""

from __future__ import annotations

import json
import logging
from typing import Any

from garminconnect import GarminConnectAuthenticationError

from app.garmin.device import WorkoutDeviceError, list_devices, resolve_device
from app.garmin.fit_workout import WorkoutFitError, parse_workout_fit
from app.garmin.probe import _call, _open_client, _redact, _safe_text

_SPORTS = ("cycling", "running", "strength_training", "yoga", "mobility")


def probe_workout_device(
    push_workout_id: int | None = None,
    download_workout_id: int | None = None,
) -> dict[str, Any]:
    """Report the device calls and, when asked, one push of an existing workout."""
    logging.getLogger("garminconnect").setLevel(logging.ERROR)
    client = _open_client()
    report: dict[str, Any] = {
        "devices": _report_device_list(client),
        "primary": _call("primary_training_device", client.get_primary_training_device),
        "last_used": _call("device_last_used", client.get_device_last_used),
        "sport_device": _report_sport_devices(client),
    }
    if download_workout_id is not None:
        report["download"] = _report_download(client, download_workout_id)
    if push_workout_id is not None:
        report["push"] = _report_push(client, push_workout_id)
    return _redact(report)


def probe_complete(report: dict[str, Any]) -> bool:
    if not report.get("devices", {}).get("ok"):
        return False
    if not report.get("primary", {}).get("ok"):
        return False
    if not report.get("last_used", {}).get("ok"):
        return False
    for entry in report.get("sport_device", {}).values():
        if not entry.get("ok"):
            return False
    push = report.get("push")
    if push is not None and not push.get("sent", {}).get("ok"):
        return False
    download = report.get("download")
    return True if download is None else bool(download.get("parsed"))


def _report_device_list(client: Any) -> dict[str, Any]:
    read = _call("get_devices", client.get_devices)
    if not read["ok"]:
        return read
    try:
        return {"ok": True, "payload": list_devices(client)}
    except WorkoutDeviceError as error:
        return {"ok": False, "error": type(error).__name__, "message": str(error)[:200]}
    except Exception as error:
        return {"ok": False, "error": type(error).__name__, "message": _safe_text(error)}


def _report_sport_devices(client: Any) -> dict[str, Any]:
    report: dict[str, Any] = {}
    for sport in _SPORTS:
        try:
            report[sport] = {"ok": True, "payload": resolve_device(client, sport)}
        except WorkoutDeviceError as error:
            report[sport] = {"ok": False, "error": type(error).__name__, "message": str(error)[:200]}
        except GarminConnectAuthenticationError:
            raise
        except Exception as error:
            report[sport] = {
                "ok": False,
                "error": type(error).__name__,
                "message": _safe_text(error),
            }
    return report


def _report_download(client: Any, workout_id: int) -> dict[str, Any]:
    """Download the FIT Garmin builds for a workout and run it through the importer.

    This is the ground truth for the parser: the file comes from Garmin itself,
    so a step, target, or exercise the parser cannot read shows up here.
    """
    fetched = _call("download_workout", lambda: client.download_workout(workout_id))
    if not fetched["ok"]:
        return fetched
    payload = fetched["payload"]
    if not isinstance(payload, (bytes, bytearray)):
        return {"ok": False, "error": "NotBytes", "message": "download_workout did not return bytes"}
    report: dict[str, Any] = {"ok": True, "byte_size": len(payload)}
    try:
        spec, warnings = parse_workout_fit(bytes(payload))
    except WorkoutFitError as error:
        report.update({"parsed": False, "error": "WorkoutFitError", "message": str(error)[:300]})
        return report
    report["parsed"] = True
    report["spec"] = spec
    report["warnings"] = warnings
    return report


def _report_push(client: Any, workout_id: int) -> dict[str, Any]:
    sport = _call("get_workout_by_id", lambda: client.get_workout_by_id(workout_id))
    report: dict[str, Any] = {"workout_id": workout_id, "workout": sport}
    if not sport["ok"]:
        return report
    workout = sport["payload"] if isinstance(sport["payload"], dict) else {}
    sport_type = workout.get("sportType")
    key = sport_type.get("sportTypeKey") if isinstance(sport_type, dict) else None
    try:
        chosen = resolve_device(client, key if isinstance(key, str) else "", None)
    except WorkoutDeviceError as error:
        report["device"] = {"ok": False, "error": type(error).__name__, "message": str(error)[:200]}
        return report
    report["device"] = {"ok": True, "payload": chosen}
    device_id = chosen["device_id"]
    report["sent"] = _call(
        "push_workout_to_device",
        lambda: _describe_push(client, workout_id, device_id),
    )
    return report


def _describe_push(client: Any, workout_id: int, device_id: int) -> dict[str, Any]:
    answer = client.push_workout_to_device(workout_id, device_id)
    return {"device_id": device_id, "response": answer}


def dump_report(report: dict[str, Any]) -> str:
    return json.dumps(report, ensure_ascii=False, indent=2, default=str)


__all__ = [
    "dump_report",
    "probe_complete",
    "probe_workout_device",
]
