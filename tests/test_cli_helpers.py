from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from audioextender.processing.track_processor import _parse_timestamp
from main import _discover_inputs, _format_duration, _output_path


class CliHelperTests(unittest.TestCase):
    def test_discovers_only_supported_audio_in_stable_order(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary)
            for name in ("b.wav", "a.MP3", "notes.txt"):
                (directory / name).touch()
            self.assertEqual(
                [path.name for path in _discover_inputs([], directory)],
                ["a.MP3", "b.wav"],
            )

    def test_explicit_unsupported_input_is_rejected(self) -> None:
        with self.assertRaisesRegex(ValueError, "Unsupported input format"):
            _discover_inputs([Path("song.m4a")], Path("unused"))

    def test_output_name_preserves_source_stem(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            output = _output_path(Path("My Song.flac"), Path(temporary))
            self.assertEqual(output.name, "My Song (Extended Edit).wav")
            self.assertEqual(output.parent.name, "extended")
            self.assertTrue((Path(temporary) / "wav").is_dir())

    def test_timestamp_parsing(self) -> None:
        self.assertEqual(_parse_timestamp("1:15.5"), 75.5)
        self.assertEqual(_parse_timestamp("75"), 75.0)
        with self.assertRaisesRegex(ValueError, "negative"):
            _parse_timestamp("-1")

    def test_duration_formatting(self) -> None:
        self.assertEqual(_format_duration(65), "01:05")
        self.assertEqual(_format_duration(3661), "1:01:01")


if __name__ == "__main__":
    unittest.main()
