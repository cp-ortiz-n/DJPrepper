from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from helpers.presets import EditPreset
from helpers.web_configuration import PresetStore, WebConfigurationService, web_defaults
from helpers.web_database import JobRepository


class WebConfigurationTests(unittest.TestCase):
    def test_effective_precedence_is_defaults_then_system_path_then_overrides(self):
        with TemporaryDirectory() as temporary:
            root = Path(temporary)
            repository = JobRepository(root / "catalog.sqlite3").settings_system
            defaults = web_defaults(str(root / "Default"))
            presets = PresetStore(root / "presets.json", {})
            service = WebConfigurationService(repository, defaults, presets)

            repository.set_system_state("music_library_path", str(root / "External"))
            repository.replace_settings({"intro_bars": 16})
            effective = service.effective()

            self.assertEqual(effective["music_library_path"], str(root / "External"))
            self.assertEqual(effective["intro_bars"], 16)
            self.assertEqual(effective["outro_bars"], defaults["outro_bars"])

    def test_persist_stores_only_values_different_from_defaults(self):
        with TemporaryDirectory() as temporary:
            root = Path(temporary)
            repository = JobRepository(root / "catalog.sqlite3").settings_system
            defaults = web_defaults(str(root / "Library"))
            presets = PresetStore(root / "presets.json", {})
            service = WebConfigurationService(repository, defaults, presets)
            values = {**defaults, "intro_bars": 16}

            overrides = service.persist(values)

            self.assertEqual(overrides, {"intro_bars": 16})
            self.assertEqual(repository.get_settings(), {"intro_bars": 16})

    def test_preset_store_layers_custom_definitions_and_hidden_builtins(self):
        with TemporaryDirectory() as temporary:
            path = Path(temporary) / "presets.json"
            built_in = EditPreset(8, 8, False, 60, 2)
            store = PresetStore(path, {"club": built_in})
            store.save({
                "definitions": {"custom": {
                    "intro_bars": 16, "outro_bars": 16, "use_stems": False,
                    "minimum_loop_quality": 70, "maximum_repetitions": 2,
                }},
                "hidden": ["club"],
            })

            self.assertEqual(set(store.available()), {"custom"})
            self.assertEqual(store.snapshot("custom")["preset_definition"]["intro_bars"], 16)


if __name__ == "__main__":
    unittest.main()
