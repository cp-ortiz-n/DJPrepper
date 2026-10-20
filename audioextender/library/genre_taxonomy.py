"""Authoritative folder taxonomy for imported and cataloged music."""

from __future__ import annotations

import re
import unicodedata
from pathlib import Path


def safe_audio_name(value: str) -> str:
    """Return a filesystem-safe display name without changing its meaning."""
    cleaned = "".join(character for character in value if character not in '<>:"/\\|?*')
    return cleaned.strip()[:180] or "Imported Audio"


def safe_folder_name(value: str) -> str:
    """Return a filesystem-safe folder component."""
    return safe_audio_name(value).strip(". ") or "Imported Playlist"


def generalized_genre(value: str) -> str:
    """Map detailed provider genres to practical DJ-library folders."""
    genre = unicodedata.normalize("NFKD", str(value or "")).encode("ascii", "ignore").decode().casefold()
    electronic_families = (
        ("Techno / Schranz", ("schranz",)),
        ("Techno / Hard Techno", ("hard techno",)),
        ("Techno / Acid Techno", ("acid techno",)),
        ("Techno / Melodic Techno", ("melodic techno",)),
        ("Techno / Minimal Techno", ("minimal techno", "minimal tech")),
        ("Techno / Industrial Techno", ("industrial techno",)),
        ("Techno / Hypnotic Techno", ("hypnotic techno", "dub techno")),
        ("Techno / Peak-Time Techno", ("peak time techno", "peak-time techno")),
        ("Techno / Techno", ("techno", "tekno", "rave")),
        ("House / Afro House", ("afro house",)),
        ("House / Latin House", ("latin house", "tribal house", "guaracha")),
        ("House / Deep House", ("deep house",)),
        ("House / Tech House", ("tech house",)),
        ("House / Progressive House", ("progressive house",)),
        ("House / Melodic House", ("melodic house",)),
        ("House / Organic House", ("organic house",)),
        ("House / Bass House", ("bass house",)),
        ("House / Soulful House", ("soulful house",)),
        ("House / Funky House", ("funky house", "disco house")),
        ("House / Amapiano", ("amapiano",)),
        ("House / House", ("house",)),
        ("Bass / Future Bass", ("future bass",)),
        ("Bass / Dubstep", ("dubstep",)),
        ("Bass / Moombahton", ("moombahton",)),
        ("Bass / Phonk", ("drift phonk", "phonk")),
        ("Bass / Deep Bass", ("deep bass", "bass music")),
        ("Drum & Bass / Liquid", ("liquid drum and bass", "liquid dnb")),
        ("Drum & Bass / Jungle", ("jungle",)),
        ("Drum & Bass / Drum & Bass", ("drum and bass", "drum & bass", "dnb")),
        ("Trance / Psytrance", ("psytrance", "psy trance")),
        ("Trance / Hard Trance", ("hard trance",)),
        ("Trance / Trance", ("trance",)),
        ("Garage / UK Garage", ("uk garage", "ukg", "2-step", "2 step")),
        ("Garage / Garage", ("garage",)),
        ("Breaks / Big Beat", ("big beat",)),
        ("Breaks / Breakbeat", ("breakbeat", "breaks", "broken beat")),
        ("Downtempo / Trip Hop", ("trip hop",)),
        ("Hardcore / Gabber", ("gabber",)),
        ("Hardcore / Hardstyle", ("hardstyle",)),
        ("Hardcore / Hardcore", ("hardcore",)),
        ("Electronic / Electro", ("electro",)),
    )
    latin_families = (
        ("Reggaeton", ("reggaeton", "reggaeton", "urbano latino", "latin urban")),
        ("Reggaeton", ("neoperreo",)),
        ("Salsa", ("salsa", "timba", "son cubano", "mambo")),
        ("Cumbia", ("cumbia", "chicha", "tecnocumbia")),
        ("Merengue", ("merengue", "perico ripiao", "merengue urbano")),
        ("Zapateado", ("zapateado", "duranguense", "huapango", "quebradita")),
        ("Corridos", ("corrido", "corridos", "corridos tumbados")),
        (
            "Regional Mexican",
            ("regional mexican", "musica mexicana", "banda", "norteno", "sierreno", "ranchera", "mariachi"),
        ),
        ("Bachata", ("bachata",)),
        ("Dembow", ("dembow",)),
        ("Latin Pop", ("latin pop", "pop latino")),
        ("Latin Jazz", ("latin jazz", "afro-cuban jazz", "afro cuban jazz")),
        ("Bolero", ("bolero",)),
        ("Vallenato", ("vallenato",)),
        ("Brazilian", ("brazilian", "funk carioca", "baile funk", "samba", "pagode")),
        ("Flamenco", ("flamenco",)),
        ("Latin Rock", ("rock en espanol", "rock en espanol", "latin rock", "mexican rock")),
        ("Latin Indie", ("latin indie", "mexican indie", "latin alternative")),
        ("Latin Ska", ("mexican ska", "latin ska")),
        ("Latin Hip-Hop", ("latin hip hop", "mexican hip hop")),
        ("Latin R&B", ("latin r&b",)),
    )
    latin_matches = [(genre.find(term), family) for family, terms in latin_families for term in terms if term in genre]
    if latin_matches:
        return f"Latin / {min(latin_matches, key=lambda match: match[0])[1]}"
    electronic_matches = [
        (genre.find(term), family)
        for family, terms in electronic_families
        for term in terms
        if term in genre and (term != "electro" or re.search(r"(?<![a-z0-9])electro(?![a-z0-9])", genre))
    ]
    if electronic_matches:
        return f"Electronic / {electronic_matches[0][1]}"
    families = (
        ("Hip-Hop & Rap / Crunk", ("crunk",)),
        ("Hip-Hop & Rap / Hyphy", ("hyphy",)),
        ("Hip-Hop & Rap", ("hip hop", "hip-hop", "rap", "trap")),
        ("R&B & Soul", ("r&b", "rnb", "soul")),
        ("Disco & Funk", ("disco", "funk")),
        ("Rock & Alternative", ("rock", "indie", "alternative", "punk", "metal")),
        ("Pop / Chanson", ("chanson", "variete francaise", "variete francaise")),
        ("Pop", ("pop",)),
        ("Ambient & Chill", ("ambient", "downtempo", "chill", "lo-fi", "lofi")),
        ("Afro & Amapiano", ("afro", "afrobeats")),
    )
    matched = next((family for family, terms in families if any(term in genre for term in terms)), "")
    if matched:
        return matched
    if any(term in genre for term in ("latin", "latino", "musica mexicana")):
        return "Latin / Other"
    if any(term in genre for term in ("electronic", "edm", "dance", "big room")):
        return "Electronic / General"
    return "Other"


