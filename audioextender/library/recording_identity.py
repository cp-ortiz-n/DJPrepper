"""Stable, human-readable identities for recordings and their versions."""

from __future__ import annotations

import hashlib
import re
import unicodedata
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
            if version_kind(match.group(0)) != "ORG" or re.search(r"\b(?:version|edit)\b", match.group(0), re.I)
            else match.group(0)
        ),
        title,
    )
    for _, pattern in _VERSION_PATTERNS:
        value = pattern.sub(" ", value)
    if detected_kind != "ORG":
        value = re.sub(r"\b(?:mix|version|edit)\b", " ", value, flags=re.I)
    return normalize_identity_text(value)


def identity_key(artist: str, title: str) -> str:
    return f"{normalize_identity_text(artist)}|{base_title(title)}"


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
