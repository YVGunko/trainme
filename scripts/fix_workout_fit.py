"""Rebuild a workout FIT file whose name and step count are wrong.

The generator behind Adaptive_Hilly_Endurance_Edge840.fit wrote a control
character as the workout name (0x15) and left num_valid_steps at 16 while the
file holds 21 steps. Everything else already matches the intended session: 70
minutes, zones 2/3/4 at 30/30/10, no step longer than four minutes, cadence
95-105 except 85-92 on the Z4 steps.

Every message is copied through untouched except the workout name and the step
count, so intervals, targets and cadences are not reinterpreted on the way.
"""

from __future__ import annotations

import io
import struct
import sys
from pathlib import Path

import fitdecode
from fitdecode.utils import compute_crc

SOURCE = Path("/Volumes/Transcend/Downloads/Adaptive_Hilly_Endurance_Edge840.fit")
TARGET = Path("/Volumes/Transcend/Downloads/Adaptive_Hilly_Endurance_Edge840_fixed.fit")
NAME = "Adaptive Hilly Endurance"

WORKOUT_MESG = 26
WORKOUT_STEP_MESG = 27
FIELD_NUM_STEPS = 6
FIELD_NAME = 8

# base byte -> byte width, for the types a workout file actually uses
_WIDTHS = {0x00: 1, 0x01: 1, 0x02: 1, 0x07: 1, 0x83: 2, 0x84: 2,
           0x85: 4, 0x86: 4, 0x88: 4, 0x89: 8, 0x0A: 1, 0x8B: 2, 0x8C: 4}
_SIGNED = {0x01, 0x83, 0x85}
_STRING = 0x07
_UINT16 = 0x84


class FitRebuildError(Exception):
    """Raised when the source file cannot be read as a workout."""


def rebuild(payload: bytes, name: str) -> bytes:
    """Return a FIT file with the workout name set and the step count corrected."""
    messages = _messages(payload)
    steps = sum(1 for global_num, _ in messages if global_num == WORKOUT_STEP_MESG)
    if steps == 0:
        raise FitRebuildError("File has no workout steps")

    chunks: list[bytes] = []
    for global_num, fields in messages:
        if global_num == WORKOUT_MESG:
            fields = _retitle(fields, name, steps)
        chunks.append(_encode_message(global_num, fields))

    data = b"".join(chunks)
    header = struct.pack("<BBHI4s", 14, 0x20, 2132, len(data), b".FIT")
    header += struct.pack("<H", compute_crc(header))
    return header + data + struct.pack("<H", compute_crc(data))


def _messages(payload: bytes) -> list[tuple[int, list[tuple[int, int, bytes]]]]:
    """Return each message as (global number, [(field number, base byte, bytes)]).

    The base type comes from the field definition rather than its decoded name.
    A name like date_time or file can decode to whichever base type the file
    used, and guessing from the name is how a uint32 ends up packed as one byte.
    """
    found: list[tuple[int, list[tuple[int, int, bytes]]]] = []
    try:
        with fitdecode.FitReader(io.BytesIO(payload)) as reader:
            for frame in reader:
                if not isinstance(frame, fitdecode.FitDataMessage):
                    continue
                fields = [
                    (field.def_num, _base_byte(field), _encode(field, _base_byte(field)))
                    for field in frame.fields
                ]
                found.append((frame.def_mesg.global_mesg_num, fields))
    except Exception as error:
        raise FitRebuildError(f"Could not read the file: {type(error).__name__}") from error
    return found


def _base_byte(field: object) -> int:
    base_type = getattr(field.type, "base_type", None) or field.type
    identifier = getattr(base_type, "identifier", None)
    return identifier if isinstance(identifier, int) else 0x02


def _encode(field: object, base: int) -> bytes:
    if base == _STRING:
        return (field.value or "").encode() + b"\x00"
    if base == 0x88:
        return struct.pack("<f", float(field.value or 0))
    if base == 0x89:
        return struct.pack("<d", float(field.value or 0))
    raw = getattr(field, "raw_value", None)
    value = int(raw if raw is not None else (field.value or 0))
    return _pack(base, value)


def _pack(base: int, value: int) -> bytes:
    return value.to_bytes(_WIDTHS.get(base, 1), "little", signed=base in _SIGNED)


def _retitle(
    fields: list[tuple[int, int, bytes]], name: str, steps: int
) -> list[tuple[int, int, bytes]]:
    """Set the name and the step count, keeping every other field in place."""
    out: list[tuple[int, int, bytes]] = []
    seen_name = seen_steps = False
    for def_num, base, encoded in fields:
        if def_num == FIELD_NAME:
            out.append((def_num, _STRING, name.encode() + b"\x00"))
            seen_name = True
        elif def_num == FIELD_NUM_STEPS:
            out.append((def_num, _UINT16, _pack(_UINT16, steps)))
            seen_steps = True
        else:
            out.append((def_num, base, encoded))
    if not seen_name:
        out.append((FIELD_NAME, _STRING, name.encode() + b"\x00"))
    if not seen_steps:
        out.append((FIELD_NUM_STEPS, _UINT16, _pack(_UINT16, steps)))
    return out


def _encode_message(global_num: int, fields: list[tuple[int, int, bytes]]) -> bytes:
    definition = bytearray([0x40, 0, 0])
    definition += struct.pack("<HB", global_num, len(fields))
    for def_num, base, encoded in fields:
        definition += bytes([def_num, len(encoded), base])
    return bytes(definition) + bytes([0]) + b"".join(e for _, _, e in fields)


def describe(path: Path) -> None:
    """Print the workout summary so a rebuild can be checked by eye."""
    with fitdecode.FitReader(io.BytesIO(path.read_bytes())) as reader:
        minutes: dict[int, float] = {}
        longest = 0.0
        steps = 0
        for frame in reader:
            if not isinstance(frame, fitdecode.FitDataMessage):
                continue
            if frame.name == "workout":
                name = frame.get_field(8)
                declared = frame.get_field(6)
                print(f"  name: {name.value!r}" if name else "  name: none")
                print(f"  declared steps: {declared.value if declared else 'none'}")
            elif frame.name == "workout_step":
                steps += 1
                seconds = frame.get_field(2)
                zone = frame.get_field(4)
                length = float(seconds.value or 0)
                longest = max(longest, length)
                zone_number = int(zone.value or 0)
                minutes[zone_number] = minutes.get(zone_number, 0.0) + length
        print(f"  steps in file: {steps}")
        print(f"  total: {sum(minutes.values()) / 60:.1f} min")
        print(f"  longest step: {longest / 60:.1f} min")
        print(
            "  minutes by zone:",
            {zone: round(seconds / 60, 1) for zone, seconds in sorted(minutes.items())},
        )


def main() -> int:
    if not SOURCE.exists():
        print(f"missing source: {SOURCE}")
        return 2
    print("before:")
    describe(SOURCE)
    result = rebuild(SOURCE.read_bytes(), NAME)
    TARGET.write_bytes(result)
    print(f"\nafter ({TARGET.name}, {len(result)} bytes):")
    describe(TARGET)
    return 0


if __name__ == "__main__":
    sys.exit(main())
