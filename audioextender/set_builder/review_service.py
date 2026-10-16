"""Persistent human review and calibration reports for generated DJ sets."""

from __future__ import annotations

import uuid
from collections import Counter, defaultdict
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from audioextender.set_builder.preference_learning import JsonPreferenceStore


def _now() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")


def _rate(accepted: int, total: int) -> float | None:
    return round(accepted / total, 3) if total else None


@dataclass
class SetReviewService:
    """Store DJ judgments and derive transparent calibration evidence."""

    store: JsonPreferenceStore
    preference_profile: Callable[[str | None], dict[str, Any]]
    minimum_transition_evidence: int = 3

    def record(self, review: dict[str, Any]) -> dict[str, Any]:
        payload = self._payload()
        normalized: dict[str, Any] = {
            "id": str(review.get("id") or uuid.uuid4().hex),
            "setId": str(review.get("setId") or uuid.uuid4().hex),
            "setName": str(review.get("setName") or "Untitled set")[:200],
            "context": str(review.get("context") or "balanced").strip().casefold(),
            "overallDecision": str(review.get("overallDecision") or "unreviewed"),
            "notes": str(review.get("notes") or "")[:2000],
            "tracks": self._tracks(review.get("tracks") or []),
            "transitions": self._transitions(review.get("transitions") or []),
            "evaluation": review.get("evaluation") if isinstance(review.get("evaluation"), dict) else {},
            "comparison": review.get("comparison") if isinstance(review.get("comparison"), dict) else {},
            "createdAt": str(review.get("createdAt") or _now()),
        }
        payload["reviews"].append(normalized)
        payload["reviews"] = payload["reviews"][-1000:]
        self.store.save(payload)
        return {"review": normalized, "report": self.report(str(normalized["context"]))}

    def report(self, context: str | None = None) -> dict[str, Any]:
        normalized_context = str(context or "").strip().casefold()
        reviews = [
            review
            for review in self._payload()["reviews"]
            if not normalized_context or review.get("context") == normalized_context
        ]
        tracks = [track for review in reviews for track in review.get("tracks", [])]
        transitions = [item for review in reviews for item in review.get("transitions", [])]
        accepted = [track for track in tracks if track.get("decision") == "accept"]
        rejected = [track for track in tracks if track.get("decision") == "reject"]
        personalized = [track for track in tracks if float(track.get("preferenceAdjustment") or 0) != 0]
        neutral = [track for track in tracks if float(track.get("preferenceAdjustment") or 0) == 0]
        changed = [track for track in tracks if int(track.get("rankDelta") or 0) != 0]
        decisions: dict[str, set[str]] = defaultdict(set)
        for track in tracks:
            if track.get("decision") in {"accept", "reject"}:
                decisions[str(track.get("trackId"))].add(str(track["decision"]))
        contradictions = sorted(track_id for track_id, values in decisions.items() if len(values) > 1)
        direct = sum(
            int((review.get("evaluation") or {}).get("tierCounts", {}).get("direct") or 0) for review in reviews
        )
        expanded = sum(
            sum(int(tiers.get(name) or 0) for name in ("identity", "bridge", "fallback"))
            for review in reviews
            for tiers in [(review.get("evaluation") or {}).get("tierCounts", {})]
        )
        personalized_rate = _rate(sum(track.get("decision") == "accept" for track in personalized), len(personalized))
        neutral_rate = _rate(sum(track.get("decision") == "accept" for track in neutral), len(neutral))
        profile = self.preference_profile(normalized_context or None)
        recommendations = self._recommendations(profile, personalized_rate, neutral_rate, contradictions)
        return {
            "version": 1,
            "context": normalized_context or "all",
            "reviewCount": len(reviews),
            "overallAccepted": sum(review.get("overallDecision") == "accept" for review in reviews),
            "overallRejected": sum(review.get("overallDecision") == "reject" for review in reviews),
            "tracks": {
                "reviewed": len(accepted) + len(rejected),
                "accepted": len(accepted),
                "rejected": len(rejected),
                "rejectionReasons": dict(Counter(str(track.get("reason") or "unspecified") for track in rejected)),
                "changedByPersonalization": len(changed),
                "personalizedAcceptanceRate": personalized_rate,
                "neutralAcceptanceRate": neutral_rate,
                "acceptanceRateDelta": (
                    round(personalized_rate - neutral_rate, 3)
                    if personalized_rate is not None and neutral_rate is not None
                    else None
                ),
            },
            "catalogFit": {"direct": direct, "expanded": expanded},
            "contradictoryTrackIds": contradictions,
            "transitionProfile": self._transition_profile(transitions),
            "recommendations": recommendations,
            "recentReviews": list(reversed(reviews[-10:])),
        }

    def reset(self) -> dict[str, Any]:
        self.store.save({"version": 1, "reviews": []})
        return self.report()

    @staticmethod
    def _tracks(items: list[Any]) -> list[dict[str, Any]]:
        tracks: list[dict[str, Any]] = []
        for item in items:
            if not isinstance(item, dict) or not item.get("trackId"):
                continue
            tracks.append(
                {
                    "trackId": str(item["trackId"]),
                    "title": str(item.get("title") or "")[:300],
                    "decision": str(item.get("decision") or "unreviewed"),
                    "reason": str(item.get("reason") or "")[:200],
                    "features": item.get("features") if isinstance(item.get("features"), dict) else {},
                    "technicalScore": float(item.get("technicalScore") or 0),
                    "preferenceAdjustment": float(item.get("preferenceAdjustment") or 0),
                    "rankDelta": int(item.get("rankDelta") or 0),
                    "matchTier": str(item.get("matchTier") or "unknown"),
                }
            )
        return tracks

    @staticmethod
    def _transitions(items: list[Any]) -> list[dict[str, Any]]:
        transitions: list[dict[str, Any]] = []
        for item in items:
            if not isinstance(item, dict) or not item.get("pairId"):
                continue
            transitions.append(
                {
                    "pairId": str(item["pairId"]),
                    "rating": max(1, min(5, int(item.get("rating") or 3))),
                    "features": item.get("features") if isinstance(item.get("features"), dict) else {},
                }
            )
        return transitions

    def _transition_profile(self, transitions: list[dict[str, Any]]) -> dict[str, Any]:
        evidence: dict[tuple[str, str], dict[str, int]] = defaultdict(dict)
        for transition in transitions:
            vote = 1 if transition["rating"] >= 4 else -1 if transition["rating"] <= 2 else 0
            for dimension, raw_value in transition.get("features", {}).items():
                value = str(raw_value).strip().casefold()
                if value and vote:
                    evidence[(str(dimension), value)][transition["pairId"]] = vote
        active: list[dict[str, Any]] = []
        pending: list[dict[str, Any]] = []
        for (dimension, value), pairs in sorted(evidence.items()):
            signal = {
                "dimension": dimension,
                "value": value,
                "evidenceCount": len(pairs),
                "adjustment": max(-8, min(8, sum(pairs.values()) * 2)),
            }
            (active if len(pairs) >= self.minimum_transition_evidence else pending).append(signal)
        return {"activeSignals": active, "pendingSignals": pending, "reviewedTransitions": len(transitions)}

    @staticmethod
    def _recommendations(
        profile: dict[str, Any],
        personalized_rate: float | None,
        neutral_rate: float | None,
        contradictions: list[str],
    ) -> list[dict[str, str]]:
        recommendations = []
        if personalized_rate is not None and neutral_rate is not None and personalized_rate < neutral_rate:
            recommendations.append(
                {
                    "code": "personalization-underperforming",
                    "message": (
                        "Personalized tracks are accepted less often than neutral tracks; "
                        "review or pause active signals."
                    ),
                }
            )
        if contradictions:
            recommendations.append(
                {
                    "code": "contradictory-feedback",
                    "message": (
                        f"{len(contradictions)} tracks have both accepted and rejected judgments; "
                        "collect more context-specific evidence."
                    ),
                }
            )
        common = [
            signal
            for signal in profile.get("activeSignals", [])
            if signal.get("dimension") in {"bpm", "energy", "vocals"}
        ]
        if len(common) > max(2, len(profile.get("activeSignals", [])) // 2):
            recommendations.append(
                {
                    "code": "broad-signal-dominance",
                    "message": (
                        "Broad BPM, energy, or vocal signals dominate the profile; dismiss weak signals "
                        "or collect more genre and identity feedback."
                    ),
                }
            )
        return recommendations

    def _payload(self) -> dict[str, Any]:
        payload = self.store.load()
        reviews = payload.get("reviews") if isinstance(payload.get("reviews"), list) else []
        return {"version": 1, "reviews": reviews}
