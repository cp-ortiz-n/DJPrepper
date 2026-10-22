"""Keep the rendered workflow atlas complete and accessible."""

from __future__ import annotations

import unittest
import xml.etree.ElementTree as ET
from collections.abc import Callable
from runpy import run_path
from typing import Any, cast

from tests.support.paths import PROJECT_ROOT

FLOW_ROOT = PROJECT_ROOT / "docs" / "flows"
DIAGRAM_ROOT = FLOW_ROOT / "diagrams"
FLOW_DIAGRAMS = {
    "README.md": "application-workflow-overview.svg",
    "startup-and-navigation.md": "startup-and-navigation.svg",
    "imports.md": "imports.svg",
    "track-processing.md": "track-processing.svg",
    "music-files-and-catalog.md": "music-files-and-catalog.svg",
    "dj-library.md": "dj-library.svg",
    "set-builder.md": "set-builder.svg",
    "review-feedback-and-reporting.md": "review-feedback-and-reporting.svg",
    "settings-and-operations.md": "settings-and-operations.svg",
    "data-and-persistence.md": "data-and-persistence.svg",
}


class WorkflowDiagramTests(unittest.TestCase):
    def test_every_flow_document_embeds_its_rendered_diagram(self) -> None:
        self.assertEqual(
            set(FLOW_DIAGRAMS),
            {path.name for path in FLOW_ROOT.glob("*.md")},
            "Add every workflow document to FLOW_DIAGRAMS so it receives a rendered visual.",
        )
        for document, diagram in FLOW_DIAGRAMS.items():
            markdown = (FLOW_ROOT / document).read_text(encoding="utf-8")
            self.assertIn(f"(diagrams/{diagram})", markdown, document)
            self.assertTrue((DIAGRAM_ROOT / diagram).is_file(), diagram)

    def test_diagrams_are_accessible_svg_documents(self) -> None:
        namespace = {"svg": "http://www.w3.org/2000/svg"}
        for diagram in FLOW_DIAGRAMS.values():
            root = ET.parse(DIAGRAM_ROOT / diagram).getroot()
            self.assertEqual("img", root.attrib.get("role"), diagram)
            self.assertEqual("title desc", root.attrib.get("aria-labelledby"), diagram)
            self.assertIsNotNone(root.find("svg:title", namespace), diagram)
            self.assertIsNotNone(root.find("svg:desc", namespace), diagram)
            self.assertGreaterEqual(len(root.findall(".//svg:rect", namespace)), 6, diagram)
            self.assertGreaterEqual(len(root.findall(".//svg:path", namespace)), 5, diagram)
            self.assertGreaterEqual(len(root.findall(".//svg:g[@class='step']", namespace)), 8, diagram)

    def test_rendered_diagrams_match_their_source_definitions(self) -> None:
        renderer = run_path(str(PROJECT_ROOT / "scripts" / "development" / "render_workflow_diagrams.py"))
        render = cast(Callable[[Any], str], renderer["render"])
        diagrams = cast(tuple[Any, ...], renderer["DIAGRAMS"])
        expected = {f"{diagram.slug}.svg": render(diagram) for diagram in diagrams}
        self.assertEqual(set(FLOW_DIAGRAMS.values()), set(expected))
        for diagram, content in expected.items():
            self.assertEqual(content, (DIAGRAM_ROOT / diagram).read_text(encoding="utf-8"), diagram)


if __name__ == "__main__":
    unittest.main()
