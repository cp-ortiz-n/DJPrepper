# Track processing compatibility contract

`TrackProcessor.process` is the public transaction boundary for one source
track. ARCH-002A froze its observable behavior; ARCH-002B introduced typed stage
values. The transaction now delegates analysis preparation, candidate-selection
orchestration, render/export, result construction, and failure cleanup to
focused collaborators without changing that contract. The characterization suite lives in
`tests/unit/processing/test_track_processor_characterization.py`.

## Stage order and progress

The full-edit path currently performs these responsibilities in order:

1. load source audio;
2. load or calculate track analysis;
3. acquire optional vocal and instrumental stem analysis;
4. select the intro, then the outro;
5. optimize and validate both candidates;
6. assemble the extended edit;
7. export requested artifacts;
8. assemble `FileResult`.

Stable top-level progress checkpoints are `0` (loading), `8` (analysis start),
`80` (intro scoring), `85` (outro scoring), `88` (boundary optimization), and
`90` (edit assembly). Fresh analysis maps its internal fractional progress into
the 8–70 range. A cache hit reports `70` with `Loaded cached track analysis`.
Export progress from 94 onward belongs to `ExportService`.

`stage_timings` records loading, individual fresh-analysis labels, vocal/stem
analysis, and a final `Total`. `FileResult.elapsed` is sampled immediately before
result assembly; `Total` is sampled once afterward and may therefore be slightly
larger. Cached analysis replaces detailed analysis timings with the cache-hit
progress event.

## Cache contract

- A normal cache miss calculates and saves analysis when caching is enabled.
- A subsequent matching source/configuration revision reports
  `analysis_cache_hit=True` and does not call the analyzer.
- `refresh_cache=True` bypasses the read, recalculates analysis, and replaces the
  saved value.
- `vocal_cache_hit` is reported independently by the stem provider.
- Analysis-only processing returns the source path as both `output` and
  `wav_output` and creates no edit artifacts.

## Artifact and failure contract

The export service owns the extended WAV, source WAV, previews, and cue sheet.
`FileResult` exposes the paths and `full_exported` state returned by that service.
The processor must not fabricate artifact paths from a failed export.

Any exception after progress starts is sent to `ProcessingFailureCleanup`, which
calls `ProgressReporter.stop()` exactly once, and is re-raised unchanged. A
failed loading, analysis, stem, selection, or render stage must not invoke
export. Cleanup internal to stem separation and export remains owned by those
services.

## Safe refactoring rule

The typed analysis, selection, render, export, and result stage values retain
this public method signature, stage ordering,
progress behavior, cache semantics, artifacts, and failure propagation unless a
separate intentional compatibility change updates this contract first.
