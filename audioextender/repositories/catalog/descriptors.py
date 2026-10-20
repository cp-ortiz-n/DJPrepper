from __future__ import annotations

from contextlib import closing
from typing import Any

from audioextender.library.identity_inference import unknown_playlist_signals
from audioextender.repositories.base import RepositoryMixinBase
from audioextender.repositories.catalog.shared import catalog_now as _now


class TrackDescriptorRepositoryMixin(RepositoryMixinBase):
    def identity_vocabulary_rules(self, *, status: str | None = None) -> list[dict[str, Any]]:
        with closing(self._connect()) as connection:
            sql = "SELECT signal,category,value,status,source,confidence,updated_at FROM identity_vocabulary_rules"
            parameters: tuple[Any, ...] = ()
            if status:
                sql += " WHERE status=?"
                parameters = (status,)
            rows = connection.execute(sql + " ORDER BY signal", parameters).fetchall()
        return [dict(row) for row in rows]

    def save_identity_vocabulary_rule(
        self,
        *,
        signal: str,
        category: str = "",
        value: str = "",
        status: str = "approved",
        source: str = "manual",
        confidence: float = 1.0,
    ) -> dict[str, Any]:
        signal = signal.strip().casefold()
        with self._lock, closing(self._connect()) as connection, connection:
            connection.execute(
                """INSERT INTO identity_vocabulary_rules
                (signal,category,value,status,source,confidence,updated_at)
                VALUES (?,?,?,?,?,?,?) ON CONFLICT(signal) DO UPDATE SET
                category=excluded.category,value=excluded.value,status=excluded.status,
                source=excluded.source,confidence=excluded.confidence,updated_at=excluded.updated_at""",
                (
                    signal,
                    category.strip().casefold(),
                    value.strip().casefold(),
                    status,
                    source,
                    max(0.0, min(1.0, confidence)),
                    _now(),
                ),
            )
        return next(rule for rule in self.identity_vocabulary_rules() if rule["signal"] == signal)

    def identity_vocabulary_review(self) -> list[dict[str, Any]]:
        rules = {rule["signal"]: rule for rule in self.identity_vocabulary_rules()}
        with closing(self._connect()) as connection:
            rows = connection.execute(
                """SELECT playlist_name,COUNT(DISTINCT track_id) track_count
                FROM downloaded_track_playlists GROUP BY playlist_name"""
            ).fetchall()
        aggregated: dict[str, dict[str, Any]] = {}
        for row in rows:
            playlist, count = str(row["playlist_name"]), int(row["track_count"])
            for signal in unknown_playlist_signals([playlist]):
                item = aggregated.setdefault(signal, {"signal": signal, "track_count": 0, "examples": []})
                item["track_count"] += count
                if playlist not in item["examples"] and len(item["examples"]) < 3:
                    item["examples"].append(playlist)
        for signal, item in aggregated.items():
            item["rule"] = rules.get(signal)
        return sorted(aggregated.values(), key=lambda item: (-item["track_count"], item["signal"]))

    def track_ids_for_vocabulary_signal(self, signal: str) -> list[int]:
        with closing(self._connect()) as connection:
            rows = connection.execute(
                "SELECT track_id,playlist_name FROM downloaded_track_playlists ORDER BY track_id"
            ).fetchall()
        return sorted(
            {int(row["track_id"]) for row in rows if signal in unknown_playlist_signals([str(row["playlist_name"])])}
        )

    def track_ids_missing_inferred_identity(self) -> list[int]:
        """Return tracks missing identity or carrying descriptors from an older inference model."""
        with closing(self._connect()) as connection:
            rows = connection.execute(
                """SELECT tracks.id FROM downloaded_tracks tracks
                WHERE tracks.identity_inference_locked=0 AND (NOT EXISTS (
                    SELECT 1 FROM downloaded_track_descriptors descriptors
                    WHERE descriptors.track_id=tracks.id
                    AND descriptors.provenance IN ('inferred','crate'))
                OR EXISTS (
                    SELECT 1 FROM downloaded_track_descriptors stale
                    WHERE stale.track_id=tracks.id AND (
                        (stale.provenance='crate' AND stale.value NOT IN (
                            'party','indian party','ecuadorian party','latin party',
                            'workout / gym','rave','dancefloor','scratch practice',
                            'turntablism','running','boiler room / live set','after-hours'
                        ))
                        OR (stale.provenance='inferred' AND stale.category='familiarity'
                            AND stale.value='recognizable material')
                    )))
                ORDER BY tracks.id"""
            ).fetchall()
        return [int(row[0]) for row in rows]

    def track_ids_available_for_identity_inference(self) -> list[int]:
        """Return every track the DJ has not protected as manually approved."""
        with closing(self._connect()) as connection:
            rows = connection.execute(
                "SELECT id FROM downloaded_tracks WHERE identity_inference_locked=0 ORDER BY id"
            ).fetchall()
        return [int(row[0]) for row in rows]

    def track_identity_inference_status(self, track_id: int) -> dict[str, Any] | None:
        """Return durable inference protection and descriptor provenance for one track."""
        with closing(self._connect()) as connection:
            row = connection.execute(
                """SELECT tracks.identity_inference_locked,
                EXISTS(SELECT 1 FROM downloaded_track_descriptors descriptors
                    WHERE descriptors.track_id=tracks.id AND descriptors.provenance='manual') has_manual
                FROM downloaded_tracks tracks WHERE tracks.id=?""",
                (track_id,),
            ).fetchone()
        if row is None:
            return None
        return {
            "protected_from_inference": bool(row["identity_inference_locked"]),
            "has_manual_descriptors": bool(row["has_manual"]),
        }

    def set_track_identity_inference_protection(self, track_ids: list[int], protected: bool) -> dict[str, Any]:
        wanted = list(dict.fromkeys(int(track_id) for track_id in track_ids))
        with self._lock, closing(self._connect()) as connection, connection:
            existing = (
                {
                    int(row[0])
                    for row in connection.execute(
                        f"SELECT id FROM downloaded_tracks WHERE id IN ({','.join('?' for _ in wanted)})", wanted
                    ).fetchall()
                }
                if wanted
                else set()
            )
            connection.executemany(
                "UPDATE downloaded_tracks SET identity_inference_locked=?,updated_at=? WHERE id=?",
                [(int(protected), _now(), track_id) for track_id in existing],
            )
        return {"requested": len(wanted), "updated": len(existing), "missing": sorted(set(wanted) - existing)}

    def replace_inferred_track_descriptors(self, track_id: int, descriptors: list[dict[str, Any]]) -> dict[str, Any]:
        """Refresh machine/crate descriptors unless this track is manually protected."""
        status = self.track_identity_inference_status(track_id)
        if status is None:
            return {"requested": 1, "updated": 0, "missing": [track_id], "skipped_protected": False}
        if status["protected_from_inference"]:
            return {"requested": 1, "updated": 0, "missing": [], "skipped_protected": True}
        with self._lock, closing(self._connect()) as connection, connection:
            connection.execute(
                "DELETE FROM downloaded_track_descriptors WHERE track_id=? AND provenance!='manual'",
                (track_id,),
            )
        return {**self.update_track_descriptors([track_id], descriptors, mode="add"), "skipped_protected": False}

    def track_identity_inference_context(self, track_id: int) -> dict[str, Any] | None:
        """Collect catalog, playlist, and latest analysis evidence for inference."""
        with closing(self._connect()) as connection:
            row = connection.execute(
                """SELECT tracks.id,tracks.title,tracks.artist,tracks.filename,tracks.genre,
                    tracks.genre_category,
                    (SELECT GROUP_CONCAT(p.playlist_name,'||') FROM downloaded_track_playlists p
                     WHERE p.track_id=tracks.id) AS playlists,
                    idx.category AS library_category,idx.detail_genre AS library_detail_genre,
                    idx.roles AS library_roles,idx.energy_band,idx.vocals,idx.timing
                    FROM downloaded_tracks tracks
                    LEFT JOIN library_search_index idx ON idx.job_id=(
                        SELECT MAX(latest.job_id) FROM library_search_index latest
                        WHERE latest.downloaded_id=tracks.id)
                    WHERE tracks.id=?""",
                (track_id,),
            ).fetchone()
        if row is None:
            return None
        result = dict(row)
        result["playlists"] = [value for value in str(result.get("playlists") or "").split("||") if value]
        return result

    def track_descriptors(self, track_id: int) -> list[dict[str, Any]]:
        """Return durable musical-identity descriptors and their provenance."""
        with closing(self._connect()) as connection:
            rows = connection.execute(
                """SELECT category,value,provenance,confidence,updated_at
                FROM downloaded_track_descriptors WHERE track_id=?
                ORDER BY category,value COLLATE NOCASE""",
                (track_id,),
            ).fetchall()
        return [dict(row) for row in rows]

    def update_track_descriptors(
        self,
        track_ids: list[int],
        descriptors: list[dict[str, Any]],
        *,
        mode: str = "replace",
    ) -> dict[str, Any]:
        """Add, remove, or replace descriptors atomically across selected tracks."""
        wanted = list(dict.fromkeys(int(track_id) for track_id in track_ids))
        normalized: list[tuple[str, str, str, float]] = []
        for descriptor in descriptors:
            category = str(descriptor.get("category") or "context").strip().casefold()
            value = str(descriptor.get("value") or "").strip().casefold()
            provenance = str(descriptor.get("provenance") or "manual").strip().casefold()
            confidence = max(0.0, min(1.0, float(descriptor.get("confidence", 1.0))))
            if value:
                normalized.append((category, value, provenance, confidence))
        now = _now()
        with self._lock, closing(self._connect()) as connection, connection:
            existing = (
                {
                    int(row[0])
                    for row in connection.execute(
                        f"SELECT id FROM downloaded_tracks WHERE id IN ({','.join('?' for _ in wanted)})",
                        wanted,
                    ).fetchall()
                }
                if wanted
                else set()
            )
            if mode == "replace":
                connection.executemany(
                    "DELETE FROM downloaded_track_descriptors WHERE track_id=?",
                    [(track_id,) for track_id in existing],
                )
            elif mode == "remove" and normalized:
                connection.executemany(
                    "DELETE FROM downloaded_track_descriptors WHERE track_id=? AND category=? AND value=?",
                    [(track_id, category, value) for track_id in existing for category, value, _, _ in normalized],
                )
            if mode in {"replace", "add"} and normalized:
                connection.executemany(
                    """INSERT INTO downloaded_track_descriptors
                    (track_id,category,value,provenance,confidence,updated_at)
                    VALUES (?,?,?,?,?,?) ON CONFLICT(track_id,category,value) DO UPDATE SET
                    provenance=CASE WHEN downloaded_track_descriptors.provenance='manual'
                        AND excluded.provenance!='manual' THEN downloaded_track_descriptors.provenance
                        ELSE excluded.provenance END,
                    confidence=CASE WHEN downloaded_track_descriptors.provenance='manual'
                        AND excluded.provenance!='manual' THEN downloaded_track_descriptors.confidence
                        ELSE excluded.confidence END,
                    updated_at=excluded.updated_at""",
                    [
                        (track_id, category, value, provenance, confidence, now)
                        for track_id in existing
                        for category, value, provenance, confidence in normalized
                    ],
                )
        return {
            "requested": len(wanted),
            "updated": len(existing),
            "missing": sorted(set(wanted) - existing),
            "mode": mode,
            "descriptors": len(normalized),
            "survives_restart": True,
        }
