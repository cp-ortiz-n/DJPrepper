import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


class FrontendContractTests(unittest.TestCase):
    def test_set_builder_exposes_three_distinct_directions(self):
        app = (ROOT / "web" / "app.js").read_text()
        set_builder = (ROOT / "web" / "set-builder.js").read_text()
        page = (ROOT / "web" / "index.html").read_text()

        self.assertIn("Safe Flow", set_builder)
        self.assertIn("Energy Journey", set_builder)
        self.assertIn("Adventurous Mix", set_builder)
        self.assertIn('role="radiogroup"', page)
        self.assertIn("createSetBuilderFeature", app)
        self.assertIn("selectSetProposal", set_builder)
        self.assertIn("snapshot=setPlanSnapshot", set_builder.replace(" ", ""))

    def test_shared_controls_have_accessible_responsive_contracts(self):
        css = (ROOT / "web" / "styles.css").read_text()

        self.assertIn("--control-height", css)
        self.assertIn(":focus-visible", css)
        self.assertIn("prefers-reduced-motion:reduce", css)
        self.assertIn("@media (max-width:720px)", css)
        self.assertIn(".set-proposals { grid-template-columns:1fr; }", css)

    def test_set_builder_exposes_conservative_preference_learning_controls(self):
        set_builder = (ROOT / "web" / "set-builder.js").read_text()
        page = (ROOT / "web" / "index.html").read_text()

        self.assertIn('id="set-personalization-enabled"', page)
        self.assertIn('id="reset-set-preferences"', page)
        for action in ("lock", "remove", "replace-out", "replace-in", "save", "export"):
            self.assertIn(f"recordPreference('{action}'", set_builder)
        self.assertIn("preferenceAdjustment(track)", set_builder)
        self.assertIn('id="set-review-panel"', page)
        self.assertIn('id="submit-set-review"', page)
        self.assertIn("submitSetReview", set_builder)
        self.assertIn("transitionPreferenceAdjustment", set_builder)


if __name__ == "__main__":
    unittest.main()
