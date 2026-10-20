"""Creative Commons delivery and import-issue HTTP workflows."""

from __future__ import annotations

import json
import tempfile
import zipfile
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field
from starlette.background import BackgroundTask

from audioextender.imports.creative_commons import CreativeCommonsImportService


class CreativeCommonsMatch(BaseModel):
    url: str = Field(min_length=10, max_length=500)
    title: str = Field(min_length=1, max_length=300)
    artist: str = Field(min_length=1, max_length=300)
    spotify_uri: str = Field(default="", max_length=200)
    genre: str = Field(default="", max_length=500)
    genre_category: str = Field(default="Other", max_length=80)
    artwork_url: str = Field(default="", max_length=1000)
    playlist_name: str = Field(default="", max_length=180)


class CreativeCommonsBatchRequest(BaseModel):
    tracks: list[CreativeCommonsMatch] = Field(min_length=1, max_length=500)
    playlist_name: str = Field(default="Imported Playlist", min_length=1, max_length=180)


class ImportFailureRetryRequest(BaseModel):
    failure_ids: list[int] = Field(min_length=1, max_length=500)


@dataclass(frozen=True)
class CreativeCommonsArchiveDependencies:
    lifecycle: CreativeCommonsImportService
    music_library_root: Callable[[], Path]
    safe_folder_name: Callable[[str], str]
    genre_path_parts: Callable[[str], Sequence[str]]
    cataloged_download: Callable[[str], dict[str, Any] | None]


class CreativeCommonsArchiveService:
    """Resolve transient import results into downloadable reports and WAV archives."""

    def __init__(self, dependencies: CreativeCommonsArchiveDependencies) -> None:
        self.dependencies = dependencies

    def wav_archive(self, batch_id: str) -> tuple[Path, str]:
        try:
            state = self.dependencies.lifecycle.status(batch_id, private=True)
        except LookupError as error:
            raise HTTPException(404, str(error)) from error
        playlist_name = str(state.get("playlist_name") or "Imported Playlist")
        report_data = dict(state.get("report") or {})
        included = list(report_data.get("downloaded") or []) + list(report_data.get("already_downloaded") or [])
        if not included:
            raise HTTPException(404, "No verified Creative Commons WAV files are available")

        safe_playlist = self.dependencies.safe_folder_name(playlist_name)
        temporary = tempfile.NamedTemporaryFile(prefix=f"{safe_playlist}-", suffix="-WAVs.zip", delete=False)
        temporary.close()
        path = Path(temporary.name)
        added = 0
        try:
            with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as archive:
                for item in included:
                    category = str(item.get("genre_category") or "Other")
                    catalog_track = self.dependencies.cataloged_download(str(item.get("youtube_id") or ""))
                    source = (
                        Path(str(catalog_track.get("file_path")))
                        if catalog_track
                        else self.dependencies.music_library_root().joinpath(
                            *self.dependencies.genre_path_parts(category),
                            str(item.get("filename") or ""),
                        )
                    )
                    if catalog_track:
                        category = str(catalog_track.get("genre_category") or category)
                    if not source.is_file():
                        continue
                    category_path = "/".join(self.dependencies.genre_path_parts(category))
                    archive.write(source, arcname=f"{safe_playlist}/{category_path}/{source.name}")
                    added += 1
            if not added:
                path.unlink(missing_ok=True)
                raise HTTPException(404, "The imported WAV files are no longer available")
            return path, f"{safe_playlist} - WAVs.zip"
        except Exception:
            path.unlink(missing_ok=True)
            raise

    def report(self, batch_id: str) -> tuple[Path, str]:
        try:
            state = self.dependencies.lifecycle.status(batch_id, private=True)
        except LookupError as error:
            raise HTTPException(404, str(error)) from error
        path = Path(str(state.get("report_path") or ""))
        if not path.is_file():
            raise HTTPException(404, "Creative Commons import report is not available")
        playlist_name = self.dependencies.safe_folder_name(str(state.get("playlist_name") or "Imported Playlist"))
        return path, f"{playlist_name} - Import Report.json"


@dataclass(frozen=True)
class ImportIssueDependencies:
    repository: Callable[[], Any]
    lifecycle: Callable[[], CreativeCommonsImportService]
    report_root: Path
    safe_folder_name: Callable[[str], str]
    generalized_genre: Callable[[str], str]
    normalize_genre: Callable[[str], str]


