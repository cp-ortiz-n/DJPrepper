---
type: "architecture"
date: "2026-09-30T17:08:35.872475+00:00"
question: "Extract the authorized YouTube and SoundCloud importer from web_app.py, centralize import state and routing, and prevent imports from silently recreating a disconnected external-library path."
contributor: "graphify"
outcome: "useful"
source_nodes: ["helpers/import_service.py,helpers/import_routes.py,web_app.py,tests/test_import_service.py,tests/test_web_app.py"]
---

# Q: Extract the authorized YouTube and SoundCloud importer from web_app.py, centralize import state and routing, and prevent imports from silently recreating a disconnected external-library path.

## Answer

Created helpers/import_service.py for provider detection, scdl/yt-dlp execution, cancellation, state, temp lifecycle, catalog writes, and queue handoff; created helpers/import_routes.py for the authorized import API; composed the service in web_app.py; removed the duplicate inline worker/routes; added online-drive checks at start and immediately before final writes, and extended guardrails to Creative Commons and local-audio imports; added regression tests for offline roots and centralized lifecycle state. Full 183-test suite, JS syntax check, and dependency check pass.

## Outcome

- Signal: useful

## Source Nodes

- helpers/import_service.py,helpers/import_routes.py,web_app.py,tests/test_import_service.py,tests/test_web_app.py