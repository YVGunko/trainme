"""Print a Garmin device report for workout delivery.

The web button uses app.garmin.workout_probe. This command writes the same JSON
under .garmin/ for a local run. Token JSON is never printed.

Without --push-workout-id the run only reads. With it, one existing workout is
pushed to the resolved device, so use an id from the Garmin workout library.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.garmin.probe import (  # noqa: E402
    DatabaseNotConfigured,
    EncryptionKeyMissing,
    GarminConnectAuthenticationError,
    GarminNotConfigured,
)
from app.garmin.workout_probe import (  # noqa: E402
    dump_report,
    probe_complete,
    probe_workout_device,
)


def main() -> int:
    args = _parse_args()
    try:
        report = probe_workout_device(args.push_workout_id, args.download_workout_id)
    except (DatabaseNotConfigured, EncryptionKeyMissing, GarminNotConfigured) as exc:
        print(f"probe stopped: {exc.__class__.__name__}")
        return 2
    except GarminConnectAuthenticationError:
        print("probe stopped: GarminConnectAuthenticationError")
        return 2

    out = Path(args.output)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(dump_report(report) + "\n", encoding="utf-8")
    print(dump_report(report))
    print(f"\n# wrote {out}")
    return 0 if probe_complete(report) else 1


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Probe the Garmin device calls.")
    parser.add_argument(
        "--push-workout-id",
        type=int,
        default=None,
        help="Push this existing workout id to the resolved device",
    )
    parser.add_argument(
        "--download-workout-id",
        type=int,
        default=None,
        help="Download this existing workout as FIT and parse it",
    )
    parser.add_argument(
        "--output",
        default=str(ROOT / ".garmin" / "probe-workout-device.json"),
        help="Redacted JSON report path",
    )
    args = parser.parse_args()
    for name in ("push_workout_id", "download_workout_id"):
        value = getattr(args, name)
        if value is not None and value <= 0:
            raise SystemExit(f"--{name.replace('_', '-')} must be a positive integer")
    return args


if __name__ == "__main__":
    raise SystemExit(main())
