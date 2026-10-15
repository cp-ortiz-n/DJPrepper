"""Durable ownership for editable Set Builder records."""

from __future__ import annotations

import copy
import json
import threading
from collections.abc import Mapping, Sequence
from typing import Any, Protocol

SAVED_SET_STORAGE_KEY = "set_builder_saved_sets_v2"
SAVED_SET_SCHEMA_VERSION = 2


class SavedSetStateRepository(Protocol):
    def get_system_state(self, key: str) -> str | None: ...

    def set_system_state(self, key: str, value: str) -> None: ...


class SavedSetService:
    """Store complete editable set aggregates in the application database."""

    def __init__(self, repository: SavedSetStateRepository) -> None:
        self._repository = repository
        self._lock = threading.RLock()

    def list_sets(self) -> dict[str, Any]:
        with self._lock:
            return self._load()

    def upsert(self, raw_record: Mapping[str, Any]) -> dict[str, Any]:
        record = self._normalize(raw_record)
        with self._lock:
            document = self._load()
            sets = [item for item in document["sets"] if item["id"] != record["id"]]
            sets.insert(0, record)
            self._save(sets)
        return {"saved": True, "set": copy.deepcopy(record), "survives_restart": True}

    def delete(self, set_id: str) -> dict[str, Any]:
        with self._lock:
            document = self._load()
            retained = [item for item in document["sets"] if item["id"] != set_id]
            deleted = len(retained) != len(document["sets"])
            if deleted:
                self._save(retained)
        return {"deleted": deleted, "id": set_id, "survives_restart": True}

    def migrate_v1(self, records: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
        """Import browser version-1 records without replacing newer server data."""
        normalized = [self._normalize(record) for record in records]
        with self._lock:
            document = self._load()
            existing = {item["id"] for item in document["sets"]}
            additions = [record for record in normalized if record["id"] not in existing]
            if additions:
                self._save([*additions, *document["sets"]])
        return {
            "migrated": len(additions),
            "skipped": len(normalized) - len(additions),
            "document": self._load(),
            "survives_restart": True,
        }

    def _load(self) -> dict[str, Any]:
        raw = self._repository.get_system_state(SAVED_SET_STORAGE_KEY)
        if not raw:
            return {"version": SAVED_SET_SCHEMA_VERSION, "sets": []}
        try:
            payload = json.loads(raw)
        except (TypeError, ValueError):
            return {"version": SAVED_SET_SCHEMA_VERSION, "sets": []}
        records = payload.get("sets", []) if isinstance(payload, dict) else []
        valid: list[dict[str, Any]] = []
        for record in records:
            try:
                valid.append(self._normalize(record))
            except ValueError:
                continue
        return {"version": SAVED_SET_SCHEMA_VERSION, "sets": valid}

    def _save(self, records: list[dict[str, Any]]) -> None:
        payload = {"version": SAVED_SET_SCHEMA_VERSION, "sets": records}
        self._repository.set_system_state(SAVED_SET_STORAGE_KEY, json.dumps(payload, separators=(",", ":")))

    @staticmethod
    def _normalize(raw_record: Mapping[str, Any]) -> dict[str, Any]:
        try:
            record = copy.deepcopy(dict(raw_record))
        except (TypeError, ValueError) as error:
            raise ValueError("Saved set must be an object") from error
        set_id = str(record.get("id", "")).strip()
        name = str(record.get("name", "")).strip()
        tracks = record.get("tracks")
        if not set_id or len(set_id) > 200:
            raise ValueError("Saved set requires a stable id")
        if not name or len(name) > 150:
            raise ValueError("Saved set requires a name")
        if not isinstance(tracks, list) or len(tracks) > 5000:
            raise ValueError("Saved set tracks must be a list")
        record["id"] = set_id
        record["name"] = name
        record["tracks"] = [str(track) for track in tracks]
        record["schemaVersion"] = SAVED_SET_SCHEMA_VERSION
        try:
            json.dumps(record)
        except (TypeError, ValueError) as error:
            raise ValueError("Saved set contains unsupported values") from error
        return record
