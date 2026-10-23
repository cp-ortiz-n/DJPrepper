"""Local, explainable DJ-preference learning for Set Builder ranking."""

from __future__ import annotations

import json
import threading
import uuid
from collections import defaultdict
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

ACTION_WEIGHTS = {
    "keep": 1.0,
    "lock": 2.0,
    "save": 1.0,
    "export": 1.0,
    "replace-in": 2.0,
    "remove": -2.0,
    "replace-out": -2.0,
}
FEATURE_DIMENSIONS = {"genre", "descriptor", "artist", "vocals", "energy", "bpm"}
REKORDBOX_RATING_POLICY_VERSION = 1
REKORDBOX_RATING_ADJUSTMENTS = {1: -4.0, 2: -2.0, 3: 0.0, 4: 2.0, 5: 4.0}


def _now() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")


def _terms(value: Any) -> list[str]:
    values = value if isinstance(value, list) else [value]
    return sorted({str(item).strip().casefold() for item in values if str(item).strip()})


def candidate_features(track: dict[str, Any]) -> dict[str, list[str]]:
    energy = float(track.get("energy") or 0.5)
    bpm = float(track.get("bpm") or 0)
    return {
        "genre": _terms([track.get("genre"), *track.get("detailedGenres", [])]),
        "descriptor": _terms(
            [descriptor.get("value") for descriptor in track.get("descriptors", []) if isinstance(descriptor, dict)]
        ),
        "artist": _terms(track.get("artist")),
        "vocals": _terms(track.get("vocals")),
        "energy": ["low" if energy < 0.4 else "high" if energy >= 0.7 else "medium"],
        "bpm": ["unknown" if not bpm else f"{int(bpm // 10) * 10}s"],
    }


@dataclass
class JsonPreferenceStore:
    path: Path
    _lock: threading.RLock = field(default_factory=threading.RLock, init=False)

    def load(self) -> dict[str, Any]:
        with self._lock:
            try:
                payload = json.loads(self.path.read_text(encoding="utf-8"))
                return payload if isinstance(payload, dict) else {}
            except (OSError, ValueError):
                return {}

    def save(self, payload: dict[str, Any]) -> None:
        with self._lock:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            temporary = self.path.with_suffix(".pending.json")
            temporary.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
            temporary.replace(self.path)


