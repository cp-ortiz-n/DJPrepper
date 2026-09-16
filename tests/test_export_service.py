from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock

import numpy as np

from helpers.audio_loader import AudioData
from helpers.config import EditConfig
from helpers.cue_export import CuePoint
from helpers.exceptions import ExportError
from helpers.export_service import ExportRequest, ExportService
from helpers.interfaces import NullProgressReporter


class ExportServiceTests(unittest.TestCase):
    def setUp(self) -> None:
        self.audio = AudioData(np.zeros((100, 2), dtype=np.float32), 10)
        self.analysis = Mock(
            bpm=120.0,
            key_label="A minor",
            key_confidence=80.0,
            beat_grid_confidence=75.0,
            downbeat_continuity=90.0,
            groove_label="straight",
            timing_label="steady",
        )

    def request(self, directory: Path, config: EditConfig) -> ExportRequest:
        return ExportRequest(
            source=directory / "Song.mp3",
            output=directory / "Song (Extended Edit).wav",
            edited_audio=self.audio,
            original_audio=self.audio,
            wav_output=directory / "wav" / "Song.wav",
            analysis=self.analysis,
            intro=None,
            outro=None,
            config=config,
        )

    def test_normal_export_writes_wav_and_cue_sheet(self) -> None:
        writer = Mock()
        cue = CuePoint("Mix In", 4.0)
        cue_builder = Mock(return_value=(cue,))
        cue_writer = Mock()
        service = ExportService(writer, cue_builder, cue_writer)
        with tempfile.TemporaryDirectory() as temporary:
            request = self.request(
                Path(temporary), EditConfig(export_cues=True, preview_only=False)
            )
            result = service.export(request, NullProgressReporter())
        self.assertEqual(writer.call_count, 2)
        writer.assert_any_call(self.audio, request.wav_output, 24)
        writer.assert_any_call(self.audio, request.output, 24)
        cue_builder.assert_called_once()
        cue_writer.assert_called_once()
        self.assertTrue(result.full_exported)
        self.assertEqual(result.cue_points, (cue,))
        self.assertIsNotNone(result.cue_sheet)
        assert result.cue_sheet is not None
        self.assertEqual(result.cue_sheet.name, "Song (Extended Edit).json")

    def test_preview_only_does_not_write_full_wav_or_cues(self) -> None:
        writer = Mock()
        cue_builder = Mock()
        service = ExportService(writer, cue_builder, Mock())
        with tempfile.TemporaryDirectory() as temporary:
            result = service.export(
                self.request(
                    Path(temporary),
                    EditConfig(preview_only=True, export_cues=True),
                ),
                NullProgressReporter(),
            )
        writer.assert_not_called()
        cue_builder.assert_not_called()
        self.assertFalse(result.full_exported)
        self.assertIsNone(result.cue_sheet)

    def test_writer_failure_is_exposed_as_export_error(self) -> None:
        service = ExportService(audio_writer=Mock(side_effect=OSError("disk full")))
        with tempfile.TemporaryDirectory() as temporary:
            request = self.request(Path(temporary), EditConfig(export_cues=False))
            with self.assertRaisesRegex(ExportError, "disk full"):
                service.export(request, NullProgressReporter())

    def test_preview_directory_keeps_artifacts_out_of_output_root(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            directory = ExportService.preview_directory(
                root / "Song.mp3", root / "Song (Extended Edit).wav"
            )
            self.assertEqual(directory, root / "previews" / "Song")
            self.assertTrue(directory.is_dir())

    def test_disabled_side_removes_stale_generated_previews(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            directory = ExportService.preview_directory(
                root / "Song.mp3", root / "Song (Extended Edit).wav"
            )
            stale = [
                directory / "Intro Preview.wav",
                directory / "Intro Candidate 1.wav",
                directory / "Outro Preview.wav",
            ]
            for path in stale:
                path.touch()
            service = ExportService(audio_writer=Mock())
            service.export(
                self.request(root, EditConfig(create_previews=True)),
                NullProgressReporter(),
            )
            self.assertTrue(all(not path.exists() for path in stale))


if __name__ == "__main__":
    unittest.main()
