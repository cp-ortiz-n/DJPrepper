import re
import unittest

from tests.support.paths import PROJECT_ROOT

ROOT = PROJECT_ROOT


class FrontendContractTests(unittest.TestCase):
    def test_shared_controls_have_accessible_responsive_architecture_contracts(self) -> None:
        entry = (ROOT / "frontend" / "styles.css").read_text()
        imports = re.findall(r"@import url\(['\"]\./styles/([^'\"]+)['\"]\);", entry)
        self.assertTrue(imports, "styles.css must remain the ordered public entry point")
        css = "\n".join((ROOT / "frontend" / "styles" / name).read_text() for name in imports)
        compact_css = re.sub(r"\s+", "", css)

        self.assertIn("--control-height", css)
        self.assertIn(":focus-visible", css)
        self.assertIn("prefers-reduced-motion:reduce", compact_css)
        self.assertIn("@media(max-width:720px)", compact_css)
        self.assertIn(".set-proposals{grid-template-columns:1fr;}", compact_css)


if __name__ == "__main__":
    unittest.main()
