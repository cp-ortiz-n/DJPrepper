from __future__ import annotations

import json
from contextlib import closing
from datetime import datetime, timezone
from typing import Any

from audioextender.repositories.base import RepositoryMixinBase


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


class FeedbackRepositoryMixin(RepositoryMixinBase):
    def add_feedback(
        self,
        job_id: int,
        position: str,
        candidate_rank: int | None,
        accepted: bool,
        tags: str,
        notes: str,
    ) -> int:
        with self._lock, closing(self._connect()) as connection, connection:
            if accepted:
                connection.execute(
                    "DELETE FROM candidate_feedback WHERE job_id = ? AND position = ?",
                    (job_id, position),
                )
            else:
                connection.execute(
                    """DELETE FROM candidate_feedback
                        WHERE job_id = ? AND position = ? AND candidate_rank IS ?""",
                    (job_id, position, candidate_rank),
                )
            cursor = connection.execute(
                """INSERT INTO candidate_feedback
                    (job_id, position, candidate_rank, accepted, tags, notes, created_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?)""",
                (job_id, position, candidate_rank, int(accepted), tags, notes, _now()),
            )
            return int(cursor.lastrowid or 0)

    def feedback(self, job_id: int | None = None) -> list[dict[str, Any]]:
        query = "SELECT * FROM candidate_feedback"
        parameters: tuple[Any, ...] = ()
        if job_id is not None:
            query += " WHERE job_id = ?"
            parameters = (job_id,)
        query += " ORDER BY id DESC"
        with closing(self._connect()) as connection:
            rows = connection.execute(query, parameters).fetchall()
        return [dict(row) for row in rows]

    def add_track_feedback(
        self,
        source_name: str,
        position: str,
        accepted: bool,
        tags: str,
        notes: str,
    ) -> int:
        """Store feedback against a processed track, including CLI-only tracks."""
        with self._lock, closing(self._connect()) as connection, connection:
            cursor = connection.execute(
                """INSERT INTO track_feedback
                    (source_name, position, accepted, tags, notes, created_at)
                    VALUES (?, ?, ?, ?, ?, ?)""",
                (source_name, position, int(accepted), tags, notes, _now()),
            )
            return int(cursor.lastrowid or 0)

    def track_feedback(self, source_name: str | None = None) -> list[dict[str, Any]]:
        query = "SELECT * FROM track_feedback"
        parameters: tuple[Any, ...] = ()
        if source_name is not None:
            query += " WHERE source_name = ? COLLATE NOCASE"
            parameters = (source_name,)
        query += " ORDER BY id DESC"
        with closing(self._connect()) as connection:
            rows = connection.execute(query, parameters).fetchall()
        return [dict(row) for row in rows]

    def set_key_verification(
        self,
        source_name: str,
        verified_key: str,
        detected_key: str,
        candidates: list[dict[str, Any]],
        notes: str = "",
    ) -> dict[str, Any]:
        """Persist a user-confirmed key independently from generated analysis."""
        now = _now()
        with self._lock, closing(self._connect()) as connection, connection:
            connection.execute(
                """INSERT INTO key_verifications
                    (source_name, verified_key, detected_key, candidates_json, notes,
                     created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(source_name) DO UPDATE SET
                    verified_key=excluded.verified_key,
                    detected_key=excluded.detected_key,
                    candidates_json=excluded.candidates_json,
                    notes=excluded.notes,
                    updated_at=excluded.updated_at""",
                (
                    source_name,
                    verified_key,
                    detected_key,
                    json.dumps(candidates, separators=(",", ":")),
                    notes,
                    now,
                    now,
                ),
            )
        return self.key_verification(source_name) or {}

    def key_verification(self, source_name: str) -> dict[str, Any] | None:
        with closing(self._connect()) as connection:
            row = connection.execute(
                "SELECT * FROM key_verifications WHERE source_name=? COLLATE NOCASE",
                (source_name,),
            ).fetchone()
        if row is None:
            return None
        item = dict(row)
        try:
            item["candidates"] = json.loads(item.pop("candidates_json") or "[]")
        except (TypeError, ValueError, json.JSONDecodeError):
            item["candidates"] = []
        return item

    def key_verifications(self) -> list[dict[str, Any]]:
        with closing(self._connect()) as connection:
            rows = connection.execute("SELECT * FROM key_verifications ORDER BY updated_at DESC").fetchall()
        results = []
        for row in rows:
            item = dict(row)
            try:
                item["candidates"] = json.loads(item.pop("candidates_json") or "[]")
            except (TypeError, ValueError, json.JSONDecodeError):
                item["candidates"] = []
            results.append(item)
        return results

    def delete_key_verification(self, source_name: str) -> bool:
        with self._lock, closing(self._connect()) as connection, connection:
            cursor = connection.execute(
                "DELETE FROM key_verifications WHERE source_name=? COLLATE NOCASE",
                (source_name,),
            )
        return cursor.rowcount > 0
