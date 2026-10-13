"""Read-model service for the downloaded music catalog."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class DownloadedCatalogQuery:
    paged: bool = False
    page: int = 1
    page_size: int = 50
    search: str = ""
    genre: str = "all"
    detailed_genre: str = "all"
    playlist: str = "all"
    analysis: str = "all"
    artwork: str = "all"
    quality: str = "all"
    sort: str = "newest"


@dataclass(frozen=True)
class DownloadedCatalogQueryService:
    repository: Callable[[], Any]
    ensure_catalog_migrated: Callable[[], None]
    normalize_genre_category: Callable[[str], str]
    track_payload: Callable[[dict[str, Any]], dict[str, Any]]

    @staticmethod
    def review_flags(track: dict[str, Any]) -> dict[str, bool]:
        title = str(track.get("title") or "").strip().casefold()
        artist = str(track.get("artist") or "").strip().casefold()
        detailed_genre = str(track.get("genre") or "").strip()
        category = str(track.get("genre_category") or "Other")
        return {
            "missing_title": title in {"", "unknown title", "untitled"},
            "missing_artist": artist in {"", "unknown artist", "unknown", "unavailable"},
            "missing_genre": not detailed_genre,
            "missing_artwork": not str(track.get("artwork_path") or "").strip(),
            "unmapped_genre": bool(detailed_genre) and category == "Other",
            "broad_genre": category.endswith(" / General") or category.endswith(" / Other"),
        }

    def execute(self, query: DownloadedCatalogQuery) -> dict[str, Any]:
        self.ensure_catalog_migrated()
        repository = self.repository()
        page = query.page
        if query.paged:
            facets = repository.downloaded_catalog_facets()
            tracks, filtered_total = self._page(repository, query, page)
            excluded_analysis = {
                "complete",
                "active",
                "attention",
                "missing_title",
                "missing_artist",
                "missing_genre",
                "missing_artwork",
                "unmapped_genre",
                "broad_genre",
            }
            if query.analysis in excluded_analysis:
                analyzable_total = 0
            else:
                _, analyzable_total = repository.page_downloaded_tracks(
                    page=1,
                    page_size=1,
                    search=query.search,
                    genre=query.genre,
                    detailed_genre=query.detailed_genre,
                    playlist=query.playlist,
                    artwork=query.artwork,
                    quality=query.quality,
                    analysis="failed" if query.analysis == "failed" else "needs",
                    sort=query.sort,
                )
            total_pages = max(1, (filtered_total + query.page_size - 1) // query.page_size)
            if page > total_pages:
                page = total_pages
                tracks, filtered_total = self._page(repository, query, page)
            genres: dict[str, int] = {}
            for raw_genre, count in facets["genres"].items():
                normalized = self.normalize_genre_category(raw_genre)
                genres[normalized] = genres.get(normalized, 0) + int(count)
            playlists = facets["playlists"]
        else:
            tracks = repository.list_downloaded_tracks_with_jobs()
            genres = {}
            playlists = {}
            for track in tracks:
                category = self.normalize_genre_category(str(track.get("genre_category") or "Other"))
                genres[category] = genres.get(category, 0) + 1
                for track_playlist in track.get("playlists", []):
                    playlists[track_playlist] = playlists.get(track_playlist, 0) + 1
            filtered_total = len(tracks)
            flags = [self.review_flags(track) for track in tracks]
            keys = flags[0] if flags else self.review_flags({})
            facets = {
                "total": len(tracks),
                "review_states": {
                    **{issue: sum(item[issue] for item in flags) for issue in keys},
                    "needs_attention": sum(any(item.values()) for item in flags),
                },
            }
            total_pages = 1
            analyzable_total = sum(
                (track.get("analysis_status") or "not_analyzed") not in {"queued", "processing", "complete"}
                for track in tracks
            )
        return {
            "tracks": [
                self.track_payload(track) | {"analysis_status": track.get("analysis_status") or "not_analyzed"}
                for track in tracks
            ],
            "genres": dict(sorted(genres.items())),
            "detailed_genres": dict(sorted(facets.get("detailed_genres", {}).items())),
            "detailed_genres_by_category": facets.get("detailed_genres_by_category", {}),
            "playlists": dict(sorted(playlists.items())),
            "review_states": facets.get("review_states", {}),
            "pagination": {
                "page": page,
                "page_size": query.page_size,
                "filtered_total": filtered_total,
                "analyzable_total": analyzable_total,
                "catalog_total": facets["total"],
                "total_pages": total_pages,
            },
        }

    @staticmethod
    def _page(repository: Any, query: DownloadedCatalogQuery, page: int) -> tuple[list[dict[str, Any]], int]:
        return repository.page_downloaded_tracks(
            page=page,
            page_size=query.page_size,
            search=query.search,
            genre=query.genre,
            detailed_genre=query.detailed_genre,
            playlist=query.playlist,
            analysis=query.analysis,
            artwork=query.artwork,
            quality=query.quality,
            sort=query.sort,
        )