LATIN_SUBGENRES = frozenset(
    {
        "reggaeton",
        "salsa",
        "cumbia",
        "merengue",
        "zapateado",
        "corridos",
        "regional mexican",
        "bachata",
        "dembow",
        "latin house",
        "latin pop",
        "latin jazz",
        "bolero",
        "vallenato",
        "brazilian",
        "flamenco",
        "latin rock",
        "latin indie",
        "latin ska",
        "latin hip-hop",
        "latin r&b",
    }
)

LEGACY_ELECTRONIC_CATEGORIES = {
    "techno": "Electronic / Techno / Techno",
    "house": "Electronic / House / House",
    "trance": "Electronic / Trance / Trance",
    "drum & bass": "Electronic / Drum & Bass / Drum & Bass",
    "garage": "Electronic / Garage / Garage",
    "breaks": "Electronic / Breaks / Breakbeat",
    "electronic": "Electronic / Electronic / Electronic",
}


def normalize_genre_category(value: str) -> str:
    """Normalize user and importer categories into the on-disk taxonomy."""
    cleaned = str(value or "Other").strip()
    legacy_electronic = LEGACY_ELECTRONIC_CATEGORIES.get(cleaned.casefold())
    if legacy_electronic:
        return legacy_electronic
    if cleaned.casefold() in {"electronic / electronic / electronic", "electronic / general"}:
        return "Electronic / General"
    if cleaned.casefold() == "latin & reggaeton":
        return "Latin / Other"
    is_latin_path = cleaned.casefold().startswith("latin / ")
    lowered = cleaned.casefold().removeprefix("latin / ").strip()
    if is_latin_path and lowered == "other":
        return "Latin / Other"
    if lowered in LATIN_SUBGENRES:
        label = lowered.title()
        label = {"Reggaeton": "Reggaeton", "Dembow": "Dembow"}.get(label, label)
        return f"Latin / {label}"
    parts = [part.strip() for part in cleaned.split(" / ") if part.strip()]
    return " / ".join(safe_folder_name(part) for part in parts) or "Other"


def genre_path_parts(category: str) -> tuple[str, ...]:
    """Translate a normalized category into safe nested folder components."""
    normalized = normalize_genre_category(category)
    return tuple(safe_folder_name(part) for part in normalized.split(" / "))


def catalog_genre_category(
    wav_path: Path,
    stored_category: str,
    detailed_genre: str,
    *,
    library_root: Path,
) -> str:
    """Resolve catalog genre while preserving a user's folder choice."""
    stored = normalize_genre_category(stored_category or "Other")
    if not detailed_genre.strip() and stored in {"Other", "Latin / Other"}:
        return "Other"
    inferred = generalized_genre(detailed_genre)
    if stored == "Latin / Other" and inferred == "Other":
        stored = "Other"
    try:
        relative = wav_path.resolve().relative_to(library_root.resolve())
        folder_parts = relative.parts[:-1]
        if folder_parts and folder_parts[0] != ".audioextender":
            path_category = normalize_genre_category(" / ".join(folder_parts))
            if path_category == "Latin / Other" and inferred != "Latin / Other":
                return inferred
            return path_category
    except (ValueError, OSError):
        pass
    if stored not in {"Other", "Latin / Other"}:
        return stored
    return inferred if inferred != "Other" else stored
