"""Stable, human-readable identities for recordings and their versions."""

from __future__ import annotations

import hashlib
import re
import unicodedata
from dataclasses import dataclass
from pathlib import Path

_VERSION_PATTERNS = (
    ("LIVE", re.compile(r"\b(?:live|concert|session)\b", re.I)),
    ("RMX", re.compile(r"\b(?:remix|mix by|rework|bootleg|mashup)\b", re.I)),
    ("EXT", re.compile(r"\b(?:extended|club mix|12[\"”]? mix)\b", re.I)),
    ("RADIO", re.compile(r"\b(?:radio edit|radio mix|single edit)\b", re.I)),
    ("REM", re.compile(r"\b(?:remaster(?:ed)?|anniversary edition)\b", re.I)),
    ("INST", re.compile(r"\b(?:instrumental|karaoke)\b", re.I)),
    ("ACAP", re.compile(r"\b(?:a\s*cappella|acapella|vocals? only)\b", re.I)),
)

_ARTIST_CREDIT_SEPARATOR = re.compile(
    r"\s*(?:,|;|/|\b(?:feat(?:uring)?|ft|vs)\.?\b)\s*",
    re.I,
)


@dataclass(frozen=True)
class RecordingFamilyInference:
    """Conservative evidence that two catalog rows describe one song family."""

    confidence: str
    reason: str
    strength: int


def normalize_identity_text(value: str) -> str:
    value = unicodedata.normalize("NFKD", value).encode("ascii", "ignore").decode()
    return " ".join(re.sub(r"[^a-z0-9]+", " ", value.casefold()).split())


def version_kind(title: str) -> str:
    for code, pattern in _VERSION_PATTERNS:
        if pattern.search(title):
            return code
    return "ORG"


def base_title(title: str) -> str:
    detected_kind = version_kind(title)
    value = re.sub(
        r"\([^)]*\)|\[[^]]*\]",
        lambda match: (
            " "
            if version_kind(match.group(0)) != "ORG"
            or re.search(r"\b(?:version|edit|feat(?:uring)?|ft)\.?\b", match.group(0), re.I)
            else match.group(0)
        ),
        title,
    )
    for _, pattern in _VERSION_PATTERNS:
        value = pattern.sub(" ", value)
    if detected_kind != "ORG":
        value = re.sub(r"\b(?:mix|version|edit)\b", " ", value, flags=re.I)
    return normalize_identity_text(value)


def canonical_title_key(title: str, artist: str = "") -> str:
    """Return a conservative comparison key for the same underlying song.

    Word spacing is not meaningful for recording identity (``Funkytown`` and
    ``Funky Town``), but arbitrary fuzzy title similarity is intentionally not
    used.  A trailing artist/version credit is removed only when it starts with
    the catalog artist and the remaining words are an unambiguous version label.
    """
    value = title
    parts = re.split(r"\s+[-–—]\s+", title)
    if len(parts) > 1:
        if version_kind(title) != "ORG" and version_kind(parts[-1]) != "ORG":
            value = " - ".join(parts[:-1])
        suffix = normalize_identity_text(parts[-1])
        artist_text = normalize_identity_text(artist)
        remainder = suffix
        if artist_text and (suffix == artist_text or suffix.startswith(f"{artist_text} ")):
            remainder = suffix[len(artist_text) :].strip()
        version_words = {"club", "mix", "edit", "version", "extended", "radio", "original"}
        if remainder and set(remainder.split()).issubset(version_words):
            value = " - ".join(parts[:-1])
    return base_title(value).replace(" ", "")


def artist_credit_keys(artist: str) -> set[str]:
    """Return normalized full and individual artist credits.

    Ampersands are intentionally not separators because they commonly belong to
    a single act's name. Short partial credits are retained for exact full-name
    comparisons but are not enough to establish cross-credit overlap.
    """
    full = normalize_identity_text(artist)
    if not full:
        return set()
    parts = {
        normalize_identity_text(part)
        for part in _ARTIST_CREDIT_SEPARATOR.split(artist)
        if normalize_identity_text(part)
    }
    return {full, *parts}


