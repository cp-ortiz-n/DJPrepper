from __future__ import annotations

import unittest

from audioextender.set_builder.proposal_repairer import PlanProposalRepairer


def candidate(identifier: str, section: str, *, required: bool = False) -> dict:
    return {
        "id": identifier,
        "eligibleSectionIds": [section],
        "relevanceScore": 100 - int(identifier.rsplit(":", 1)[-1]),
        "required": required,
        "locked": False,
    }


class PlanProposalRepairerTests(unittest.TestCase):
    def test_preserves_unique_ai_choices_and_fills_missing_section_slots(self) -> None:
        candidates = [
            candidate("downloaded:1", "opening", required=True),
            candidate("downloaded:2", "opening"),
            candidate("downloaded:3", "dance"),
            candidate("downloaded:4", "dance"),
        ]
        proposal = {"summary": "test", "selections": [
            {"trackId": "downloaded:3", "sectionId": "dance", "reason": "AI", "evidence": "ai-suggested"},
            {"trackId": "downloaded:3", "sectionId": "dance", "reason": "duplicate", "evidence": "ai-suggested"},
            {"trackId": "invented:9", "sectionId": "opening", "reason": "invalid", "evidence": "ai-suggested"},
        ]}
        repaired, repairs = PlanProposalRepairer().repair(
            proposal, candidates, {"opening": 2, "dance": 2}
        )
        self.assertEqual(
            [(item["trackId"], item["sectionId"]) for item in repaired["selections"]],
            [
                ("downloaded:1", "opening"), ("downloaded:2", "opening"),
                ("downloaded:3", "dance"), ("downloaded:4", "dance"),
            ],
        )
        self.assertTrue(any(item["code"] == "filled-section-slot" for item in repairs))


if __name__ == "__main__":
    unittest.main()
