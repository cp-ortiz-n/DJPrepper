from __future__ import annotations

import unittest

from audioextender.set_builder.saved_sets import SAVED_SET_STORAGE_KEY, SavedSetService


class MemoryStateRepository:
    def __init__(self) -> None:
        self.values: dict[str, str] = {}

    def get_system_state(self, key: str) -> str | None:
        return self.values.get(key)

    def set_system_state(self, key: str, value: str) -> None:
        self.values[key] = value


def record(set_id: str = "set-1", name: str = "Friday") -> dict:
    return {
        "id": set_id,
        "name": name,
        "tracks": ["track-1", "track-2"],
        "draftId": "draft-1",
        "planRevision": {"id": "revision-1", "number": 1, "parentId": None},
        "planningReceipt": {"provider": "ollama", "validated": True},
        "transitions": {"1": {"bars": 16}},
        "locked": ["track-1"],
    }


class SavedSetServiceTests(unittest.TestCase):
    def test_saved_set_survives_service_restart_with_complete_editable_state(self) -> None:
        repository = MemoryStateRepository()
        result = SavedSetService(repository).upsert(record())

        restored = SavedSetService(repository).list_sets()

        self.assertTrue(result["survives_restart"])
        self.assertEqual(restored["version"], 2)
        self.assertEqual(restored["sets"][0]["planningReceipt"]["provider"], "ollama")
        self.assertEqual(restored["sets"][0]["draftId"], "draft-1")
        self.assertEqual(restored["sets"][0]["planRevision"]["id"], "revision-1")
        self.assertEqual(restored["sets"][0]["transitions"]["1"]["bars"], 16)
        self.assertIn(SAVED_SET_STORAGE_KEY, repository.values)

    def test_version_one_migration_preserves_server_records_and_is_idempotent(self) -> None:
        repository = MemoryStateRepository()
        service = SavedSetService(repository)
        service.upsert(record("server", "Server"))

        first = service.migrate_v1([record("legacy", "Legacy"), record("server", "Old server copy")])
        second = service.migrate_v1([record("legacy", "Legacy")])

        self.assertEqual(first["migrated"], 1)
        self.assertEqual(first["skipped"], 1)
        self.assertEqual(second["migrated"], 0)
        records = {item["id"]: item for item in service.list_sets()["sets"]}
        self.assertEqual(records["server"]["name"], "Server")
        self.assertEqual(records["legacy"]["schemaVersion"], 2)

    def test_delete_and_validation_are_explicit(self) -> None:
        service = SavedSetService(MemoryStateRepository())
        with self.assertRaisesRegex(ValueError, "requires a name"):
            service.upsert({"id": "broken", "name": "", "tracks": []})
        service.upsert(record())
        self.assertTrue(service.delete("set-1")["deleted"])
        self.assertFalse(service.delete("set-1")["deleted"])

    def test_saved_set_normalization_keeps_one_preferred_version_per_recording_family(self) -> None:
        repository = MemoryStateRepository()
        payload = record()
        payload["tracks"] = ["original", "bridge", "remix"]
        payload["locked"] = ["remix"]
        payload["required"] = ["original"]
        payload["trackDetails"] = [
            {"id": "original", "recordingKey": "recording:DSC-1"},
            {"id": "bridge", "recordingKey": "recording:DSC-2"},
            {"id": "remix", "recordingKey": "recording:DSC-1"},
        ]

        saved = SavedSetService(repository).upsert(payload)["set"]

        self.assertEqual(saved["tracks"], ["bridge", "remix"])
        self.assertEqual(saved["locked"], ["remix"])
        self.assertEqual(saved["required"], [])
        self.assertEqual([detail["id"] for detail in saved["trackDetails"]], ["bridge", "remix"])

    def test_legacy_saved_set_without_family_metadata_only_collapses_exact_track_ids(self) -> None:
        payload = record()
        payload["tracks"] = ["same", "same", "different"]
        payload.pop("trackDetails", None)

        saved = SavedSetService(MemoryStateRepository()).upsert(payload)["set"]

        self.assertEqual(saved["tracks"], ["same", "different"])


if __name__ == "__main__":
    unittest.main()
