from __future__ import annotations

import unittest
from dataclasses import FrozenInstanceError

from audioextender.infrastructure.operation_lifecycle import (
    AUDIO_JOBS,
    AUTHORIZED_IMPORTS,
    CREATIVE_COMMONS_IMPORTS,
    LIBRARY_RELOCATION,
    LIFECYCLE_FAMILIES,
    METADATA_BATCHES,
    SET_PLANNING,
    LifecyclePersistence,
    LifecycleStatus,
)


class OperationLifecycleContractTests(unittest.TestCase):
    def test_every_audited_family_has_a_canonical_adapter(self) -> None:
        self.assertEqual(
            set(LIFECYCLE_FAMILIES),
            {
                "audio-jobs",
                "authorized-import",
                "local-audio-import",
                "playlist-match",
                "creative-commons-import",
                "metadata-batches",
                "integrity-scan",
                "audio-quality-scan",
                "set-planning",
                "library-relocation",
            },
        )

    def test_core_operation_families_conform_to_the_same_projection(self) -> None:
        samples: dict[str, dict[str, object]] = {
            "audio-jobs": {"id": 42, "status": "queued", "stage": "Waiting"},
            "authorized-import": {"id": "import", "status": "processing", "stage": "Downloading"},
            "local-audio-import": {"id": "local", "status": "complete", "stage": "Imported"},
            "playlist-match": {"id": "match", "status": "failed", "error": "No match"},
            "creative-commons-import": {"id": "cc", "status": "failed", "retryable": True},
            "metadata-batches": {"batch_id": "metadata", "status": "canceling"},
            "integrity-scan": {"batch_id": "integrity", "status": "complete"},
            "audio-quality-scan": {"batch_id": "quality", "status": "processing"},
            "set-planning": {"jobId": "plan", "status": "canceled", "retryable": True},
            "library-relocation": {"id": "move", "status": "rolled_back"},
        }

        for family_name, state in samples.items():
            with self.subTest(family=family_name):
                projection = LIFECYCLE_FAMILIES[family_name].project(state)
                self.assertEqual(projection.family, family_name)
                self.assertTrue(projection.operation_id)
                self.assertIsInstance(projection.status, LifecycleStatus)
                self.assertEqual(projection.persistence, LIFECYCLE_FAMILIES[family_name].persistence)

    def test_snake_case_batch_projects_without_changing_source_payload(self) -> None:
        state = {
            "batch_id": "batch-1",
            "status": "failed",
            "stage": "Failed",
            "progress": 50,
            "retryable": True,
            "retry_of": "batch-0",
            "created_at": "created",
            "updated_at": "updated",
            "errors": [{"id": 7, "error": "write failed", "code": "io"}],
            "receipt": {"status": "failed"},
            "result": {"updated": 2},
        }

        projected = METADATA_BATCHES.project(state)

        self.assertEqual(projected.operation_id, "batch-1")
        self.assertEqual(projected.status, LifecycleStatus.FAILED)
        self.assertTrue(projected.terminal)
        self.assertEqual(projected.retry_of, "batch-0")
        self.assertEqual(projected.errors[0].item_id, 7)
        self.assertEqual(projected.errors[0].code, "io")
        self.assertEqual(projected.receipt, {"status": "failed"})
        self.assertEqual(state["batch_id"], "batch-1")

    def test_camel_case_planning_job_uses_the_same_contract(self) -> None:
        projected = SET_PLANNING.project(
            {
                "jobId": "plan-1",
                "status": "canceling",
                "stage": "Canceling safely",
                "progress": 35,
                "retryable": False,
                "retryOf": "plan-0",
                "createdAt": "created",
                "updatedAt": "updated",
                "result": None,
            }
        )

        self.assertEqual(projected.operation_id, "plan-1")
        self.assertEqual(projected.status, LifecycleStatus.CANCELING)
        self.assertFalse(projected.terminal)
        self.assertEqual(projected.retry_of, "plan-0")
        self.assertEqual(projected.updated_at, "updated")

    def test_family_capabilities_preserve_feature_specific_behavior(self) -> None:
        self.assertTrue(AUDIO_JOBS.capabilities.pause)
        self.assertTrue(AUTHORIZED_IMPORTS.capabilities.cancel)
        self.assertFalse(AUTHORIZED_IMPORTS.capabilities.retry)
        self.assertTrue(CREATIVE_COMMONS_IMPORTS.capabilities.retry)
        self.assertTrue(LIBRARY_RELOCATION.capabilities.rollback)
        self.assertEqual(AUDIO_JOBS.persistence, LifecyclePersistence.SQLITE)

    def test_action_receipts_link_retries_without_mutating_legacy_states(self) -> None:
        original = {"batch_id": "old", "status": "failed", "retryable": True}
        retry = {"batch_id": "new", "status": "processing", "retry_of": "old"}

        receipt = METADATA_BATCHES.action_receipt("retry", original, linked_state=retry)

        self.assertTrue(receipt.accepted)
        self.assertEqual(receipt.operation_id, "old")
        self.assertEqual(receipt.linked_operation_id, "new")
        self.assertEqual(receipt.status, LifecycleStatus.FAILED)

    def test_projection_is_immutable(self) -> None:
        projection = LIBRARY_RELOCATION.project({"id": "move", "status": "planned"})
        with self.assertRaises(FrozenInstanceError):
            projection.stage = "changed"  # type: ignore[misc]

    def test_invalid_status_is_rejected_instead_of_silently_normalized(self) -> None:
        with self.assertRaises(ValueError):
            SET_PLANNING.project({"jobId": "plan", "status": "mystery"})


if __name__ == "__main__":
    unittest.main()
