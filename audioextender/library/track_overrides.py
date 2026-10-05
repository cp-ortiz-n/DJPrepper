"""Load optional, per-track musical boundaries supplied by the DJ."""

from __future__ import annotations

import json
import math
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class TrackOverride:
    intro_before: float | None = None
    outro_after: float | None = None
    outro_before: float | None = None


def load_track_overrides(path: Path) -> dict[str, TrackOverride]:
    """Return case-insensitive filename-to-musical-boundary mappings."""
    if not path.exists():
        return {}
    try:
        document = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise ValueError(f"Could not read track overrides from {path}: {error}") from error
    if not isinstance(document, dict):
        raise ValueError("Track overrides must be a JSON object keyed by filename")

    result: dict[str, TrackOverride] = {}
    for filename, settings in document.items():
        if not isinstance(filename, str) or not isinstance(settings, dict):
            raise ValueError("Each track override must map a filename to an object")
        values: dict[str, float | None] = {}
        for key in ("intro_before", "outro_after", "outro_before"):
            value = settings.get(key)
            if value is not None and (not isinstance(value, (int, float)) or not math.isfinite(value) or value <= 0):
                raise ValueError(f"{key} for {filename!r} must be a positive number")
            values[key] = float(value) if value is not None else None
        result[filename.casefold()] = TrackOverride(**values)
    return result
