"""Deterministic DJ transition policy and bounded running-order optimization."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any


def bpm_distance_ratio(left: dict[str, Any], right: dict[str, Any]) -> float:
    """Return the smallest relative BPM gap, including half/double-time equivalence."""
    first, second = float(left.get("bpm") or 0), float(right.get("bpm") or 0)
    if not first or not second:
        return 0.0
    return min(
        abs(first - adjusted) / min(first, adjusted)
        for adjusted in (second / 2, second, second * 2)
    )


def camelot_key(value: str) -> tuple[int, str] | None:
    match = re.fullmatch(r"(1[0-2]|[1-9])([AB])", value.strip().upper())
    return (int(match.group(1)), match.group(2)) if match else None


def weak_harmonic_transition(left: dict[str, Any], right: dict[str, Any]) -> bool:
    first = camelot_key(str(left.get("camelot") or left.get("key") or ""))
    second = camelot_key(str(right.get("camelot") or right.get("key") or ""))
    if not first or not second:
        return False
    distance = min((first[0] - second[0]) % 12, (second[0] - first[0]) % 12)
    return distance > 1 or (first[1] != second[1] and first[0] != second[0])


def transition_cost(left: dict[str, Any] | None, right: dict[str, Any]) -> float:
    if left is None:
        return 0.0
    bpm_cost = min(3.0, bpm_distance_ratio(left, right) * 10)
    key_cost = 1.2 if weak_harmonic_transition(left, right) else 0.0
    vocal_cost = 0.8 if left.get("vocals") == right.get("vocals") == "vocal-forward" else 0.0
    energy_cost = abs(float(left.get("energy") or 0.5) - float(right.get("energy") or 0.5)) * 0.5
    return bpm_cost + key_cost + vocal_cost + energy_cost


@dataclass(frozen=True)
class DeterministicTransitionOptimizer:
    """Order an already-selected track set without changing its membership or section allocation."""

    beam_width: int = 96

    def optimize(
        self,
        section_tracks: list[tuple[dict[str, Any], list[dict[str, Any]]]],
    ) -> list[tuple[str, dict[str, Any]]]:
        beam: list[tuple[float, tuple[tuple[str, dict[str, Any]], ...]]] = [(0.0, ())]
        for section, tracks in section_tracks:
            section_id = str(section.get("id") or "")
            for position in range(len(tracks)):
                expanded: list[tuple[float, tuple[tuple[str, dict[str, Any]], ...]]] = []
                for score, order in beam:
                    used = {track["id"] for chosen_section, track in order if chosen_section == section_id}
                    previous = order[-1][1] if order else None
                    for track in tracks:
                        if track["id"] in used:
                            continue
                        energy_cost = self._energy_position_cost(track, section, position, len(tracks))
                        expanded.append((
                            score + transition_cost(previous, track) + energy_cost,
                            (*order, (section_id, track)),
                        ))
                expanded.sort(key=lambda state: (
                    round(state[0], 8),
                    tuple(str(track.get("id") or "") for _, track in state[1]),
                ))
                beam = expanded[:self.beam_width]
        return list(beam[0][1]) if beam else []

    @staticmethod
    def _energy_position_cost(
        track: dict[str, Any], section: dict[str, Any], position: int, count: int
    ) -> float:
        start = float(section.get("energyStart") or 5) / 10
        end = float(section.get("energyEnd") or start * 10) / 10
        progress = position / max(1, count - 1)
        target = start + (end - start) * progress
        return abs(float(track.get("energy") or 0.5) - target) * 1.5