@dataclass
class DJPreferenceService:
    store: JsonPreferenceStore
    minimum_distinct_tracks: int = 3
    maximum_adjustment: float = 8.0

    def record(self, events: list[dict[str, Any]]) -> dict[str, Any]:
        payload = self._payload()
        known_ids = {str(event.get("id")) for event in payload["events"]}
        accepted = 0
        for raw in events:
            action = str(raw.get("action") or "")
            track_id = str(raw.get("trackId") or "")
            if action not in ACTION_WEIGHTS or not track_id:
                continue
            event_id = str(raw.get("id") or uuid.uuid4().hex)
            if event_id in known_ids:
                continue
            features = {
                dimension: _terms(values)
                for dimension, values in (raw.get("features") or {}).items()
                if dimension in FEATURE_DIMENSIONS and _terms(values)
            }
            payload["events"].append(
                {
                    "id": event_id,
                    "action": action,
                    "trackId": track_id,
                    "context": str(raw.get("context") or "balanced").strip().casefold(),
                    "features": features,
                    "createdAt": str(raw.get("createdAt") or _now()),
                }
            )
            known_ids.add(event_id)
            accepted += 1
        payload["events"] = payload["events"][-10000:]
        self.store.save(payload)
        context = str(events[0].get("context") or "balanced") if events else None
        return {"recorded": accepted, "profile": self.profile(context)}

    def profile(self, context: str | None = None) -> dict[str, Any]:
        payload = self._payload()
        ignored = {
            (str(item.get("dimension") or ""), str(item.get("value") or ""))
            for item in payload["ignoredSignals"]
        }
        normalized_context = str(context or "").strip().casefold()
        per_signal_track: dict[tuple[str, str], dict[str, float]] = defaultdict(dict)
        for event in payload["events"]:
            event_context = str(event.get("context") or "balanced").casefold()
            if normalized_context and event_context not in {normalized_context, "global"}:
                continue
            weight = ACTION_WEIGHTS.get(str(event.get("action") or ""), 0)
            track_id = str(event.get("trackId") or "")
            for dimension, values in (event.get("features") or {}).items():
                for value in _terms(values):
                    key = (str(dimension), value)
                    per_signal_track[key][track_id] = max(
                        -2.0, min(2.0, per_signal_track[key].get(track_id, 0) + weight)
                    )
        active: list[dict[str, Any]] = []
        pending: list[dict[str, Any]] = []
        for (dimension, value), tracks in sorted(per_signal_track.items()):
            if (dimension, value) in ignored:
                continue
            evidence = len(tracks)
            score = sum(tracks.values())
            signal = {
                "dimension": dimension,
                "value": value,
                "evidenceCount": evidence,
                "adjustment": round(max(-self.maximum_adjustment, min(self.maximum_adjustment, score)), 2),
            }
            (active if evidence >= self.minimum_distinct_tracks and score else pending).append(signal)
        return {
            "version": 1,
            "enabled": bool(payload.get("enabled", True)),
            "context": normalized_context or "all",
            "minimumDistinctTracks": self.minimum_distinct_tracks,
            "eventCount": len(payload["events"]),
            "activeSignals": active,
            "pendingSignals": pending,
            "ignoredSignals": payload["ignoredSignals"],
        }

    def set_enabled(self, enabled: bool) -> dict[str, Any]:
        payload = self._payload()
        payload["enabled"] = bool(enabled)
        self.store.save(payload)
        return self.profile()

    def reset(self) -> dict[str, Any]:
        self.store.save({"version": 1, "enabled": True, "events": [], "ignoredSignals": []})
        return self.profile()

    def dismiss_signal(self, dimension: str, value: str) -> dict[str, Any]:
        payload = self._payload()
        signal = {"dimension": dimension.strip().casefold(), "value": value.strip().casefold()}
        if signal["dimension"] in FEATURE_DIMENSIONS and signal["value"]:
            payload["ignoredSignals"] = [
                item for item in payload["ignoredSignals"]
                if item != signal
            ] + [signal]
            self.store.save(payload)
        return self.profile()

    def _payload(self) -> dict[str, Any]:
        payload = self.store.load()
        events = payload.get("events") if isinstance(payload.get("events"), list) else []
        ignored = payload.get("ignoredSignals") if isinstance(payload.get("ignoredSignals"), list) else []
        return {
            "version": 1,
            "enabled": bool(payload.get("enabled", True)),
            "events": events,
            "ignoredSignals": ignored,
        }


@dataclass(frozen=True)
class PersonalizedCandidateRanker:
    profile_loader: Callable[[str | None], dict[str, Any]]
    maximum_adjustment: float = 8.0

    def adjustment(self, track: dict[str, Any], context: str | None) -> tuple[float, list[str]]:
        profile = self.profile_loader(context)
        if not profile.get("enabled"):
            return 0.0, []
        features = candidate_features(track)
        matched = [
            signal
            for signal in profile.get("activeSignals", [])
            if signal.get("value") in features.get(str(signal.get("dimension") or ""), [])
        ]
        # Damp the combined signal so broad attributes such as BPM and energy do not
        # immediately saturate the cap and hide a more distinctive genre or descriptor.
        learned_adjustment = sum(float(signal.get("adjustment") or 0) for signal in matched) * 0.5
        reasons = [
            f"Learned {signal['dimension']} preference: {signal['value']} ({signal['evidenceCount']} distinct tracks)."
            for signal in matched
        ]
        external = track.get("externalRating") or {}
        rating = int(external.get("rating") or 0) if isinstance(external, dict) else 0
        rating_adjustment = REKORDBOX_RATING_ADJUSTMENTS.get(rating, 0.0)
        if rating_adjustment:
            synced = str(external.get("synced_at") or "").split("T", 1)[0]
            reasons.append(
                f"Rekordbox rating: {rating} stars ({rating_adjustment:+g})"
                + (f", synced {synced}." if synced else ".")
            )
        adjustment = max(
            -self.maximum_adjustment,
            min(self.maximum_adjustment, learned_adjustment + rating_adjustment),
        )
        return round(adjustment, 2), reasons
