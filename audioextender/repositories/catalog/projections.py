from __future__ import annotations

from contextlib import closing
from typing import Any

from audioextender.repositories.base import RepositoryMixinBase


class TrackProjectionRepositoryMixin(RepositoryMixinBase):
    def list_downloaded_tracks_with_jobs(self) -> list[dict[str, Any]]:
        """Return the catalog with latest job state resolved inside SQLite."""
        with closing(self._connect()) as connection:
            rows = connection.execute(
                """
                    WITH latest_any AS (
                        SELECT source_path, MAX(id) AS job_id
                        FROM jobs GROUP BY source_path
                    ), latest_complete AS (
                        SELECT source_path, MAX(id) AS job_id
                        FROM jobs WHERE status = 'complete' GROUP BY source_path
                    )
                    SELECT tracks.*,
                        GROUP_CONCAT(playlists.playlist_name, '||') AS playlists,
                        (SELECT json_group_array(json_object(
                            'category', descriptors.category, 'value', descriptors.value,
                            'provenance', descriptors.provenance,
                            'confidence', descriptors.confidence,
                            'updated_at', descriptors.updated_at))
                         FROM downloaded_track_descriptors descriptors
                         WHERE descriptors.track_id=tracks.id) AS descriptors_json,
                        latest_job.status AS analysis_status,
                        latest_job.id AS library_job_id,
                        completed_job.id AS completed_library_job_id
                    FROM downloaded_tracks AS tracks
                    LEFT JOIN downloaded_track_playlists AS playlists
                        ON playlists.track_id = tracks.id
                    LEFT JOIN latest_any
                        ON latest_any.source_path = tracks.file_path
                    LEFT JOIN jobs AS latest_job
                        ON latest_job.id = latest_any.job_id
                    LEFT JOIN latest_complete
                        ON latest_complete.source_path = tracks.file_path
                    LEFT JOIN jobs AS completed_job
                        ON completed_job.id = latest_complete.job_id
                    GROUP BY tracks.id
                    ORDER BY tracks.imported_at DESC, tracks.id DESC
                    """
            ).fetchall()
        results = []
        for row in rows:
            item = dict(row)
            item["playlists"] = [value for value in str(item.get("playlists") or "").split("||") if value]
            results.append(item)
        return results

    def page_downloaded_tracks(
        self,
        *,
        page: int,
        page_size: int,
        search: str = "",
        genre: str = "all",
        playlist: str = "all",
        detailed_genre: str = "all",
        analysis: str = "all",
        artwork: str = "all",
        quality: str = "all",
        sort: str = "newest",
    ) -> tuple[list[dict[str, Any]], int]:
        """Filter, sort, and page the downloaded catalog entirely in SQLite."""
        conditions: list[str] = []
        parameters: list[Any] = []
        if search.strip():
            value = f"%{search.strip().casefold()}%"
            conditions.append(
                "(LOWER(tracks.title) LIKE ? OR LOWER(tracks.artist) LIKE ? "
                "OR LOWER(tracks.genre) LIKE ? OR LOWER(tracks.genre_category) LIKE ? "
                "OR LOWER(tracks.recording_code || '-' || tracks.version_code) LIKE ? "
                "OR EXISTS (SELECT 1 FROM downloaded_track_playlists search_playlist "
                "WHERE search_playlist.track_id = tracks.id "
                "AND LOWER(search_playlist.playlist_name) LIKE ?) "
                "OR EXISTS (SELECT 1 FROM downloaded_track_descriptors search_descriptor "
                "WHERE search_descriptor.track_id = tracks.id AND LOWER(search_descriptor.value) LIKE ?))"
            )
            parameters.extend([value] * 7)
        missing_title = (
            "TRIM(COALESCE(tracks.title, '')) = '' OR LOWER(TRIM(tracks.title)) IN ('unknown title','untitled')"
        )
        missing_artist = (
            "TRIM(COALESCE(tracks.artist, '')) = '' OR "
            "LOWER(TRIM(tracks.artist)) IN ('unknown artist','unknown','unavailable')"
        )
        missing_genre = "TRIM(COALESCE(tracks.genre, '')) = ''"
        missing_artwork = "TRIM(COALESCE(tracks.artwork_path, '')) = ''"
        unmapped_genre = "TRIM(COALESCE(tracks.genre, '')) != '' AND tracks.genre_category = 'Other'"
        broad_genre = "(tracks.genre_category LIKE '% / General' OR tracks.genre_category LIKE '% / Other')"
        if genre != "all":
            aliases = {
                "Electronic / General": "Electronic / Electronic / Electronic",
                "Latin / General": "Latin / Other",
            }
            stored_genre = aliases.get(genre, genre)
            conditions.append("(tracks.genre_category = ? OR tracks.genre_category LIKE ? ESCAPE '\\')")
            escaped = stored_genre.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
            parameters.extend((stored_genre, f"{escaped} / %"))
        if detailed_genre != "all":
            # Source genres are stored as comma-separated tags. Pad both sides
            # with commas so selecting "house" cannot also match "deep house".
            normalized_tag = detailed_genre.strip().casefold()
            conditions.append(
                "(',' || REPLACE(REPLACE(LOWER(COALESCE(tracks.genre, '')), ', ', ','), ' ,', ',') || ',') LIKE ?"
            )
            parameters.append(f"%,{normalized_tag},%")
        if playlist != "all":
            conditions.append(
                "EXISTS (SELECT 1 FROM downloaded_track_playlists selected_playlist "
                "WHERE selected_playlist.track_id = tracks.id "
                "AND selected_playlist.playlist_name = ?)"
            )
            parameters.append(playlist)
        status = "COALESCE(latest_job.status, 'not_analyzed')"
        analysis_conditions = {
            "needs": f"{status} IN ('not_analyzed','failed','canceled')",
            "complete": f"{status} = 'complete'",
            "active": f"{status} IN ('queued','processing')",
            "failed": f"{status} IN ('failed','canceled')",
            "attention": (
                f"({missing_title} OR {missing_artist} OR {missing_genre} OR "
                f"{missing_artwork} OR {unmapped_genre} OR {broad_genre})"
            ),
            "missing_title": f"({missing_title})",
            "missing_artist": f"({missing_artist})",
            "missing_genre": f"({missing_genre})",
            "missing_artwork": f"({missing_artwork})",
            "unmapped_genre": f"({unmapped_genre})",
            "broad_genre": f"({broad_genre})",
        }
        if analysis in analysis_conditions:
            conditions.append(analysis_conditions[analysis])
        if artwork == "missing":
            conditions.append("TRIM(COALESCE(tracks.artwork_path, '')) = ''")
        elif artwork == "available":
            conditions.append("TRIM(COALESCE(tracks.artwork_path, '')) != ''")
        quality_conditions = {
            "excellent": "tracks.audio_quality_label = 'excellent'",
            "good": "tracks.audio_quality_label = 'good'",
            "review": "tracks.audio_quality_label = 'review'",
            "poor": "tracks.audio_quality_label = 'poor'",
            "below-target": "tracks.audio_quality_label IN ('review','poor')",
            "unanalyzed": "tracks.audio_quality_score IS NULL",
        }
        if quality in quality_conditions:
            conditions.append(quality_conditions[quality])
        where = f"WHERE {' AND '.join(conditions)}" if conditions else ""
        order = {
            "newest": "tracks.imported_at DESC, tracks.id DESC",
            "title": "tracks.title COLLATE NOCASE, tracks.id",
            "artist": "tracks.artist COLLATE NOCASE, tracks.title COLLATE NOCASE",
            "genre": "tracks.genre_category COLLATE NOCASE, tracks.artist COLLATE NOCASE",
        }.get(sort, "tracks.imported_at DESC, tracks.id DESC")
        ctes = """WITH latest_any AS (
                SELECT source_path, MAX(id) AS job_id FROM jobs GROUP BY source_path
            ), latest_complete AS (
                SELECT source_path, MAX(id) AS job_id FROM jobs
                WHERE status = 'complete' GROUP BY source_path
            )"""
        joins = """FROM downloaded_tracks AS tracks
                LEFT JOIN latest_any ON latest_any.source_path = tracks.file_path
                LEFT JOIN jobs AS latest_job ON latest_job.id = latest_any.job_id
                LEFT JOIN latest_complete ON latest_complete.source_path = tracks.file_path
                LEFT JOIN jobs AS completed_job ON completed_job.id = latest_complete.job_id"""
        with closing(self._connect()) as connection:
            total = int(connection.execute(f"{ctes} SELECT COUNT(*) {joins} {where}", parameters).fetchone()[0])
            rows = connection.execute(
                f"""{ctes} SELECT tracks.id, tracks.title, tracks.artist,
                    tracks.filename, tracks.genre, tracks.genre_category,
                    tracks.recording_code, tracks.version_code,
                    tracks.identity_confidence, tracks.identity_reason,
                    tracks.identity_inference_locked,
                    tracks.audio_quality_score, tracks.audio_quality_label,
                    tracks.audio_quality_json, tracks.audio_quality_analyzed_at,
                    tracks.artwork_url, tracks.artwork_path, tracks.file_path,
                    tracks.duration_seconds, tracks.imported_at,
                    (SELECT json_group_array(json_object(
                        'category', descriptors.category, 'value', descriptors.value,
                        'provenance', descriptors.provenance,
                        'confidence', descriptors.confidence,
                        'updated_at', descriptors.updated_at))
                     FROM downloaded_track_descriptors descriptors
                     WHERE descriptors.track_id=tracks.id) AS descriptors_json,
                    (SELECT GROUP_CONCAT(p.playlist_name, '||')
                     FROM downloaded_track_playlists p WHERE p.track_id = tracks.id) AS playlists,
                    latest_job.status AS analysis_status,
                    latest_job.id AS library_job_id,
                    completed_job.id AS completed_library_job_id
                    {joins} {where} ORDER BY {order} LIMIT ? OFFSET ?""",
                (*parameters, page_size, (page - 1) * page_size),
            ).fetchall()
        results = []
        for row in rows:
            item = dict(row)
            item["playlists"] = [value for value in str(item.get("playlists") or "").split("||") if value]
            results.append(item)
        return results, total

    def downloaded_catalog_facets(self) -> dict[str, Any]:
        with closing(self._connect()) as connection:
            total = int(connection.execute("SELECT COUNT(*) FROM downloaded_tracks").fetchone()[0])
            genres = dict(
                connection.execute(
                    "SELECT genre_category, COUNT(*) FROM downloaded_tracks GROUP BY genre_category"
                ).fetchall()
            )
            playlists = dict(
                connection.execute(
                    "SELECT playlist_name, COUNT(*) FROM downloaded_track_playlists GROUP BY playlist_name"
                ).fetchall()
            )
            detailed_genres: dict[str, int] = {}
            detailed_genres_by_category: dict[str, dict[str, int]] = {}
            canonical_tags: dict[str, str] = {}
            for category, raw_genres in connection.execute(
                "SELECT genre_category, genre FROM downloaded_tracks WHERE TRIM(COALESCE(genre, '')) != ''"
            ).fetchall():
                category_genres = detailed_genres_by_category.setdefault(str(category or "Other"), {})
                seen: set[str] = set()
                for raw_tag in str(raw_genres or "").split(","):
                    tag = raw_tag.strip()
                    key = tag.casefold()
                    if not tag or key in seen:
                        continue
                    seen.add(key)
                    display = canonical_tags.setdefault(key, tag)
                    detailed_genres[display] = detailed_genres.get(display, 0) + 1
                    category_genres[display] = category_genres.get(display, 0) + 1
            issue_conditions = {
                "missing_title": "TRIM(COALESCE(title, '')) = '' OR LOWER(TRIM(title)) IN ('unknown title','untitled')",
                "missing_artist": (
                    "TRIM(COALESCE(artist, '')) = '' OR "
                    "LOWER(TRIM(artist)) IN ('unknown artist','unknown','unavailable')"
                ),
                "missing_genre": "TRIM(COALESCE(genre, '')) = ''",
                "missing_artwork": "TRIM(COALESCE(artwork_path, '')) = ''",
                "unmapped_genre": "TRIM(COALESCE(genre, '')) != '' AND genre_category = 'Other'",
                "broad_genre": "genre_category LIKE '% / General' OR genre_category LIKE '% / Other'",
            }
            review_states = {
                name: int(connection.execute(f"SELECT COUNT(*) FROM downloaded_tracks WHERE {condition}").fetchone()[0])
                for name, condition in issue_conditions.items()
            }
            review_states["needs_attention"] = int(
                connection.execute(
                    "SELECT COUNT(*) FROM downloaded_tracks WHERE "
                    + " OR ".join(f"({condition})" for condition in issue_conditions.values())
                ).fetchone()[0]
            )
        return {
            "total": total,
            "genres": genres,
            "detailed_genres": detailed_genres,
            "detailed_genres_by_category": detailed_genres_by_category,
            "playlists": playlists,
            "review_states": review_states,
        }