def artists_share_credit(left: str, right: str) -> bool:
    """Return whether two artist fields share a conservative named credit."""
    left_full = normalize_identity_text(left)
    right_full = normalize_identity_text(right)
    if not left_full or not right_full:
        return False
    if left_full == right_full:
        return True
    return any(len(credit.replace(" ", "")) >= 4 for credit in artist_credit_keys(left) & artist_credit_keys(right))


def infer_recording_family(
    left_artist: str,
    left_title: str,
    right_artist: str,
    right_title: str,
) -> RecordingFamilyInference | None:
    """Infer a shared song family from structured metadata, never fuzzy titles.

    Version words, bracketed remix/feature credits, harmless spacing, and
    diacritics are normalized before comparison. A shared named artist credit
    is still required so unrelated covers with the same title remain separate.
    """
    left_title_key = canonical_title_key(left_title, left_artist)
    right_title_key = canonical_title_key(right_title, right_artist)
    if not left_title_key or left_title_key != right_title_key:
        return None
    if not artists_share_credit(left_artist, right_artist):
        return None
    exact_artist = normalize_identity_text(left_artist) == normalize_identity_text(right_artist)
    return RecordingFamilyInference(
        confidence="review",
        reason=(
            "Matched canonical song title and artist"
            if exact_artist
            else "Matched canonical song title and shared artist credit"
        ),
        strength=2 if exact_artist else 1,
    )


def identity_key(artist: str, title: str) -> str:
    return f"{normalize_identity_text(artist)}|{canonical_title_key(title, artist)}"


def recording_dedupe_key(
    artist: str,
    title: str,
    *,
    recording_code: str = "",
) -> str:
    """Return the Set Builder identity for one underlying recording.

    A persisted family is authoritative.  The normalized metadata key is a
    safe fallback for analyzed jobs that have not entered the catalog yet.
    """
    code = str(recording_code or "").strip().upper()
    return f"recording:{code}" if code else f"metadata:{identity_key(artist, title)}"


def genre_family_code(genre_category: str) -> str:
    """Return a stable, readable three-letter code for a parent genre."""
    value = normalize_identity_text(genre_category)
    if value.startswith("afro") or value.startswith("amapiano"):
        return "AFR"
    rules = (
        ("drum bass", "DNB"),
        ("hip hop", "HIP"),
        ("r b", "RNB"),
        ("disco", "DSC"),
        ("house", "HOU"),
        ("funk", "DSC"),
        ("latin", "LAT"),
        ("reggae", "REG"),
        ("dancehall", "REG"),
        ("ambient", "AMB"),
        ("chill", "AMB"),
        ("techno", "TEC"),
        ("electronic", "ELC"),
        ("pop", "POP"),
        ("rock", "RCK"),
        ("alternative", "RCK"),
    )
    return next((code for phrase, code in rules if phrase in value), "OTH")


def format_family_code(number: int, genre_category: str = "Other") -> str:
    return f"{genre_family_code(genre_category)}-{number:06d}"


def next_version_code(kind: str, existing: set[str]) -> str:
    if kind in {"ORG", "RADIO", "INST", "ACAP"} and kind not in existing:
        return kind
    if kind == "ORG":
        number = 2
        while f"ORG{number:02d}" in existing:
            number += 1
        return f"ORG{number:02d}"
    number = 1
    while f"{kind}{number:02d}" in existing:
        number += 1
    return f"{kind}{number:02d}"


def audio_fingerprint(path: Path, sample_bytes: int = 131_072) -> str:
    """Build a fast exact-file signature without decoding the entire recording."""
    size = path.stat().st_size
    digest = hashlib.sha256(str(size).encode("ascii"))
    with path.open("rb") as source:
        digest.update(source.read(sample_bytes))
        if size > sample_bytes:
            source.seek(max(0, size - sample_bytes))
            digest.update(source.read(sample_bytes))
    return digest.hexdigest()
