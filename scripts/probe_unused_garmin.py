"""Print a Garmin probe report for one calendar day.

The web button uses app.garmin.probe. This command writes the same JSON under
.garmin/ for a local run. Token JSON is never printed.
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import date
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.garmin.probe import (  # noqa: E402
    DatabaseNotConfigured,
    EncryptionKeyMissing,
    GarminConnectAuthenticationError,
    GarminNotConfigured,
    probe_complete,
    probe_unused,
)


def main() -> int:
    args = _parse_args()
    try:
        report = probe_unused(args.date)
    except (DatabaseNotConfigured, EncryptionKeyMissing, GarminNotConfigured) as exc:
        print(f"probe stopped: {exc.__class__.__name__}: {_safe_text(exc)}")
        return 2
    except GarminConnectAuthenticationError as exc:
        print(f"probe stopped: GarminConnectAuthenticationError: {_safe_text(exc)}")
        return 2

    text = json.dumps(report, ensure_ascii=False, indent=2, default=_json_default)
    out = Path(args.output)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(text + "\n", encoding="utf-8")
    print(text)
    print(f"\n# wrote {out}")
    return 0 if probe_complete(report) else 1


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Probe unused Garmin Connect read methods.")
    parser.add_argument("--date", default="2026-10-14", help="Account calendar day, YYYY-MM-DD")
    parser.add_argument(
        "--output",
        default=str(ROOT / ".garmin" / "probe-unused-2026-10-14.json"),
        help="Redacted JSON report path",
    )
    args = parser.parse_args()
    try:
        args.date = date.fromisoformat(args.date)
    except ValueError as exc:
        raise SystemExit("date must be YYYY-MM-DD") from exc
    return args


def _safe_text(exc: BaseException) -> str:
    text = " ".join(str(exc).split())
    return text[:400]


def _json_default(value: Any) -> str:
    return str(value)


if __name__ == "__main__":
    raise SystemExit(main())
