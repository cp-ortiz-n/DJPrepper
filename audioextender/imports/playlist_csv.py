"""Parsing for exported playlist CSV files."""

from __future__ import annotations

import csv
import io
from collections.abc import Callable


def parse_playlist_csv(contents: bytes, generalized_genre: Callable[[str], str]) -> list[dict]:
    """Parse common playlist-export columns into the import matching contract."""
    try:
        text = contents.decode("utf-8-sig")
    except UnicodeDecodeError as error:
        raise ValueError("Playlist CSV must use UTF-8 text encoding") from error
    reader = csv.DictReader(io.StringIO(text))
    fields = {field.casefold().strip(): field for field in (reader.fieldnames or [])}
    title_field = next((fields[name] for name in ("track name", "title", "name") if name in fields), None)
    artist_field = next(
        (fields[name] for name in ("artist name(s)", "artist name", "artists", "artist") if name in fields),
        None,
    )
    if title_field is None or artist_field is None:
        raise ValueError("CSV needs track and artist columns, such as Track Name and Artist Name(s)")
    duration_field = fields.get("duration (ms)") or fields.get("duration_ms")
    tracks: list[dict] = []
    for row in reader:
        title = str(row.get(title_field) or "").strip()
        artist = str(row.get(artist_field) or "").strip().replace(";", ", ")
        if not title or not artist:
            continue
        duration = str(row.get(duration_field) or "").strip() if duration_field else ""
        genre = str(row.get(fields.get("genres", "")) or "").strip()
        tracks.append(
            {
                "title": title,
                "artist": artist,
                "duration_ms": int(duration) if duration.isdigit() else None,
                "genre": genre,
                "genre_category": generalized_genre(genre),
                "tempo": str(row.get(fields.get("tempo", "")) or "").strip(),
                "spotify_uri": str(row.get(fields.get("track uri", "")) or "").strip(),
            }
        )
    if not tracks:
        raise ValueError("The playlist CSV does not contain any usable tracks")
    return tracks
