---
type: "architecture"
date: "2026-09-30T17:44:31.251801+00:00"
question: "Extract the Creative Commons import lifecycle and introduce a persistent shared background-task registry."
contributor: "graphify"
outcome: "useful"
source_nodes: ["helpers/creative_commons_import_service.py,helpers/background_tasks.py,web_app.py,tests/test_background_tasks.py,tests/test_web_app.py"]
---

# Q: Extract the Creative Commons import lifecycle and introduce a persistent shared background-task registry.

## Answer

Added CreativeCommonsImportService for batch validation, start, retry, status, active detection, and cleanup. Added BackgroundTaskRegistry with thread-safe atomic JSON persistence and restart recovery that marks interrupted processing as retryable failure. Migrated Creative Commons batches to the registry while preserving existing worker, download, report, and failure APIs. Added persistence/restart tests and updated retry tests. Full 187 Python tests and JavaScript checks pass.

## Outcome

- Signal: useful

## Source Nodes

- helpers/creative_commons_import_service.py,helpers/background_tasks.py,web_app.py,tests/test_background_tasks.py,tests/test_web_app.py