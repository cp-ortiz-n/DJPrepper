import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


class FrontendContractTests(unittest.TestCase):
    def test_shared_controls_have_accessible_responsive_architecture_contracts(self) -> None:
        css = (ROOT / "web" / "styles.css").read_text()

        self.assertIn("--control-height", css)
        self.assertIn(":focus-visible", css)
        self.assertIn("prefers-reduced-motion:reduce", css)
        self.assertIn("@media (max-width:720px)", css)
        self.assertIn(".set-proposals { grid-template-columns:1fr; }", css)


if __name__ == "__main__":
    unittest.main()
