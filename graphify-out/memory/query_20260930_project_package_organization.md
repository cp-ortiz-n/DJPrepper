---
type: "architecture"
date: "2026-09-30T18:30:00-05:00"
question: "Organize project files so application functions no longer live in a flat helpers folder."
contributor: "graphify"
outcome: "useful"
source_nodes: ["audioextender/core", "audioextender/audio", "audioextender/analysis", "audioextender/processing", "audioextender/library", "audioextender/imports", "audioextender/repositories", "audioextender/infrastructure", "audioextender/reporting"]
---

# Q: Organize project files so application functions no longer live in a flat helpers folder.

## Answer

Replaced the flat `helpers` package with the domain-owned `audioextender` package. Application
modules now live under core, audio, analysis, processing, library, imports, repositories,
infrastructure, and reporting. Updated application, script, and test imports; documented the
dependency direction; and added a structure test that prevents legacy helper modules from
returning. The public repository facade remains intact as `audioextender.repositories.facade`.

## Outcome

- Signal: useful

## Source Nodes

- audioextender/core
- audioextender/audio
- audioextender/analysis
- audioextender/processing
- audioextender/library
- audioextender/imports
- audioextender/repositories
- audioextender/infrastructure
- audioextender/reporting
