"""FastAPI delivery layer for the paginated DJ Library catalog."""

from __future__ import annotations

import json
import math
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from fastapi import APIRouter, HTTPException, Query

from audioextender.library.job_catalog import LibraryJobCatalogService, LibraryTrackRemovalError
from audioextender.library.musical_profile import musical_profile


@dataclass(frozen=True)
class LibraryRouteDependencies:
    repository: Callable[[], Any]
    ensure_search_index_current: Callable[[], Any]
    generalized_genre: Callable[[str], str]
    catalog_cache: dict[str, Any]
    catalog_cache_lock: Any
    job_catalog: LibraryJobCatalogService | None = None


def create_library_router(deps: LibraryRouteDependencies) -> APIRouter:
    """Create catalog routes without coupling them to the application module."""
    router = APIRouter(prefix="/api/library", tags=["library"])

    job_catalog = deps.job_catalog
    if job_catalog is not None:

        @router.delete("/{source_name}")
        def remove_library_track(source_name: str) -> dict:
            try:
                return job_catalog.remove(source_name)
            except LibraryTrackRemovalError as error:
                raise HTTPException(error.status_code, error.detail) from error

    @router.get("/catalog")
    def catalog(
        page: int = Query(default=1, ge=1),
        page_size: int = Query(default=50, ge=1, le=100),
        search: str = "",
        role: str = "all",
        category: str = "all",
        detailed_genre: str = "all",
        preset: str = "all",
        result: str = "all",
        bpm_min: float | None = None,
        bpm_max: float | None = None,
        key: str = "all",
        energy: str = "all",
        vocals: str = "all",
        timing: str = "all",
        quality: str = Query(
            default="all",
            pattern="^(all|excellent|good|review|poor|below-target|unanalyzed)$",
        ),
        sort: str = "newest",
    ) -> dict:
        """Return the compact index; expensive generation history stays lazy."""
        signature = deps.ensure_search_index_current()
        repository = deps.repository()
        rows, filtered_total = repository.page_library_tracks(
            page=page,
            page_size=page_size,
            search=search,
            role=role,
            category=category,
            detail_genre=detailed_genre,
            preset=preset,
            result=result,
            quality=quality,
            bpm_min=bpm_min,
            bpm_max=bpm_max,
            musical_key=key,
            energy=energy,
            vocals=vocals,
            timing=timing,
            sort=sort,
        )
        with deps.catalog_cache_lock:
            cached_facets = (
                deps.catalog_cache.get("facets") if deps.catalog_cache.get("facets_signature") == signature else None
            )
        if cached_facets is None:
            facets = repository.library_search_facets()
            with deps.catalog_cache_lock:
                deps.catalog_cache["facets_signature"] = signature
                deps.catalog_cache["facets"] = facets
            facets = dict(facets)
        else:
            facets = dict(cached_facets)

        total_pages = max(1, math.ceil(filtered_total / page_size))
        if page > total_pages:
            page = total_pages
            rows, filtered_total = repository.page_library_tracks(
                page=page,
                page_size=page_size,
                search=search,
                role=role,
                category=category,
                detail_genre=detailed_genre,
                preset=preset,
                result=result,
                quality=quality,
                bpm_min=bpm_min,
                bpm_max=bpm_max,
                musical_key=key,
                energy=energy,
                vocals=vocals,
                timing=timing,
                sort=sort,
            )

        tracks = [_catalog_track(row, deps.generalized_genre) for row in rows]
        intelligence = [
            {
                "job_id": item["job_id"],
                "source_name": item["source_name"],
                "analysis": _serialized_analysis(item),
            }
            for item in facets.pop("intelligence")
        ]
        return {
            "tracks": tracks,
            "total": facets["total"],
            "filtered_total": filtered_total,
            "page": page,
            "page_size": page_size,
            "total_pages": total_pages,
            "facets": facets,
            "intelligence": intelligence,
        }

    return router


def _serialized_analysis(item: dict[str, Any]) -> dict[str, Any]:
    analysis = {
        "source_name": item["source_name"],
        "bpm": item["bpm"],
        "key": item["musical_key"],
        "_roles": str(item.get("roles") or "").strip("|").split("|"),
        "_energy": item["energy"],
        "_vocals": item["vocals"],
        "_timing": item["timing"],
    }
    return analysis | {"musical_profile": musical_profile(analysis)}


def _catalog_track(row: dict[str, Any], generalized_genre: Callable[[str], str]) -> dict:
    row.pop("analysis_json", None)
    analysis = {
        "source_name": row.get("source_name") or "",
        "bpm": row.get("library_bpm") or row.get("bpm") or 0,
        "key": row.get("musical_key") or "",
        "_roles": str(row.get("library_roles") or "").strip("|").split("|"),
        "_energy": row.get("library_energy"),
        "_vocals": row.get("vocals") or "mixed",
        "_timing": row.get("timing") or "steady",
    }
    analysis["musical_profile"] = musical_profile(analysis)
    downloaded = None
    if row.get("downloaded_id"):
        try:
            quality_details = json.loads(str(row.get("audio_quality_json") or "{}"))
        except (TypeError, ValueError, json.JSONDecodeError):
            quality_details = {}
        downloaded = {
            "id": row["downloaded_id"],
            "title": row["library_title"],
            "artist": row["library_artist"],
            "genre": row.get("genre") or "",
            "genre_category": row["library_category"],
            "recording_code": row.get("recording_code") or "",
            "version_code": row.get("version_code") or "",
            "identity_confidence": row.get("identity_confidence") or "",
            "identity_reason": row.get("identity_reason") or "",
            "identity_inference_locked": bool(row.get("identity_inference_locked")),
            "audio_quality_score": row.get("audio_quality_score"),
            "audio_quality_label": row.get("audio_quality_label") or "",
            "audio_quality": quality_details,
            "descriptors": _descriptor_payload(row.get("descriptors_json")),
            "suggested_genre": generalized_genre(str(row.get("genre") or "")),
            "completed_library_job_id": row["job_id"],
            "artwork_available": bool(row.get("artwork_path")) and Path(str(row["artwork_path"])).is_file(),
        }
    job_fields = (
        "id",
        "source_name",
        "source_path",
        "status",
        "progress",
        "stage",
        "preset",
        "intro_bars",
        "outro_bars",
        "use_stems",
        "config_json",
        "error",
        "extended_path",
        "wav_path",
        "intro_preview_path",
        "outro_preview_path",
        "cue_sheet_path",
        "rekordbox_path",
        "parent_job_id",
        "bpm",
        "intro_quality",
        "outro_quality",
        "review_status",
        "created_at",
        "updated_at",
        "generation_count",
    )
    return {
        "job": {field: row.get(field) for field in job_fields},
        "analysis": analysis,
        "downloaded": downloaded,
    }


def _descriptor_payload(raw: Any) -> list[dict[str, Any]]:
    try:
        value = json.loads(str(raw or "[]"))
    except (TypeError, ValueError, json.JSONDecodeError):
        return []
    return value if isinstance(value, list) else []
