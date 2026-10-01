---
type: "architecture"
date: "2026-09-30T17:32:04.491036+00:00"
question: "Continue decomposing all import workflows and make bulk queues durable across refresh and drive reconnects."
contributor: "graphify"
outcome: "useful"
source_nodes: ["helpers/import_routes.py,helpers/local_import_service.py,helpers/playlist_match_service.py,web/import-queue.js,web/app.js,web_app.py,tests/import_queue.test.js,tests/test_playlist_match_service.py"]
---

# Q: Continue decomposing all import workflows and make bulk queues durable across refresh and drive reconnects.

## Answer

Moved local-audio import staging, conversion, metadata/source record writing, catalog insertion, status, and cleanup into LocalAudioImportService. Moved playlist matching orchestration and state into PlaylistMatchService while keeping matching/scoring injected. Registered both through the imports router. Extracted the authorized bulk queue into a reusable browser module with localStorage persistence, ordering, pause/resume, cancel/retry, active-import reconnection, and online recovery. Added Python and Node behavior tests; 183 Python tests plus queue and playlist-service tests pass.

## Outcome

- Signal: useful

## Source Nodes

- helpers/import_routes.py,helpers/local_import_service.py,helpers/playlist_match_service.py,web/import-queue.js,web/app.js,web_app.py,tests/import_queue.test.js,tests/test_playlist_match_service.py