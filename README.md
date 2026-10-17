# DJ Library Studio

DJ Library Studio is a local macOS workspace for importing and organizing music,
analyzing BPM, beat grids, key, structure, energy, timing, cues, and track
compatibility, and creating DJ-friendly extended WAV edits. Its Set Builder can
turn a musical brief into a validated, catalog-backed running order using local
rules or optional local AI. The original AudioExtender command-line workflow
remains supported.

Audio and catalog data stay on the machine unless an optional remote AI provider
is explicitly configured. Local Ollama planning receives text and bounded
catalog metadata, never audio.

## Requirements

- macOS 12 or newer recommended
- Python 3.12
- Node.js 22 for frontend development and tests
- FFmpeg for broad audio decoding and WAV metadata support
- enough free disk space for uncompressed stereo WAV files
- optional: Ollama with `qwen3.5:4b` for local Set Builder interpretation and
  planning

Install the system dependencies with Homebrew if needed:

```sh
brew install python@3.12 ffmpeg
```

## Install

Create an isolated environment and install the application and frontend
dependencies:

```sh
cd /Users/cortizn/Documents/LocalScripts/AudioExtender
python3.12 -m venv .venv
.venv/bin/python -m pip install --upgrade pip
.venv/bin/python -m pip install -r requirements.txt
npm install
```

For development, install the complete pinned toolchain instead:

```sh
.venv/bin/python -m pip install -r requirements-dev.txt
npm ci
```

## Start the application

From the repository root:

```sh
.venv/bin/python web_app.py
```

Then open [http://localhost:8765](http://localhost:8765).

On macOS, you can instead double-click `Start AudioExtender.command`. The
launcher can start Ollama, prepare the configured local model, start the web
application, and open the browser. Closing the browser does not cancel running
jobs; closing the server process does.

## Basic workflows

### Import and analyze music

Use **Music Files** to add local audio or supported playlist sources. The
processing queue reports progress and persists across browser refreshes. Review
analysis, artwork, genres, musical identity, and generated extended edits before
committing changes.

### Maintain the DJ library

Use **DJ Library** to search, filter, preview, edit metadata and musical
identity, synchronize WAV tags, and reconcile files. The shared preview
controller ensures only one audio preview plays at a time.

If the library lives on an external drive, reconnect it and run
**Settings → Library health → Verify library** before attempting writes. The
application does not silently redirect imports to a temporary folder.

### Build a set

Use **Set Builder** to define duration, genres, energy, context, must-play or
excluded tracks, and an optional natural-language intention. Choose among:

- **AI Planned** — a configured model selects from a bounded real-catalog
  shortlist;
- **AI Interpreted** — AI structures the brief while deterministic rules choose
  tracks; or
- **Classic** — local deterministic planning only.

Every proposal is validated against real catalog IDs, file availability,
duplicates, exclusions, required tracks, duration, genre and journey coverage,
and transition constraints. Invalid or unavailable AI results fall back to a
validated deterministic plan.

### Create an extended edit

The command-line workflow remains available for direct processing:

```sh
.venv/bin/python main.py input/song.mp3
```

Run `.venv/bin/python main.py --help` for profiles, track overrides, candidate
review, cue export, and output options.

## Optional local AI

Install and prepare the recommended model:

```sh
brew install --cask ollama-app
open -a Ollama
ollama pull qwen3.5:4b
```

Set Builder remains usable when Ollama is stopped. Its planning receipt records
which provider and model ran, validation and repair results, quality comparison,
and any deterministic fallback. Full provider configuration and privacy details
are in the [user guide](docs/user-guide.md#optional-local-ai-for-set-builder).

## Documentation

- [User guide](docs/user-guide.md) — application features, detailed workflows,
  CLI commands, profiles, reports, cues, Demucs, and troubleshooting context
- [Operator guide](docs/operator-guide.md) — startup, external-drive recovery,
  background operations, health checks, backups, and safe workspace cleanup
- [Developer guide](docs/developer-guide.md) — repository layout, configuration,
  ownership boundaries, tests, coverage, and generated artifacts
- [Contributing](CONTRIBUTING.md) — supported toolchain and change workflow
- [Architecture](docs/architecture.md) — authoritative module ownership and
  dependency rules
- [Repository map](docs/repository-map.md) — source and test navigation
- [Architecture decisions](docs/decisions/README.md) — compatibility-sensitive
  decisions and their rationale
- [Backlog](BACKLOG.md) — planned work

## Development checks

Use the repository entry points instead of assembling ad hoc commands:

```sh
make quality
make stability
make browser
make coverage
```

See the [developer guide](docs/developer-guide.md#automated-tests) for focused
commands and gate responsibilities.

## License

This project is licensed under the terms in [LICENSE](LICENSE).
