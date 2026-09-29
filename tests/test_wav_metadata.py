from __future__ import annotations

import json
import subprocess
import tempfile
import unittest
import wave
import xml.etree.ElementTree as ET
from pathlib import Path
from types import SimpleNamespace

from helpers.cue_export import write_rekordbox_xml
from helpers.wav_metadata import (
    embed_wav_artwork,
    read_wav_artwork,
    split_artist_title,
    sync_wav_metadata,
    write_wav_metadata,
)


class WavMetadataTests(unittest.TestCase):
    def test_embedded_artwork_survives_metadata_retagging(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "Artwork.wav"
            with wave.open(str(path), "wb") as output:
                output.setnchannels(1)
                output.setsampwidth(2)
                output.setframerate(8000)
                output.writeframes(b"\0\0" * 800)
            image = b"\xff\xd8\xff\xe0test-cover\xff\xd9"
            embed_wav_artwork(path, image, "image/jpeg")
            self.assertEqual(read_wav_artwork(path), {"mime": "image/jpeg", "size": len(image)})
            write_wav_metadata(path, title="Track", artist="Artist", genre="House")
            self.assertEqual(read_wav_artwork(path), {"mime": "image/jpeg", "size": len(image)})

    def test_wav_tags_are_embedded_without_reencoding(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "Artist - Track.wav"
            with wave.open(str(path), "wb") as output:
                output.setnchannels(1)
                output.setsampwidth(2)
                output.setframerate(8000)
                output.writeframes(b"\0\0" * 800)

            write_wav_metadata(
                path, title="Track", artist="Artist", genre="House", album="Night Set"
            )
            probe = subprocess.run(
                [
                    "ffprobe", "-v", "error", "-show_entries", "format_tags",
                    "-of", "json", str(path),
                ],
                check=True,
                capture_output=True,
                text=True,
            )
            tags = json.loads(probe.stdout)["format"]["tags"]
            normalized = {key.casefold(): value for key, value in tags.items()}
            self.assertEqual(normalized["title"], "Track")
            self.assertEqual(normalized["artist"], "Artist")
            self.assertEqual(normalized["genre"], "House")
            self.assertEqual(normalized["album"], "Night Set")
            self.assertFalse(sync_wav_metadata(
                path, title="Track", artist="Artist", genre="House", album="Night Set"
            ))
            self.assertTrue(sync_wav_metadata(
                path, title="Track", artist="Artist", genre="Techno", album="Night Set"
            ))

    def test_rekordbox_xml_contains_catalog_identity(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            audio = root / "Track.wav"
            audio.write_bytes(b"RIFF")
            result = SimpleNamespace(
                full_exported=True,
                output=audio,
                output_duration=180.0,
                bpm=124.0,
                key_label="A minor",
                cue_points=(),
                title="Track",
                artist="Artist",
                genre="House",
                album="Night Set",
            )
            xml_path = root / "rekordbox.xml"
            write_rekordbox_xml([result], xml_path)
            track = ET.parse(xml_path).getroot().find("./COLLECTION/TRACK")
            assert track is not None
            self.assertEqual(track.attrib["Name"], "Track")
            self.assertEqual(track.attrib["Artist"], "Artist")
            self.assertEqual(track.attrib["Genre"], "House")
            self.assertEqual(track.attrib["Album"], "Night Set")

    def test_filename_metadata_fallback(self) -> None:
        self.assertEqual(split_artist_title("Artist - Track"), ("Artist", "Track"))
        self.assertEqual(split_artist_title("Track"), ("", "Track"))


if __name__ == "__main__":
    unittest.main()
