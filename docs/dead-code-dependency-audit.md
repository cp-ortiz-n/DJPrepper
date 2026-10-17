# Dead-code and dependency audit

Audit date: 2026-10-15. Scope: `audioextender/` for dead-code analysis and the
full Python workspace for import/dependency comparison. The audit is diagnostic;
its heuristic output is not an automatic deletion list.

## Commands

```sh
.venv/bin/vulture audioextender --min-confidence 60
.venv/bin/vulture audioextender --min-confidence 80
.venv/bin/pipreqs . --print --force \
  --pypi-server https://pypi.org/pypi/ \
  --ignore .venv,.venv-intel-backup,input,output,cache,graphify-out
.venv/bin/python -m pip check
.venv/bin/pipdeptree --warn fail
```

## Vulture results

Vulture reported 205 candidates at 60% confidence and zero candidates at 80%
confidence. The 60% results were concentrated in dynamically registered or
framework-owned surfaces:

| Package | Candidates |
| --- | ---: |
| `web` | 144 |
| `infrastructure` | 14 |
| `imports` | 12 |
| `analysis` | 7 |
| `core` | 7 |
| `processing` | 6 |
| `audio` | 5 |
| `set_builder` | 5 |
| `repositories` | 3 |
| `library` | 2 |

FastAPI route functions, Pydantic fields and validators, dataclass/protocol
members, callback entry points, and functions used by top-level scripts or tests
account for most findings. Examples confirmed as live include
`ConfigFactory.from_arguments`, `clear_cache`, `NullProgressReporter`,
`RepositoryConcurrencyProbe`, `SetPlanningEvaluationHarness`, and
`assess_ai_release`. They must not be removed based on Vulture alone.

The following 60%-confidence symbols have no repository references outside their
definitions and are candidates for focused characterization/removal work:

- `AnalysisError`
- `analysis.key_detection.analyze_key`
- `analysis.section_selector.select_section`
- `processing.extended_edit._choose_splice_mode`
- `processing.track_processor._format_duration`
- `processing.track_processor._print_candidate`
- `processing.web_jobs.default_job_values`
- `JobRepository.update_downloaded_track_key_analysis`

These remain in place because this audit does not prove that external consumers,
serialized callbacks, or compatibility imports do not use them. Remove them only
in a focused change with import, API, and behavior tests.

## Focused reassessment

The follow-up compatibility pass separated the candidates by visibility and
observable behavior:

- Removed the unreferenced private helpers
  `processing.extended_edit._choose_splice_mode`,
  `processing.track_processor._format_duration`,
  `processing.track_processor._print_candidate`, and
  `processing.web_jobs.default_job_values`.
- Preserved `AnalysisError` as part of the expected application exception
  hierarchy.
- Preserved `analyze_key` as the public key-only analysis boundary and locked
  down its `KeyAnalysis` result contract.
- Preserved `select_section` as the single-result compatibility adapter over
  ranked section selection.
- Preserved `update_downloaded_track_key_analysis` as the key-only catalog write
  boundary; its test proves unrelated catalog fields survive the update.

`tests/unit/architecture/test_dead_code_compatibility.py` characterizes all eight decisions and
prevents the removed private helpers from quietly returning.

## Dependency results

`pip check` and `pipdeptree --warn fail` found no installed dependency conflicts.
Pipreqs identified direct imports for Certifi, FastAPI, HTTPX, Librosa, Mutagen,
NumPy, Pydantic, SciPy, SoundFile, Starlette, Torch, Uvicorn, and yt-dlp.

The checked-in requirement groups intentionally differ from that heuristic list:

- `torch` is supplied by the optional `requirements-demucs.txt` path.
- `python-multipart` is a FastAPI runtime requirement triggered by form routes,
  even though application code does not import its module directly.
- `scdl` is invoked as an external command and is therefore invisible to an
  import scanner.
- Pydantic and Starlette are imported directly but constrained transitively by
  FastAPI. Splitting them into explicit top-level constraints is a future
  packaging-policy decision, not an automatic audit fix.
- HTTPX is imported directly by application and test code. The audit found that
  the existing environment supplied it only through optional Demucs, so it is
  now an explicit runtime requirement rather than relying on that accidental
  transitive dependency.

Pipreqs resolves current PyPI versions and does not understand these optional,
command-line, or framework relationships. Its generated list must not replace
`requirements.txt` automatically.
