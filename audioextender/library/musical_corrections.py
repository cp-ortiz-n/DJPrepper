"""Delivery-time precedence for durable user-confirmed musical facts."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class MusicalCorrectionIndex:
    """Apply manual corrections without overwriting detected analysis evidence."""

    keys: dict[str, dict[str, Any]]
    bpms: dict[str, dict[str, Any]]

    @classmethod
    def from_records(
        cls,
        key_records: list[dict[str, Any]],
        bpm_records: list[dict[str, Any]],
    ) -> MusicalCorrectionIndex:
        def indexed(records: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
            return {str(item["source_name"]).casefold(): item for item in records}

        return cls(keys=indexed(key_records), bpms=indexed(bpm_records))

    def apply(
        self,
        song: dict[str, Any],
        source_name: str,
        *,
        detected_bpm_fallback: float | None = None,
    ) -> dict[str, Any]:
        corrected = dict(song)
        identity = source_name.casefold()
        if verification := self.keys.get(identity):
            corrected.update(
                detected_key=corrected.get("key"),
                key=verification["verified_key"],
                key_confidence=1.0,
                key_verified=True,
            )
        if verification := self.bpms.get(identity):
            corrected.update(
                detected_bpm=corrected.get("bpm") or detected_bpm_fallback or 0,
                bpm=float(verification["verified_bpm"]),
                bpm_verified=True,
            )
        return corrected
