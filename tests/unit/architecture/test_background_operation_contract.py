from __future__ import annotations

import json
import unittest

from tests.support.paths import PROJECT_ROOT

ROOT = PROJECT_ROOT
CONTRACT = json.loads((ROOT / "docs" / "background-operation-lifecycles.json").read_text(encoding="utf-8"))
EXPECTED_OPERATIONS = {
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
}


class BackgroundOperationContractTests(unittest.TestCase):
    def test_contract_covers_every_audited_operation_family(self) -> None:
        operations = CONTRACT["operations"]
        self.assertEqual(CONTRACT["schema_version"], 2)
        self.assertEqual({item["id"] for item in operations}, EXPECTED_OPERATIONS)
        self.assertEqual(len(operations), len(EXPECTED_OPERATIONS))

    def test_machine_contract_names_the_canonical_internal_projection(self) -> None:
        canonical = CONTRACT["canonical_contract"]
        self.assertEqual(
            canonical["implementation"],
            "audioextender/infrastructure/operation_lifecycle.py",
        )
        self.assertEqual(
            set(canonical["active_states"]),
            {"queued", "pending", "planned", "processing", "canceling"},
        )
        self.assertEqual(
            set(canonical["terminal_states"]),
            {"complete", "failed", "canceled", "rolled_back"},
        )
        self.assertIn("capabilities", canonical["fields"])
        self.assertEqual(set(canonical["actions"]), {"cancel", "retry", "pause", "rollback"})

    def test_every_operation_has_a_complete_lifecycle_description(self) -> None:
        required = {
            "id",
            "owner",
            "routes",
            "states",
            "persistence",
            "restart",
            "cancellation",
            "retry",
            "timestamps",
            "errors",
            "receipt",
            "result",
        }
        for operation in CONTRACT["operations"]:
            with self.subTest(operation=operation["id"]):
                self.assertEqual(set(operation), required)
                self.assertTrue((ROOT / operation["owner"]).is_file())
                self.assertTrue(operation["routes"])
                self.assertTrue(operation["states"])
                self.assertIn(operation["persistence"], {"memory", "json", "sqlite"})
                for field in ("restart", "cancellation", "retry", "errors", "receipt", "result"):
                    self.assertTrue(operation[field].strip())

    def test_active_and_terminal_state_vocabulary_is_explicit(self) -> None:
        active = {"queued", "pending", "planned", "processing", "canceling"}
        terminal = {"complete", "failed", "canceled", "rolled_back"}
        for operation in CONTRACT["operations"]:
            states = set(operation["states"])
            with self.subTest(operation=operation["id"]):
                self.assertTrue(states & active)
                self.assertTrue(states & terminal)
                self.assertFalse(states - active - terminal)


if __name__ == "__main__":
    unittest.main()
