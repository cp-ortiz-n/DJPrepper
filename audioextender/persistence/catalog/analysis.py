from __future__ import annotations

import json
from contextlib import closing
from typing import Any

from audioextender.persistence.base import RepositoryMixinBase
from audioextender.persistence.catalog.shared import catalog_now as _now


class TrackAnalysisStateRepositoryMixin(RepositoryMixinBase):
    """Persist analysis results that do not replace catalog metadata."""

    def update_audio_quality(self, track_id: int, result: dict[str, Any]) -> None:
        """Persist one quality assessment without changing music metadata."""
        now = _now()
        with self._lock, closing(self._connect()) as connection, connection:
            connection.execute(
                """UPDATE downloaded_tracks SET audio_quality_score=?,
                    audio_quality_label=?,audio_quality_json=?,audio_quality_analyzed_at=?,
                    updated_at=? WHERE id=?""",
                (
                    float(result["score"]),
                    str(result["label"]),
                    json.dumps(result, sort_keys=True),
                    now,
                    now,
                    track_id,
                ),
            )

    def audio_quality_summary(self) -> dict[str, Any]:
        """Return lightweight library-wide quality statistics for Settings."""
        with closing(self._connect()) as connection:
            row = connection.execute(
                """SELECT COUNT(*) AS total,
                    COUNT(audio_quality_score) AS analyzed,
                    AVG(audio_quality_score) AS average_score,
                    SUM(CASE WHEN audio_quality_label='excellent' THEN 1 ELSE 0 END) AS excellent,
                    SUM(CASE WHEN audio_quality_label='good' THEN 1 ELSE 0 END) AS good,
                    SUM(CASE WHEN audio_quality_label='review' THEN 1 ELSE 0 END) AS review,
                    SUM(CASE WHEN audio_quality_label='poor' THEN 1 ELSE 0 END) AS poor
                    FROM downloaded_tracks"""
            ).fetchone()
        return {key: (0 if value is None else value) for key, value in dict(row).items()}

    def update_downloaded_track_key_analysis(
        self,
        track_id: int,
        *,
        detected_key: str,
        confidence: float,
        candidates: list[dict[str, Any]],
    ) -> dict[str, Any]:
        """Save a key-only result without replacing the track's other analysis."""
        now = _now()
        with self._lock, closing(self._connect()) as connection, connection:
            connection.execute(
                """UPDATE downloaded_tracks SET detected_key=?, key_confidence=?,
                    key_candidates_json=?, key_analyzed_at=?, updated_at=? WHERE id=?""",
                (
                    detected_key,
                    confidence,
                    json.dumps(candidates, separators=(",", ":")),
                    now,
                    now,
                    track_id,
                ),
            )
        return self.get_downloaded_track(track_id) or {}
