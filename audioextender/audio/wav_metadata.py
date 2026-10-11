"""Embed portable DJ metadata in PCM WAV containers."""

from __future__ import annotations

import json
import os
import subprocess
import tempfile
from pathlib import Path

from mutagen.id3 import APIC
from mutagen.wave import WAVE


def _embedded_artwork(path: Path) -> tuple[bytes, str] | None:
    audio = WAVE(path)
    if audio.tags is None:
        return None
    picture = next(iter(audio.tags.getall("APIC")), None)
    return (bytes(picture.data), str(picture.mime or "image/jpeg")) if picture else None


def embed_wav_artwork(path: Path, artwork: Path | bytes, mime: str = "image/jpeg") -> None:
    """Embed front-cover art in the WAV ID3 chunk without touching PCM audio."""
    data = artwork.read_bytes() if isinstance(artwork, Path) else bytes(artwork)
    if not data:
        return
    audio = WAVE(path)
    if audio.tags is None:
        audio.add_tags()
    tags = audio.tags
    if tags is None:
        raise RuntimeError("WAV artwork tags could not be initialized")
    tags.delall("APIC")
    tags.add(APIC(encoding=3, mime=mime, type=3, desc="Cover", data=data))
    audio.save()


def split_artist_title(stem: str) -> tuple[str, str]:
    """Use the project's `Artist - Title` filename convention when available."""
    artist, separator, title = stem.partition(" - ")
    return (artist.strip(), title.strip()) if separator else ("", stem.strip())


def write_wav_metadata(
    path: Path,
    *,
    title: str,
    artist: str = "",
    genre: str = "",
    album: str = "",
) -> None:
    """Atomically rewrite a WAV with RIFF metadata without re-encoding PCM audio."""
    source = path.resolve()
    if not source.is_file():
        raise FileNotFoundError(source)
    preserved_artwork = _embedded_artwork(source)
    descriptor, temporary_name = tempfile.mkstemp(prefix=f".{source.stem}-tags-", suffix=".wav", dir=source.parent)
    os.close(descriptor)
    temporary = Path(temporary_name)
    temporary.unlink(missing_ok=True)
    command = [
        "ffmpeg",
        "-nostdin",
        "-hide_banner",
        "-loglevel",
        "error",
        "-y",
        "-i",
        str(source),
        "-map",
        "0:a:0",
        "-c:a",
        "copy",
        "-metadata",
        f"title={title.strip()}",
        "-metadata",
        f"artist={artist.strip()}",
        "-metadata",
        f"genre={genre.strip()}",
        "-metadata",
        f"album={album.strip()}",
        str(temporary),
    ]
    try:
        subprocess.run(command, check=True, capture_output=True, text=True)
        os.replace(temporary, source)
        if preserved_artwork:
            embed_wav_artwork(source, preserved_artwork[0], preserved_artwork[1])
    finally:
        temporary.unlink(missing_ok=True)


def read_wav_metadata(path: Path) -> dict[str, str]:
    """Read container tags without decoding the audio payload."""
    source = path.resolve()
    if not source.is_file():
        raise FileNotFoundError(source)
    result = subprocess.run(
        [
            "ffprobe",
            "-v",
            "error",
            "-show_entries",
            "format_tags",
            "-of",
            "json",
            str(source),
        ],
        check=True,
        capture_output=True,
        text=True,
    )
    tags = json.loads(result.stdout or "{}").get("format", {}).get("tags", {})
    return {str(key).casefold(): str(value).strip() for key, value in tags.items()}


def read_wav_artwork(path: Path) -> dict[str, object] | None:
    """Return embedded artwork details without exposing the image bytes."""
    artwork = _embedded_artwork(path.resolve())
    return {"mime": artwork[1], "size": len(artwork[0])} if artwork else None


def sync_wav_metadata(
    path: Path,
    *,
    title: str,
    artist: str = "",
    genre: str = "",
    album: str = "",
) -> bool:
    """Return True only when the WAV needed to be rewritten."""
    expected = {
        "title": title.strip(),
        "artist": artist.strip(),
        "genre": genre.strip(),
        "album": album.strip(),
    }
    existing = read_wav_metadata(path)
    if all(existing.get(key, "") == value for key, value in expected.items()):
        return False
    write_wav_metadata(path, **expected)
    return True
