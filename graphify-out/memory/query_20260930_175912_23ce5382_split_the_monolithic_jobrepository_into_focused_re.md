---
type: "architecture"
date: "2026-09-30T17:59:12.577999+00:00"
question: "Split the monolithic JobRepository into focused repository domains without breaking existing callers."
contributor: "graphify"
outcome: "useful"
source_nodes: ["helpers/web_database.py,helpers/repositories/base.py,helpers/repositories/system_state.py,helpers/repositories/jobs.py,helpers/repositories/library_analysis.py,helpers/repositories/feedback.py,helpers/repositories/track_catalog.py"]
---

# Q: Split the monolithic JobRepository into focused repository domains without breaking existing callers.

## Answer

Reduced helpers/web_database.py from 2,079 lines to a 461-line compatibility facade that owns schema initialization and SQLite connections. Moved operations into SystemStateRepositoryMixin, JobQueueRepositoryMixin, LibraryAnalysisRepositoryMixin, FeedbackRepositoryMixin, and TrackCatalogRepositoryMixin under helpers/repositories, with a shared structural base. Preserved the JobRepository public API and database schema. Ruff and mypy pass for all repository modules; 187 Python tests and JavaScript checks pass.

## Outcome

- Signal: useful

## Source Nodes

- helpers/web_database.py,helpers/repositories/base.py,helpers/repositories/system_state.py,helpers/repositories/jobs.py,helpers/repositories/library_analysis.py,helpers/repositories/feedback.py,helpers/repositories/track_catalog.py