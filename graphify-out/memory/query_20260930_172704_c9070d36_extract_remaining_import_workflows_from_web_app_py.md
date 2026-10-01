---
type: "architecture"
date: "2026-09-30T17:27:04.428628+00:00"
question: "Extract remaining import workflows from web_app.py and make the bulk authorized import queue survive refreshes and external-drive reconnects."
contributor: "graphify"
outcome: "useful"
source_nodes: ["helpers/local_import_service.py,helpers/import_routes.py,helpers/import_service.py,web/import-queue.js,web/app.js,web_app.py,tests/import_queue.test.js"]
---

# Q: Extract remaining import workflows from web_app.py and make the bulk authorized import queue survive refreshes and external-drive reconnects.

## Answer

Extracted local audio staging/conversion/catalog persistence into helpers/local_import_service.py and registered its endpoints through helpers/import_routes.py. Added web/import-queue.js as a reusable persistent authorized-import queue that preserves order, pause state, failures, and active import IDs in localStorage; refreshes reconnect to existing backend imports rather than duplicating them; offline work pauses and can resume/retry after reconnect. Added Node behavior tests and retained the centralized external-drive guard. Full 183 Python tests and 2 JavaScript queue tests pass.

## Outcome

- Signal: useful

## Source Nodes

- helpers/local_import_service.py,helpers/import_routes.py,helpers/import_service.py,web/import-queue.js,web/app.js,web_app.py,tests/import_queue.test.js