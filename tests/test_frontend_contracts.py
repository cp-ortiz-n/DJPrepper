import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


class FrontendContractTests(unittest.TestCase):
    def test_set_builder_exposes_three_distinct_directions(self):
        app = (ROOT / "web" / "app.js").read_text()
        page = (ROOT / "web" / "index.html").read_text()

        self.assertIn("Safe Flow", app)
        self.assertIn("Energy Journey", app)
        self.assertIn("Adventurous Mix", app)
        self.assertIn('role="radiogroup"', page)
        self.assertIn("selectSetProposal", app)
        self.assertIn("snapshot=setPlanSnapshot", app.replace(" ", ""))

    def test_shared_controls_have_accessible_responsive_contracts(self):
        css = (ROOT / "web" / "styles.css").read_text()

        self.assertIn("--control-height", css)
        self.assertIn(":focus-visible", css)
        self.assertIn("prefers-reduced-motion:reduce", css)
        self.assertIn("@media (max-width:720px)", css)
        self.assertIn(".set-proposals { grid-template-columns:1fr; }", css)

    def test_quick_view_keeps_optional_tools_hidden_and_genre_editable(self):
        app = (ROOT / "web" / "app.js").read_text()

        self.assertIn('class="inspector-family" hidden', app)
        self.assertIn("inspector-manage-family", app)
        self.assertIn("inspector-family-close", app)
        self.assertIn("inspector-genre-trigger", app)
        self.assertIn("genreEditorMarkup(track.genre_category", app)
        self.assertIn("bindGenreEditor(inspectorGenreEditor", app)

    def test_settings_save_reports_validation_and_library_verification(self):
        app = (ROOT / "web" / "app.js").read_text()
        ui = (ROOT / "web" / "modules" / "ui.js").read_text()

        self.assertIn("function apiErrorMessage", ui)
        self.assertIn("field ? `${field}: `", ui)
        self.assertIn("Music library connected", app)
        self.assertIn("Library location verified", app)
        self.assertIn("status.available_tracks", app)
        self.assertIn("status.cataloged_tracks", app)

    def test_metadata_editor_uses_genre_language(self):
        app = (ROOT / "web" / "modules" / "genre-controls.js").read_text()

        self.assertIn('<label>Genre<select name="genre_category">', app)
        self.assertNotIn('<label>Category<select name="genre_category">', app)

    def test_frontend_uses_shared_feature_modules(self):
        app = (ROOT / "web" / "app.js").read_text()

        self.assertIn("from './modules/ui.js'", app)
        self.assertIn("from './modules/genre-controls.js'", app)
        self.assertIn("from './modules/audio-player.js'", app)
        self.assertIn("from './modules/background-tasks.js'", app)
        self.assertNotIn("function apiErrorMessage", app)
        self.assertNotIn("const compactAudioEngine", app)
        self.assertNotIn("const backgroundTasks", app)


if __name__ == "__main__":
    unittest.main()
