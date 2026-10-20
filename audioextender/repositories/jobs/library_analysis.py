from __future__ import annotations

import json
from contextlib import closing
from datetime import UTC, datetime
from typing import Any

from audioextender.repositories.base import RepositoryMixinBase


def _now() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")


class LibraryAnalysisRepositoryMixin(RepositoryMixinBase):
    def library_index_source_signature(self) -> str:
        """Return a stable logical signature unaffected by unrelated SQLite writes."""
        with closing(self._connect()) as connection:
            jobs = connection.execute(
                "SELECT COUNT(*), COALESCE(MAX(id),0), COALESCE(MAX(updated_at),'') FROM jobs WHERE status='complete'"
            ).fetchone()
            tracks = connection.execute(
                "SELECT COUNT(*), COALESCE(MAX(id),0), COALESCE(MAX(updated_at),'') FROM downloaded_tracks"
            ).fetchone()
            indexed = int(connection.execute("SELECT COUNT(*) FROM library_search_index").fetchone()[0])
        return json.dumps({"jobs": list(jobs), "tracks": list(tracks), "indexed": indexed}, separators=(",", ":"))

    def catalog_source_signatures(self) -> dict[str, tuple[int, int]]:
        with closing(self._connect()) as connection:
            rows = connection.execute("SELECT source_path,mtime_ns,size FROM catalog_source_index").fetchall()
        return {str(row["source_path"]): (int(row["mtime_ns"]), int(row["size"])) for row in rows}

    def upsert_catalog_source_signatures(self, signatures: list[tuple[str, int, int]]) -> None:
        if not signatures:
            return
        now = _now()
        with self._lock, closing(self._connect()) as connection, connection:
            connection.executemany(
                """INSERT INTO catalog_source_index
                    (source_path,mtime_ns,size,scanned_at) VALUES (?,?,?,?)
                    ON CONFLICT(source_path) DO UPDATE SET
                    mtime_ns=excluded.mtime_ns,size=excluded.size,
                    scanned_at=excluded.scanned_at""",
                [(path, mtime, size, now) for path, mtime, size in signatures],
            )

    def replace_library_search_index(self, entries: list[dict[str, Any]]) -> None:
        """Atomically refresh the compact, queryable latest-generation Library index."""
        columns = (
            "job_id",
            "source_name",
            "title",
            "artist",
            "downloaded_id",
            "category",
            "detail_genre",
            "roles",
            "preset",
            "requested_preset",
            "result",
            "bpm",
            "musical_key",
            "camelot",
            "energy",
            "energy_band",
            "vocals",
            "timing",
            "updated_at",
            "analysis_json",
            "set_analysis_json",
        )
        with self._lock, closing(self._connect()) as connection, connection:
            connection.execute("DELETE FROM library_search_index")
            if entries:
                connection.executemany(
                    f"INSERT INTO library_search_index ({','.join(columns)}) VALUES ({','.join('?' for _ in columns)})",
                    [
                        tuple(
                            entry.get(column, "{}")
                            if column == "set_analysis_json"
                            else entry.get(column, "")
                            if column == "detail_genre"
                            else entry.get(column)
                            for column in columns
                        )
                        for entry in entries
                    ],
                )

    def page_library_tracks(
        self,
        *,
        page: int,
        page_size: int,
        search: str = "",
        role: str = "all",
        category: str = "all",
        detail_genre: str = "all",
        preset: str = "all",
        result: str = "all",
        quality: str = "all",
        bpm_min: float | None = None,
        bpm_max: float | None = None,
        musical_key: str = "all",
        energy: str = "all",
        vocals: str = "all",
        timing: str = "all",
        sort: str = "newest",
    ) -> tuple[list[dict[str, Any]], int]:
        conditions: list[str] = []
        parameters: list[Any] = []
        if search.strip():
            value = f"%{search.strip().casefold()}%"
            conditions.append(
                "(LOWER(idx.source_name) LIKE ? OR LOWER(idx.title) LIKE ? OR "
                "LOWER(idx.artist) LIKE ? OR LOWER(idx.category) LIKE ? OR LOWER(idx.detail_genre) LIKE ? OR "
                "LOWER(idx.roles) LIKE ? OR LOWER(idx.preset) LIKE ? OR "
                "LOWER(idx.musical_key) LIKE ? OR LOWER(idx.camelot) LIKE ? OR "
                "LOWER(COALESCE(tracks.recording_code, '')) LIKE ? OR "
                "LOWER(COALESCE(tracks.recording_code, '') || '-' || "
                "COALESCE(tracks.version_code, '')) LIKE ? OR "
                "EXISTS (SELECT 1 FROM downloaded_track_descriptors search_descriptor "
                "WHERE search_descriptor.track_id = tracks.id AND LOWER(search_descriptor.value) LIKE ?))"
            )
            parameters.extend([value] * 12)
        if role != "all":
            conditions.append("idx.roles LIKE ?")
            parameters.append(f"%|{role}|%")
        if category != "all":
            conditions.append("(LOWER(idx.category) = ? OR LOWER(idx.category) LIKE ?)")
            normalized = category.casefold()
            parameters.extend((normalized, f"{normalized} / %"))
        if detail_genre != "all":
            conditions.append(
                "(',' || REPLACE(REPLACE(LOWER(COALESCE(idx.detail_genre, '')), ', ', ','), ' ,', ',') || ',') LIKE ?"
            )
            parameters.append(f"%,{detail_genre.strip().casefold()},%")
        for column, value in (
            ("preset", preset),
            ("result", result),
            ("musical_key", musical_key),
            ("energy_band", energy),
            ("vocals", vocals),
            ("timing", timing),
        ):
            if value != "all":
                conditions.append(f"idx.{column} = ?")
                parameters.append(value)
        if bpm_min is not None:
            conditions.append("idx.bpm >= ?")
            parameters.append(bpm_min)
        if bpm_max is not None:
            conditions.append("idx.bpm <= ?")
            parameters.append(bpm_max)
        quality_conditions = {
            "excellent": "tracks.audio_quality_label = 'excellent'",
            "good": "tracks.audio_quality_label = 'good'",
            "review": "tracks.audio_quality_label = 'review'",
            "poor": "tracks.audio_quality_label = 'poor'",
            "below-target": "tracks.audio_quality_label IN ('review','poor')",
            "unanalyzed": "tracks.audio_quality_score IS NULL",
        }
        if quality in quality_conditions:
            conditions.append(quality_conditions[quality])
        where = f"WHERE {' AND '.join(conditions)}" if conditions else ""
        order = {
            "title": "idx.title COLLATE NOCASE, idx.job_id",
            "bpm-up": "idx.bpm, idx.job_id",
            "bpm-down": "idx.bpm DESC, idx.job_id DESC",
            "energy-down": "idx.energy DESC, idx.job_id DESC",
            "newest": "idx.updated_at DESC, idx.job_id DESC",
        }.get(sort, "idx.updated_at DESC, idx.job_id DESC")
        with closing(self._connect()) as connection:
            total = int(
                connection.execute(
                    f"""SELECT COUNT(*) FROM library_search_index idx
                    LEFT JOIN downloaded_tracks tracks ON tracks.id = idx.downloaded_id
                    {where}""",
                    parameters,
                ).fetchone()[0]
            )
            rows = connection.execute(
                f"""SELECT jobs.id, jobs.source_name, jobs.source_path, jobs.status,
                    jobs.progress, jobs.stage, jobs.preset, jobs.intro_bars, jobs.outro_bars,
                    jobs.use_stems, jobs.config_json, jobs.error, jobs.extended_path, jobs.wav_path,
                    jobs.intro_preview_path, jobs.outro_preview_path, jobs.cue_sheet_path,
                    jobs.rekordbox_path, jobs.parent_job_id, jobs.bpm, jobs.intro_quality,
                    jobs.outro_quality, jobs.review_status, jobs.created_at, jobs.updated_at,
                    idx.job_id, idx.downloaded_id,
                    idx.title AS library_title, idx.artist AS library_artist,
                    idx.category AS library_category, idx.detail_genre AS library_detail_genre,
                    idx.roles AS library_roles,
                    idx.preset AS library_preset, idx.requested_preset, idx.result AS library_result,
                    idx.bpm AS library_bpm, idx.musical_key, idx.camelot,
                    idx.energy AS library_energy, idx.energy_band, idx.vocals, idx.timing,
                    (SELECT COUNT(*) FROM jobs version
                     WHERE version.status = 'complete' AND version.source_path = jobs.source_path)
                     AS generation_count,
                    tracks.genre, tracks.genre_category, tracks.recording_code,
                    tracks.version_code, tracks.identity_confidence, tracks.identity_reason,
                    tracks.audio_quality_score, tracks.audio_quality_label,
                    tracks.audio_quality_json, tracks.audio_quality_analyzed_at,
                    (SELECT json_group_array(json_object(
                        'category', descriptors.category, 'value', descriptors.value,
                        'provenance', descriptors.provenance,
                        'confidence', descriptors.confidence,
                        'updated_at', descriptors.updated_at))
                     FROM downloaded_track_descriptors descriptors
                     WHERE descriptors.track_id=tracks.id) AS descriptors_json,
                    tracks.artwork_path, tracks.file_path AS downloaded_file_path
                    FROM library_search_index idx JOIN jobs ON jobs.id = idx.job_id
                    LEFT JOIN downloaded_tracks tracks ON tracks.id = idx.downloaded_id
                    {where} ORDER BY {order} LIMIT ? OFFSET ?""",
                (*parameters, page_size, (page - 1) * page_size),
            ).fetchall()
        return [dict(row) for row in rows], total

    def library_search_facets(self) -> dict[str, Any]:
        with closing(self._connect()) as connection:
            total = int(connection.execute("SELECT COUNT(*) FROM library_search_index").fetchone()[0])
            categories = dict(
                connection.execute("SELECT category, COUNT(*) FROM library_search_index GROUP BY category").fetchall()
            )
            detail_rows = connection.execute(
                "SELECT category, detail_genre, COUNT(*) FROM library_search_index "
                "WHERE detail_genre != '' GROUP BY category, detail_genre"
            ).fetchall()
            presets = [
                row[0]
                for row in connection.execute(
                    "SELECT DISTINCT preset FROM library_search_index ORDER BY preset"
                ).fetchall()
            ]
            keys = [
                row[0]
                for row in connection.execute(
                    "SELECT DISTINCT musical_key FROM library_search_index WHERE musical_key != '' ORDER BY musical_key"
                ).fetchall()
            ]
            role_rows = connection.execute("SELECT roles FROM library_search_index").fetchall()
            intelligence = connection.execute(
                """SELECT job_id, source_name, bpm, musical_key, roles, energy,
                    energy_band, vocals, timing FROM library_search_index"""
            ).fetchall()
        roles: dict[str, int] = {}
        for row in role_rows:
            for name in str(row[0] or "").strip("|").split("|"):
                if name:
                    roles[name] = roles.get(name, 0) + 1
        detailed_genres: dict[str, int] = {}
        detailed_by_category: dict[str, dict[str, int]] = {}
        canonical: dict[str, str] = {}
        for category, raw_genres, count in detail_rows:
            category_counts = detailed_by_category.setdefault(str(category), {})
            for raw_genre in str(raw_genres or "").split(","):
                genre = raw_genre.strip()
                if not genre:
                    continue
                display = canonical.setdefault(genre.casefold(), genre)
                detailed_genres[display] = detailed_genres.get(display, 0) + int(count)
                category_counts[display] = category_counts.get(display, 0) + int(count)
        return {
            "total": total,
            "categories": categories,
            "detailed_genres": detailed_genres,
            "detailed_genres_by_category": detailed_by_category,
            "presets": presets,
            "keys": keys,
            "roles": roles,
            "intelligence": [dict(row) for row in intelligence],
        }

    def get_library_analysis(self, job_id: int) -> dict[str, Any]:
        """Load one indexed analysis record for waveform timeline rendering."""
        with closing(self._connect()) as connection:
            row = connection.execute(
                "SELECT analysis_json FROM library_search_index WHERE job_id=?", (job_id,)
            ).fetchone()
        if row is None:
            return {}
        try:
            return json.loads(str(row["analysis_json"] or "{}"))
        except (TypeError, ValueError, json.JSONDecodeError):
            return {}

    def list_set_builder_tracks(self) -> list[dict[str, Any]]:
        """Return every latest analyzed track using the compact Library index."""
        with closing(self._connect()) as connection:
            rows = connection.execute(
                """SELECT idx.job_id, idx.downloaded_id, idx.source_name, idx.title, idx.artist,
                    idx.category, idx.detail_genre, idx.roles, idx.energy, idx.vocals, idx.timing,
                    idx.camelot, idx.set_analysis_json,
                    jobs.source_path, jobs.wav_path,
                    jobs.extended_path, jobs.config_json,
                    downloaded.file_path AS library_path,
                    (SELECT json_group_array(json_object(
                        'category', descriptors.category, 'value', descriptors.value,
                        'provenance', descriptors.provenance,
                        'confidence', descriptors.confidence,
                        'updated_at', descriptors.updated_at))
                     FROM downloaded_track_descriptors descriptors
                     WHERE descriptors.track_id=downloaded.id) AS descriptors_json
                    FROM library_search_index idx
                    JOIN jobs ON jobs.id = idx.job_id
                    LEFT JOIN downloaded_tracks downloaded ON downloaded.id = idx.downloaded_id
                    ORDER BY idx.source_name COLLATE NOCASE, idx.job_id"""
            ).fetchall()
        return [dict(row) for row in rows]

    def library_index_count(self) -> int:
        with closing(self._connect()) as connection:
            return int(connection.execute("SELECT COUNT(*) FROM library_search_index").fetchone()[0])
