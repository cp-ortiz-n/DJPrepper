from __future__ import annotations

import json
from contextlib import closing
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from audioextender.repositories.base import RepositoryMixinBase


def _now() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")


class SystemStateRepositoryMixin(RepositoryMixinBase):
    def get_system_state(self, key: str) -> str | None:
        with closing(self._connect()) as connection:
            row = connection.execute("SELECT value FROM system_state WHERE key=?", (key,)).fetchone()
        return str(row["value"]) if row else None

    def set_system_state(self, key: str, value: str) -> None:
        with self._lock, closing(self._connect()) as connection, connection:
            connection.execute(
                """INSERT INTO system_state (key,value,updated_at) VALUES (?,?,?)
                    ON CONFLICT(key) DO UPDATE SET value=excluded.value,
                    updated_at=excluded.updated_at""",
                (key, value, _now()),
            )

    def get_settings(self) -> dict[str, Any]:
        with closing(self._connect()) as connection:
            rows = connection.execute("SELECT key, value_json FROM web_settings").fetchall()
        settings: dict[str, Any] = {}
        for row in rows:
            try:
                settings[str(row["key"])] = json.loads(row["value_json"])
            except (TypeError, ValueError):
                continue
        return settings

    def replace_settings(self, values: dict[str, Any]) -> None:
        with self._lock, closing(self._connect()) as connection, connection:
            connection.execute("DELETE FROM web_settings")
            connection.executemany(
                "INSERT INTO web_settings (key, value_json, updated_at) VALUES (?, ?, ?)",
                [(key, json.dumps(value), _now()) for key, value in values.items()],
            )

    def relocate_library_paths(self, old_root: Path, new_root: Path) -> dict[str, int]:
        """Atomically rewrite managed library paths while preserving record IDs."""
        old_root = old_root.expanduser().resolve()
        new_root = new_root.expanduser().resolve()
        old_prefix = str(old_root) + "/"
        new_prefix = str(new_root) + "/"
        counts = {"tracks": 0, "artwork": 0, "jobs": 0, "job_paths": 0, "sources": 0}
        with self._lock, closing(self._connect()) as connection, connection:
            duplicate = connection.execute(
                """SELECT COUNT(*) FROM downloaded_tracks target
                    WHERE target.file_path LIKE ? AND EXISTS (
                        SELECT 1 FROM downloaded_tracks source
                        WHERE source.file_path LIKE ?
                        AND target.file_path = ? || SUBSTR(source.file_path, ?)
                        AND target.id != source.id)""",
                (new_prefix + "%", old_prefix + "%", new_prefix, len(old_prefix) + 1),
            ).fetchone()[0]
            if duplicate:
                raise ValueError("The destination is already represented by conflicting catalog records")
            cursor = connection.execute(
                "UPDATE downloaded_tracks SET file_path=? || SUBSTR(file_path, ?), updated_at=? WHERE file_path LIKE ?",
                (new_prefix, len(old_prefix) + 1, _now(), old_prefix + "%"),
            )
            counts["tracks"] = cursor.rowcount
            cursor = connection.execute(
                "UPDATE downloaded_tracks SET artwork_path=? || SUBSTR(artwork_path, ?), "
                "updated_at=? WHERE artwork_path LIKE ?",
                (new_prefix, len(old_prefix) + 1, _now(), old_prefix + "%"),
            )
            counts["artwork"] = cursor.rowcount
            cursor = connection.execute(
                "UPDATE jobs SET source_path=? || SUBSTR(source_path, ?), updated_at=? WHERE source_path LIKE ?",
                (new_prefix, len(old_prefix) + 1, _now(), old_prefix + "%"),
            )
            counts["jobs"] = cursor.rowcount
            for field in (
                "wav_path",
                "extended_path",
                "intro_preview_path",
                "outro_preview_path",
                "cue_sheet_path",
                "rekordbox_path",
            ):
                cursor = connection.execute(
                    f"UPDATE jobs SET {field}=? || SUBSTR({field}, ?), updated_at=? WHERE {field} LIKE ?",  # noqa: S608
                    (new_prefix, len(old_prefix) + 1, _now(), old_prefix + "%"),
                )
                counts["job_paths"] += cursor.rowcount
            cursor = connection.execute(
                "UPDATE catalog_source_index SET source_path=? || SUBSTR(source_path, ?) WHERE source_path LIKE ?",
                (new_prefix, len(old_prefix) + 1, old_prefix + "%"),
            )
            counts["sources"] = cursor.rowcount
            settings = {
                str(row["key"]): json.loads(row["value_json"])
                for row in connection.execute("SELECT key, value_json FROM web_settings")
            }
            settings["music_library_path"] = str(new_root)
            connection.execute(
                """INSERT INTO system_state (key,value,updated_at) VALUES (?,?,?)
                    ON CONFLICT(key) DO UPDATE SET value=excluded.value,
                    updated_at=excluded.updated_at""",
                ("music_library_path", str(new_root), _now()),
            )
            connection.execute("DELETE FROM web_settings")
            connection.executemany(
                "INSERT INTO web_settings (key, value_json, updated_at) VALUES (?, ?, ?)",
                [(key, json.dumps(value), _now()) for key, value in settings.items()],
            )
            connection.execute(
                """INSERT INTO system_state (key,value,updated_at) VALUES (?,?,?)
                    ON CONFLICT(key) DO UPDATE SET value=excluded.value,
                    updated_at=excluded.updated_at""",
                ("music_library_path", str(new_root), _now()),
            )
        return counts
