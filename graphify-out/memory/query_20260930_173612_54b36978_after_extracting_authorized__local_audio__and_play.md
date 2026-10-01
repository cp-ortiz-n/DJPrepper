---
type: "architecture"
date: "2026-09-30T17:36:12.698211+00:00"
question: "After extracting authorized, local-audio, and playlist import services, what backend cleanup should AudioExtender prioritize next?"
contributor: "graphify"
outcome: "useful"
source_nodes: ["web_app.py,helpers/web_database.py,helpers/web_jobs.py,helpers/import_service.py,helpers/local_import_service.py,helpers/playlist_match_service.py,helpers/library_relocation.py,helpers/library_backup.py"]
---

# Q: After extracting authorized, local-audio, and playlist import services, what backend cleanup should AudioExtender prioritize next?

## Answer

Prioritize CreativeCommonsImportService and retry/report routes; split JobRepository into domain repositories; replace numerous global batch dictionaries/locks with one persistent BackgroundTaskRegistry; split web_app.py's 112 routes into import, library, analysis, settings/storage, set-builder, and feedback routers; extract LibraryCatalogService/cache; isolate settings, backup, relocation, and storage services; unify audio quality, integrity, artwork, genre, WAV-tag, and key-analysis jobs behind one batch runner; then harden typed exceptions, dependency injection, API contracts, and service-level tests.

## Outcome

- Signal: useful

## Source Nodes

- web_app.py,helpers/web_database.py,helpers/web_jobs.py,helpers/import_service.py,helpers/local_import_service.py,helpers/playlist_match_service.py,helpers/library_relocation.py,helpers/library_backup.py