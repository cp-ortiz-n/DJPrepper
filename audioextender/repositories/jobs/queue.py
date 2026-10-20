from __future__ import annotations

import json
from contextlib import closing
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from audioextender.repositories.base import RepositoryMixinBase


def _now() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")


class JobQueueRepositoryMixin(RepositoryMixinBase):
    def create(
        self,
        source_name: str,
        source_path: Path,
        preset: str,
        intro_bars: int,
        outro_bars: int,
        use_stems: bool,
        config_overrides: dict[str, Any] | None = None,
        parent_job_id: int | None = None,
    ) -> int:
        now = _now()
        config_values = config_overrides or {}
        review_status = (
            "resolved"
            if config_values.get("manual_candidate_selection")
            else "pending"
            if config_values.get("review_candidates")
            else None
        )
        with self._lock, closing(self._connect()) as connection, connection:
            cursor = connection.execute(
                """
                    INSERT INTO jobs (
                        source_name, source_path, status, preset, intro_bars,
                        outro_bars, use_stems, config_json, parent_job_id,
                        review_status, created_at, updated_at
                    ) VALUES (?, ?, 'queued', ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                (
                    source_name,
                    str(source_path.resolve()),
                    preset,
                    intro_bars,
                    outro_bars,
                    int(use_stems),
                    json.dumps(config_values, sort_keys=True),
                    parent_job_id,
                    review_status,
                    now,
                    now,
                ),
            )
            if cursor.lastrowid is None:
                raise RuntimeError("SQLite did not return a job id")
            return cursor.lastrowid

    def update(self, job_id: int, **values: Any) -> None:
        allowed = {
            "status",
            "progress",
            "stage",
            "error",
            "extended_path",
            "wav_path",
            "intro_preview_path",
            "outro_preview_path",
            "bpm",
            "intro_quality",
            "outro_quality",
            "cue_sheet_path",
            "rekordbox_path",
            "candidates_json",
            "cues_json",
            "review_status",
        }
        selected = {key: value for key, value in values.items() if key in allowed}
        if not selected:
            return
        selected["updated_at"] = _now()
        assignments = ", ".join(f"{key} = ?" for key in selected)
        with self._lock, closing(self._connect()) as connection, connection:
            connection.execute(
                f"UPDATE jobs SET {assignments} WHERE id = ?",  # noqa: S608
                (*selected.values(), job_id),
            )

    def get(self, job_id: int) -> dict[str, Any] | None:
        with closing(self._connect()) as connection:
            row = connection.execute("SELECT * FROM jobs WHERE id = ?", (job_id,)).fetchone()
        return dict(row) if row else None

    def list_jobs(self, limit: int = 100) -> list[dict[str, Any]]:
        with closing(self._connect()) as connection:
            rows = connection.execute("SELECT * FROM jobs ORDER BY id DESC LIMIT ?", (limit,)).fetchall()
        return [dict(row) for row in rows]

    def list_storage_job_references(self) -> list[dict[str, Any]]:
        """Return only fields needed to classify managed cache and output files."""
        columns = (
            "source_path, wav_path, extended_path, intro_preview_path, "
            "outro_preview_path, cue_sheet_path, rekordbox_path, preset, "
            "intro_bars, outro_bars, use_stems, config_json"
        )
        with closing(self._connect()) as connection:
            rows = connection.execute(f"SELECT {columns} FROM jobs").fetchall()
        return [dict(row) for row in rows]

    def analytics_summary(self) -> dict[str, Any]:
        """Return dashboard aggregates without loading full job rows into Python."""
        with closing(self._connect()) as connection:
            job_counts = connection.execute(
                """SELECT COUNT(*) AS completed,
                    COALESCE(SUM(CASE WHEN use_stems = 1 THEN 1 ELSE 0 END), 0) AS stemmed
                    FROM jobs WHERE status = 'complete'"""
            ).fetchone()
            feedback_rows = connection.execute(
                """SELECT accepted, tags FROM candidate_feedback
                    UNION ALL SELECT accepted, tags FROM track_feedback"""
            ).fetchall()
        return {
            "completed": int(job_counts["completed"]),
            "stemmed": int(job_counts["stemmed"]),
            "feedback": [dict(row) for row in feedback_rows],
        }

    def list_job_summaries(self, limit: int = 100) -> list[dict[str, Any]]:
        """Return queue-card fields without the potentially large candidate and cue payloads."""
        columns = (
            "id, source_name, source_path, status, progress, stage, preset, intro_bars, "
            "outro_bars, use_stems, error, extended_path, wav_path, bpm, intro_quality, "
            "outro_quality, created_at, updated_at, intro_preview_path, outro_preview_path, "
            "config_json, cue_sheet_path, rekordbox_path, parent_job_id, review_status"
        )
        with closing(self._connect()) as connection:
            rows = connection.execute(
                f"SELECT {columns} FROM jobs ORDER BY id DESC LIMIT ?",  # noqa: S608
                (limit,),
            ).fetchall()
        return [dict(row) for row in rows]

    def list_jobs_page(
        self,
        *,
        page: int = 1,
        page_size: int = 50,
        statuses: tuple[str, ...] = (),
    ) -> tuple[list[dict[str, Any]], int]:
        """Return a bounded jobs page without materializing the full history."""
        where = ""
        parameters: tuple[Any, ...] = ()
        if statuses:
            placeholders = ",".join("?" for _ in statuses)
            where = f"WHERE status IN ({placeholders})"
            parameters = statuses
        with closing(self._connect()) as connection:
            total = int(
                connection.execute(
                    f"SELECT COUNT(*) FROM jobs {where}",  # noqa: S608
                    parameters,
                ).fetchone()[0]
            )
            rows = connection.execute(
                f"SELECT * FROM jobs {where} ORDER BY id DESC LIMIT ? OFFSET ?",  # noqa: S608
                (*parameters, page_size, (page - 1) * page_size),
            ).fetchall()
        return [dict(row) for row in rows], total

    def list_latest_completed_jobs(self) -> list[dict[str, Any]]:
        """Return one latest completed generation per source using SQLite grouping."""
        with closing(self._connect()) as connection:
            rows = connection.execute(
                """WITH latest AS (
                        SELECT source_path, MAX(id) AS job_id, COUNT(*) AS generation_count
                        FROM jobs WHERE status = 'complete' GROUP BY source_path
                    )
                    SELECT jobs.*, latest.generation_count
                    FROM latest JOIN jobs ON jobs.id = latest.job_id
                    ORDER BY jobs.updated_at DESC, jobs.id DESC"""
            ).fetchall()
        return [dict(row) for row in rows]

    def list_report_audio_jobs(self) -> list[dict[str, Any]]:
        """Return the newest completed audio references for every report track name.

        Report history outlives the bounded queue listing, so diagnostics must not
        depend on ``list_job_summaries`` to locate previews for older tracks.
        """
        with closing(self._connect()) as connection:
            rows = connection.execute(
                """WITH latest AS (
                        SELECT LOWER(source_name) AS source_key, MAX(id) AS job_id
                        FROM jobs WHERE status = 'complete' GROUP BY LOWER(source_name)
                    )
                    SELECT jobs.id, jobs.source_name, jobs.wav_path, jobs.extended_path,
                    (SELECT id FROM downloaded_tracks
                     WHERE file_path=jobs.source_path
                     ORDER BY id LIMIT 1) AS downloaded_track_id,
                    (SELECT detected_key FROM downloaded_tracks
                     WHERE file_path=jobs.source_path
                     ORDER BY id LIMIT 1) AS latest_detected_key,
                    (SELECT key_confidence FROM downloaded_tracks
                     WHERE file_path=jobs.source_path
                     ORDER BY id LIMIT 1) AS latest_key_confidence,
                    (SELECT key_analyzed_at FROM downloaded_tracks
                     WHERE file_path=jobs.source_path
                     ORDER BY id LIMIT 1) AS key_analyzed_at
                    FROM latest JOIN jobs ON jobs.id = latest.job_id
                    ORDER BY jobs.id DESC"""
            ).fetchall()
        return [dict(row) for row in rows]

    def list_completed_versions(self, source_path: str) -> list[dict[str, Any]]:
        """Load version history only when a Library card asks for it."""
        with closing(self._connect()) as connection:
            rows = connection.execute(
                """SELECT * FROM jobs WHERE status = 'complete' AND source_path = ?
                    ORDER BY id DESC""",
                (source_path,),
            ).fetchall()
        return [dict(row) for row in rows]

    def delete(self, job_id: int) -> bool:
        with self._lock, closing(self._connect()) as connection, connection:
            connection.execute("DELETE FROM candidate_feedback WHERE job_id = ?", (job_id,))
            cursor = connection.execute("DELETE FROM jobs WHERE id = ?", (job_id,))
        return cursor.rowcount > 0

    def recover_interrupted(self) -> None:
        with closing(self._connect()) as connection, connection:
            connection.execute(
                "UPDATE jobs SET status = 'failed', stage = 'Server stopped', "
                "error = 'Processing was interrupted when the web app stopped', "
                "updated_at = ? WHERE status = 'processing'",
                (_now(),),
            )

    def fail_stalled_jobs(self, minutes: int = 30) -> int:
        """Close processing records that have stopped reporting progress."""
        cutoff = (datetime.now(UTC) - timedelta(minutes=minutes)).isoformat(timespec="seconds")
        with self._lock, closing(self._connect()) as connection, connection:
            cursor = connection.execute(
                """UPDATE jobs SET status='failed', stage='Processing stalled',
                    error='No processing progress was reported for 30 minutes', updated_at=?
                    WHERE status='processing' AND updated_at < ?""",
                (_now(), cutoff),
            )
        return cursor.rowcount
