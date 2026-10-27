"""Build catalog search and Set Builder projections outside HTTP composition."""

from __future__ import annotations

import json
import re
from collections.abc import Callable
from pathlib import Path
from typing import Any

from audioextender.library.musical_corrections import MusicalCorrectionIndex
from audioextender.library.musical_profile import musical_profile
from audioextender.library.playlist_identity import catalog_genre_terms, playlist_identity_projection


class CatalogProjectionBuilder:
    """Translate durable jobs and catalog rows into compact read models."""

    def __init__(
        self,
        *,
        repository: Callable[[], Any],
        load_processing_report: Callable[[], dict[str, Any]],
        normalize_genre_category: Callable[[str], str],
        catalog_path: Callable[[], Path],
        camelot_keys: dict[str, str],
    ) -> None:
        self._repository = repository
        self._load_processing_report = load_processing_report
        self._normalize_genre_category = normalize_genre_category
        self._catalog_path = catalog_path
        self._camelot_keys = camelot_keys

    def _roles(self, song: dict) -> list[str]:
        return musical_profile(song)["roles"]

    def _energy(self, song: dict) -> float:
        return float(musical_profile(song)["energy"])

    def _set_builder_analysis(self, song: dict, *, roles: list[str], energy: float, vocals: str, timing: str) -> dict:
        profile = musical_profile(song | {"_roles": roles, "_energy": energy, "_vocals": vocals, "_timing": timing})
        base_fields = {
            "source_name",
            "bpm",
            "detected_bpm",
            "bpm_verified",
            "key",
            "key_confidence",
            "beat_grid_confidence",
            "duration_seconds",
            "mix_in",
            "mix_out",
        }
        compact = {key: value for key, value in song.items() if key in base_fields}
        compact.update(
            {
                "_roles": roles,
                "_energy": energy,
                "_vocals": vocals,
                "_timing": timing,
                "musical_profile": profile,
                "intro": {
                    key: value
                    for key, value in (song.get("intro") or {}).items()
                    if key in {"instrumentalness", "section"}
                },
                "outro": {
                    key: value
                    for key, value in (song.get("outro") or {}).items()
                    if key in {"instrumentalness", "section"}
                },
                "dj_readiness": {
                    key: value
                    for key, value in (song.get("dj_readiness") or {}).items()
                    if key in {"intro_mixable_bars", "outro_mixable_bars"}
                },
                "arrangement_sections": [
                    {
                        key: value
                        for key, value in section.items()
                        if key in {"label", "name", "start", "end", "confidence"}
                    }
                    for section in (song.get("arrangement_sections") or [])
                ],
            }
        )
        return compact

    def build_catalog_payload(self) -> dict:
        rows = self._repository().list_set_builder_tracks()
        genre_terms = catalog_genre_terms(rows)
        tracks = []
        for row in rows:
            try:
                descriptors = json.loads(str(row.get("descriptors_json") or "[]"))
            except (TypeError, ValueError, json.JSONDecodeError):
                descriptors = []
            analysis = json.loads(row.get("set_analysis_json") or "{}")
            analysis.update(
                title=row.get("title") or "",
                artist=row.get("artist") or "",
                _camelot=row.get("camelot") or "",
            )
            tracks.append(
                {
                    "analysis": analysis,
                    "genre": row.get("category") or "Other",
                    "detailed_genre": row.get("detail_genre") or "",
                    "downloaded_id": row.get("downloaded_id"),
                    "recording_code": row.get("recording_code") or "",
                    "version_code": row.get("version_code") or "",
                    "external_rating": json.loads(row.get("external_rating_json") or "null"),
                    "descriptors": descriptors,
                    **playlist_identity_projection(row.get("playlists_json"), genre_terms),
                    "job": {
                        "id": row["job_id"],
                        "source_name": row["source_name"],
                        "source_path": row.get("source_path"),
                        "wav_path": row.get("wav_path"),
                        "library_path": row.get("library_path"),
                        "extended_path": row.get("extended_path"),
                        "config_json": row.get("config_json") or "{}",
                    },
                }
            )
        return {"version": 10, "tracks": tracks, "total": len(tracks)}

    def write_catalog_cache(self) -> None:
        payload = self.build_catalog_payload()
        self._catalog_path().parent.mkdir(parents=True, exist_ok=True)
        temporary = self._catalog_path().with_suffix(".pending.json")
        temporary.write_text(json.dumps(payload, separators=(",", ":")), encoding="utf-8")
        temporary.replace(self._catalog_path())

    def rebuild(self) -> None:
        analysis_by_name = {
            str(song.get("source_name") or "").casefold(): song
            for song in self._load_processing_report().get("songs", {}).values()
        }
        repository = self._repository()
        downloaded_tracks = repository.list_downloaded_tracks_with_jobs()
        downloaded_by_path = {str(track.get("file_path") or ""): track for track in downloaded_tracks}
        downloaded_by_job = {
            int(track["completed_library_job_id"]): track
            for track in downloaded_tracks
            if track.get("completed_library_job_id")
        }
        corrections = MusicalCorrectionIndex.from_records(
            repository.key_verifications(), repository.bpm_verifications()
        )
        entries = []
        for job in repository.list_latest_completed_jobs():
            song = dict(analysis_by_name.get(str(job.get("source_name") or "").casefold(), {}))
            song = corrections.apply(song, str(job.get("source_name") or ""), detected_bpm_fallback=job.get("bpm"))
            downloaded = downloaded_by_job.get(int(job["id"])) or downloaded_by_path.get(
                str(job.get("source_path") or "")
            )
            if downloaded and downloaded.get("key_analyzed_at"):
                song["key"] = downloaded.get("detected_key") or song.get("key")
                song["key_confidence"] = float(downloaded.get("key_confidence") or 0) / 100.0
            source_stem = re.sub(r"\.[^.]+$", "", str(job.get("source_name") or ""))
            source_parts = source_stem.split(" - ")
            title = str(downloaded.get("title") or "") if downloaded else ""
            artist = str(downloaded.get("artist") or "") if downloaded else ""
            title = title or (" - ".join(source_parts[1:]) if len(source_parts) > 1 else source_stem)
            artist = artist or (source_parts[0] if len(source_parts) > 1 else "Unknown artist")
            category = (
                self._normalize_genre_category(str(downloaded.get("genre_category") or "Other"))
                if downloaded
                else str(song.get("detected_style") or "Unclassified")
            )
            roles = self._roles(song)
            energy = self._energy(song)
            analyzed_preset = str(song.get("preset") or "")
            preset = (
                analyzed_preset.split("→")[-1].strip() if "→" in analyzed_preset else analyzed_preset.strip()
            ) or str(job.get("preset") or "default")
            result = (
                "review"
                if job.get("review_status") == "pending"
                else "extended"
                if job.get("intro_quality") is not None or job.get("outro_quality") is not None
                else "preserved"
            )
            musical_key = (
                str(song.get("key") or "")
                .replace("Db ", "C# ")
                .replace("Eb ", "D# ")
                .replace("Gb ", "F# ")
                .replace("Ab ", "G# ")
                .replace("Bb ", "A# ")
            )
            instrumental_values = [
                float(value)
                for value in (
                    (song.get("intro") or {}).get("instrumentalness"),
                    (song.get("outro") or {}).get("instrumentalness"),
                )
                if value is not None
            ]
            instrumental = max(instrumental_values) if instrumental_values else None
            timing_text = str(song.get("timing") or "").casefold()
            vocal_profile = (
                "mixed"
                if instrumental is None
                else "vocal-safe"
                if instrumental >= 0.72
                else "vocal-forward"
                if instrumental < 0.45
                else "mixed"
            )
            timing_profile = (
                "variable"
                if "live" in timing_text or "variable" in timing_text or float(song.get("tempo_drift") or 0) >= 0.08
                else "steady"
            )
            entries.append(
                {
                    "job_id": int(job["id"]),
                    "source_name": job["source_name"],
                    "title": title,
                    "artist": artist,
                    "downloaded_id": int(downloaded["id"]) if downloaded else None,
                    "category": category,
                    "detail_genre": str(downloaded.get("genre") or "").strip() if downloaded else "",
                    "roles": f"|{'|'.join(roles)}|",
                    "preset": preset.casefold(),
                    "requested_preset": str(job.get("preset") or "default").casefold(),
                    "result": result,
                    "bpm": float(song.get("bpm") or job.get("bpm") or 0),
                    "musical_key": musical_key,
                    "camelot": self._camelot_keys.get(musical_key, ""),
                    "energy": energy,
                    "energy_band": "high" if energy >= 0.67 else "low" if energy < 0.4 else "medium",
                    "vocals": vocal_profile,
                    "timing": timing_profile,
                    "updated_at": job["updated_at"],
                    "analysis_json": json.dumps(song, separators=(",", ":")),
                    "set_analysis_json": json.dumps(
                        self._set_builder_analysis(
                            song, roles=roles, energy=energy, vocals=vocal_profile, timing=timing_profile
                        ),
                        separators=(",", ":"),
                    ),
                }
            )
        repository.replace_library_search_index(entries)
        self.write_catalog_cache()