class ImportIssueService:
    """Own failed-import discovery, retry selection, dismissal, and report lookup."""

    def __init__(self, dependencies: ImportIssueDependencies) -> None:
        self.dependencies = dependencies

    @property
    def repository(self) -> Any:
        return self.dependencies.repository()

    def list(self) -> dict[str, Any]:
        if not self.repository.list_import_failures(include_resolved=True):
            self._backfill_reports()
        failures = self.repository.list_import_failures()
        return {"failures": failures, "total": len(failures)}

    def retry(self, failure_ids: Sequence[int]) -> dict[str, Any]:
        wanted = set(failure_ids)
        failures = [item for item in self.repository.list_import_failures() if int(item["id"]) in wanted]
        if len(failures) != len(wanted):
            raise HTTPException(404, "One or more import issues are no longer available")
        return self.dependencies.lifecycle().start_retry(failures)

    def dismiss(self, failure_id: int) -> dict[str, Any]:
        failures = self.repository.list_import_failures(include_resolved=True)
        failure = next((item for item in failures if int(item["id"]) == failure_id), None)
        if failure is None:
            raise HTTPException(404, "Import failure not found")
        self.repository.resolve_import_failure(
            playlist_name=str(failure["playlist_name"]),
            title=str(failure["title"]),
            artist=str(failure["artist"]),
        )
        return {"resolved": True, "id": failure_id}

    def original_metadata(self, playlist_name: str, title: str, artist: str) -> dict[str, str]:
        """Recover source metadata from the first playlist report for a failed track."""
        wanted_title = title.strip().casefold()
        wanted_artist = artist.strip().casefold()
        preferred = self.dependencies.report_root / self.dependencies.safe_folder_name(playlist_name)
        candidates = [*preferred.glob("*Import Report.json")]
        candidates.extend(
            path
            for path in self.dependencies.report_root.glob("**/*Import Report.json")
            if path.parent != preferred and path.parent.name != "Retry imports"
        )
        for report_path in candidates:
            try:
                document = json.loads(report_path.read_text(encoding="utf-8"))
            except (OSError, ValueError):
                continue
            for section in ("failed", "downloaded", "already_downloaded"):
                for item in (document.get("results") or {}).get(section, []):
                    if (
                        str(item.get("title") or "").strip().casefold() == wanted_title
                        and str(item.get("artist") or "").strip().casefold() == wanted_artist
                    ):
                        genre = str(item.get("genre") or "").strip()
                        category = str(item.get("genre_category") or "").strip()
                        return {
                            "genre": genre,
                            "genre_category": (
                                self.dependencies.generalized_genre(genre)
                                if genre
                                else self.dependencies.normalize_genre(category or "Other")
                            ),
                        }
        return {"genre": "", "genre_category": "Other"}

    def _backfill_reports(self) -> None:
        for report_path in self.dependencies.report_root.glob("**/*Import Report.json"):
            try:
                document = json.loads(report_path.read_text(encoding="utf-8"))
            except (OSError, ValueError):
                continue
            playlist_name = str(document.get("playlist_name") or report_path.parent.name)
            for item in (document.get("results") or {}).get("failed", []):
                self.repository.record_import_failure(
                    playlist_name=playlist_name,
                    title=str(item.get("title") or item.get("filename") or "Unknown track"),
                    artist=str(item.get("artist") or ""),
                    spotify_uri=str(item.get("spotify_uri") or ""),
                    youtube_url=str(item.get("url") or item.get("youtube_url") or ""),
                    error=str(item.get("error") or "Download failed"),
                )


def create_creative_commons_router(
    lifecycle: CreativeCommonsImportService,
    archives: CreativeCommonsArchiveService,
    issues: ImportIssueService,
) -> APIRouter:
    router = APIRouter(prefix="/api/imports", tags=["imports"])

    @router.post("/creative-commons", status_code=202)
    def create_creative_commons_batch(request: CreativeCommonsBatchRequest) -> dict[str, Any]:
        try:
            return lifecycle.start(request.tracks, request.playlist_name)
        except ValueError as error:
            raise HTTPException(400, str(error)) from error

    @router.get("/creative-commons/{batch_id}")
    def creative_commons_batch_status(batch_id: str) -> dict[str, Any]:
        try:
            return lifecycle.status(batch_id)
        except LookupError as error:
            raise HTTPException(404, str(error)) from error

    @router.get("/creative-commons/{batch_id}/download")
    def download_creative_commons_batch(batch_id: str) -> FileResponse:
        path, filename = archives.wav_archive(batch_id)
        return FileResponse(path, filename=filename, background=BackgroundTask(path.unlink, missing_ok=True))

    @router.get("/creative-commons/{batch_id}/report")
    def download_creative_commons_report(batch_id: str) -> FileResponse:
        path, filename = archives.report(batch_id)
        return FileResponse(path, filename=filename)

    @router.get("/failures")
    def list_import_failures() -> dict[str, Any]:
        return issues.list()

    @router.post("/failures/retry", status_code=202)
    def retry_import_failures(request: ImportFailureRetryRequest) -> dict[str, Any]:
        return issues.retry(request.failure_ids)

    @router.delete("/failures/{failure_id}")
    def dismiss_import_failure(failure_id: int) -> dict[str, Any]:
        return issues.dismiss(failure_id)

    return router
