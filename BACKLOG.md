# AudioExtender Backlog

## Next work

- [x] **Extract downloaded-library metadata batch operations.** Move genre
  rescanning, WAV retagging, and artwork synchronization out of
  `audioextender/web/application.py` into focused services and routers. Preserve
  progress reporting, retry/error state, existing API contracts, and background
  batch behavior. Completed with a shared cancellable/retryable batch lifecycle,
  focused metadata routes, atomic mutation service, and relocation state parity.

## Implementation audit — September 21, 2026

Status definitions:

- **Complete** means the full backlog behavior is available in the current app.
- **Partial** means a useful foundation exists, but at least one requirement in
  the original item remains unfinished.
- Items not listed in this audit remain planned.

### Completed

- [x] **Manual waveform editor.** Review Queue supports custom intro/outro
  regions, draggable selection, exact timestamps, editable approximate bars,
  bar snapping, zoom, full-track and region playback, copies, source-to-output
  insertion, destination placement, and a rendered placement preview.
- [x] **Library Intelligence foundation.** DJ Library groups analyzed tracks by
  warm-up, peak-time, closing, vocal-safe, melodic, ambient, and live-timing
  roles and provides BPM/key-compatible track suggestions.
- [x] **Latest analysis overflow fix.** Long track names are bounded in the
  Process dashboard without pushing content outside the card.
- [x] **Process/DJ Library responsibility split.** Process is focused on batch
  configuration, active jobs, and recent status; collection discovery and
  set-planning filters live in DJ Library.
- [x] **Beginner-friendly mix-role explanations.** Every role explains its
  intended DJ use.
- [x] **Expandable role collections.** Role counts can reveal every matching
  track instead of limiting the user to three examples.
- [x] **Musical key and Camelot display.** DJ Library shows conventional and
  Camelot notation and remembers the selected display mode.
- [x] **Effective preset visibility.** The app distinguishes an `auto` request
  from the effective selected preset, and DJ Library can filter by the effective
  preset.
- [x] **DJ Library as a planning hub.** The page now combines analyzed-track
  browsing, DJ metadata, mix roles, compatibility, versions, downloads, genre
  editing, extension entry points, and set-planning filters.
- [x] **Initial Set Builder.** The app can generate an ordered set from genre,
  duration, BPM, energy curve, key strictness, vocal profile, timing, and edit
  preferences. Plans are explainable, manually reorderable, saveable, and
  exportable as CSV or M3U8.
- [x] **Required, excluded, locked, and alternate set tracks.** Set Builder
  preserves locked positions, supports required/excluded rules, and can replace
  a track with an unused alternative.
- [x] **Navigation terminology.** The primary workflow is consistently labeled
  Process, Import, Music Files, DJ Library, Set Builder, Review Queue, Analysis
  & Feedback, and Settings.
- [x] **Bulk collection interaction.** Music Files and DJ Library support
  select-all-visible, broad card-click selection, selected-row highlighting,
  bulk actions, and collapsible crate sidebars.
- [x] **Manual genre synchronization.** Genre changes move the WAV, survive
  refresh/rescan, and propagate to Music Files, DJ Library, filters, and Set
  Builder. Tracks with no genre metadata enter `Needs genre` instead of
  `Latin / Other`.

### Partially completed

- [~] **Feedback-informed candidate ranking.** Candidate feedback is captured,
  persisted, summarized in Analysis & Feedback, and protected from duplicate
  log entries. Candidate reranking is explainable and style-aware. Accepted and
  rejected feedback does not yet personalize future rankings, expose separate
  preference scores, enforce a learning threshold, or protect against
  preference overfitting.
- [~] **Preflight analysis mode.** Users can analyze without extending, request
  candidate review, inspect warnings/classifications, and open the custom
  editor before committing an edit. There is not yet one batch-level approval
  screen covering proposed presets, stems, bar lengths, candidates, and
  warnings before any audition rendering.
- [~] **Automatic A/B evaluation.** Source and edited audio have synchronized
  playback and feedback capture. The app does not yet create automatic,
  identical loudness-matched transition windows or store a direct A/B winner.
- [~] **Transition repair modes.** The processing engine has crossfade and
  compatibility-aware splice policies, including bass/timbre/tail safeguards.
  The complete selectable set of micro-crossfade, tail overlap, reverb, drum
  underlay, harmonic sustain, and progressive stem reconstruction is not
  available.
- [~] **DJ export profiles.** WAV bit depth, cue sheets, Rekordbox XML, preview
  exports, and grouped bulk downloads exist. Dedicated Serato, Engine DJ, and
  Traktor naming/cue/loop/metadata profiles remain unfinished.
- [~] **Compatibility explanations.** Match percentages expose tempo, harmonic
  key, energy, and shared-role components. Vocal density and timing behavior are
  not yet included in the displayed compatibility formula.
- [~] **Set-planning filters.** DJ Library supports search, BPM range, key,
  Camelot display, energy, role, genre, vocals, timing, extension result,
  effective preset, active chips, reset, and several sort modes. It does not yet
  filter by processing status, compatibility to a chosen track, or prior set
  usage, and chips are not individually removable.
- [~] **Clickable filter discovery.** Role and genre crates can apply filters
  directly. BPM, key, compatibility factors, and metadata values throughout
  expanded track details are not all clickable filter shortcuts yet.
- [~] **Candidate diversity.** Multiple candidates are generated and ranked
  with phrase, loop, transition, context, and safety measurements. The three
  choices are not yet deliberately assigned distinct strategies such as
  original-preserving, smoothest-loop, and strongest-DJ-utility.
- [~] **Metadata authority and consistency.** Manual genre decisions currently
  outrank inferred metadata and propagate across the main collection views.
  The same explicit authority model and stored override provenance still needs
  to cover every artist, title, version, BPM, key, duration, role, and playlist
  value.
- [~] **Duplicate control.** Tracks now receive durable, human-readable
  recording-family and version IDs, new imports match source identifiers and
  normalized recording names, exact audio fingerprints are generated, and
  Collection Integrity supports conservative merge review or an explicit
  keep-separate decision. Confirmed merges preserve playlists, jobs, feedback,
  verified keys, artwork, and the unused physical WAV. Perceptual fingerprinting
  and automatic prevention before every external download remain planned.
- [~] **Durable background jobs.** Processing jobs persist, interrupted active
  work is recovered to a truthful failure state, and the UI supports pause,
  resume, cancel, retry/reprocess, reordering, review states, and queue cleanup.
  Downloads, matching, exports, and processing do not yet share one durable job
  model, and automatic restart continuation/idempotency requires more work.
- [~] **UI consistency.** Navigation language, dense track rows, crate sidebars,
  selection behavior, destructive styling, single-audio playback, and many
  responsive layouts are aligned. A formal shared component system, complete
  status/color normalization, keyboard audit, reduced-motion support, and
  viewport regression suite remain unfinished.
- [~] **Set Builder maturity.** The current builder includes one explainable
  proposal, energy/BPM curves, manual ordering, rules, alternatives, transition
  scores, vocal-clash warnings, saved plans, and exports. Multiple proposal
  strategies, transition audio previews, used-in-set tracking, deeper warnings,
  and DJ-platform set exports remain planned.
- [~] **Restart and recovery testing.** Interrupted-job recovery and pause/resume
  behavior have automated tests. Large realistic catalog migrations, complete
  restart/retry end-to-end coverage and performance fixtures remain part of the
  milestone gate. Integrity-checked backup/restore, retention, restore preview,
  pre-restore snapshots, and recovery documentation are complete.

## Feedback-informed candidate ranking

Use accepted and rejected listening feedback to personalize candidate ordering
without replacing the technical safety score.

- Derive preference signals by track classification and transition traits.
- Show technical and personal-preference scores separately.
- Explain which feedback patterns influenced each score.
- Require a minimum amount of feedback before applying adjustments.
- Keep feedback ranking optional and retain the original scorer as a baseline.
- Prevent a small number of tracks from overfitting the ranking model.

## Preflight analysis mode

Analyze a batch before rendering audio, then review proposed classifications,
presets, stem use, bar lengths, candidates, and warnings before approval.

## Automatic A/B evaluation

Compare original and edited transitions with identical, loudness-matched
listening windows and record the preferred version.

## Manual waveform editor

Drag loop and splice regions on the waveform, snap them to bars, audition the
result, and rebuild without editing JSON overrides.

## Candidate diversity

Make the three ranked choices intentionally represent different strategies:
closest to the original arrangement, smoothest technical loop, and strongest
DJ utility.

## Transition repair modes

Select among micro-crossfade, tail-preserving overlap, reverb continuation,
drum underlay, harmonic sustain, and progressive stem reconstruction.

## DJ export profiles

Provide Rekordbox, Serato, Engine DJ, and Traktor naming, bit depth, cue, loop,
and metadata profiles.

## Beat-grid verification workflow — deferred

Status: **Backlog.** Keep this design for a later milestone; it is not the
current implementation priority.

Add a dedicated review workflow for tracks whose rhythmic analysis needs
confirmation, without treating missing cues as an analysis failure.

- Surface tracks with low beat-grid confidence, tempo drift, or conflicting BPM
  and downbeat estimates.
- Show the waveform with detected beat and downbeat markers during playback.
- Provide quick corrections for half/double BPM, grid offset, and the first
  downbeat.
- Let the user mark a beat grid as verified and exclude verified tracks from the
  review queue.
- Preserve manual beat-grid corrections and verification across reanalysis,
  rescans, imports, and library moves.
- Use verified timing data in loops, cue placement, transition scoring, and Set
  Builder recommendations.

## Library intelligence

Group tracks by warm-up, peak-time, closing, vocal-safe, melodic, ambient, and
live timing behavior, with BPM/key-compatible track suggestions.

Next Library milestone:

- Fix the Workspace **Latest analysis** card so long track names never overflow
  its column. Use a bounded title area with wrapping or ellipsis, preserve the
  metadata line, and keep the card responsive at narrow widths.
- Keep Workspace focused on active processing and brief recent status. Put
  discovery, organization, compatibility, and set-planning filters in Library
  rather than duplicating them on the processing dashboard.
- Explain every mix role in beginner-friendly language, including when a DJ
  would use warm-up, peak-time, closing, vocal-safe, melodic, ambient, and live
  timing tracks.
- Make every role expandable so a count such as `16 warm-up` can reveal all 16
  tracks rather than only showing three examples.
- Explain compatibility percentages and show the individual factors behind the
  score, such as BPM distance, harmonic compatibility, energy, role, vocal
  density, and timing behavior.
- Show both conventional musical keys and Camelot Wheel notation throughout the
  Library. Make the preferred notation configurable without discarding the
  alternate value.
- Distinguish the preset requested by the user from the concrete preset chosen
  by automatic classification. Filtering by the effective detected preset must
  work even when the original job was submitted with `auto`.
- Replace the basic Library filter row with set-planning filters for BPM range,
  key/Camelot value, energy, mix role, genre/category, vocals, timing behavior,
  extension result, effective preset, and processing status.
- Support practical discovery questions such as: tracks near the current BPM,
  harmonically compatible tracks, tracks that raise or lower energy, vocal-safe
  transitions, warm-up or closing alternatives, and tracks not yet used in a
  planned set.
- Allow clicking a role, key, BPM, category, or compatibility factor anywhere
  in Library to apply it as a filter instead of requiring the user to rebuild
  the same query manually.
- Make active filters visible, removable, and easy to reset; include sorting by
  title, BPM, key, energy, compatibility, and most recently processed.
- Treat the Library as a broader DJ set-planning hub rather than only an archive
  of generated edits.

Potential follow-up: add a set builder that proposes an ordered crate or set
using harmonic compatibility, BPM progression, energy arcs, mix roles, vocal
spacing, and user-defined opening/peak/closing goals. Keep suggestions
explainable and manually reorderable.

## Automatic best-source import

Keep single-track importing simple: the user supplies a Spotify or YouTube
reference and the app recommends one source rather than making them compare
formats manually.

Use the same resolver for playlist CSV and other bulk imports. Bulk mode should
automatically download the best eligible version for every track without asking
the user to choose candidates one by one.

- Resolve Spotify metadata, then search approved external catalogs and YouTube.
- Prefer an explicitly downloadable, clearly licensed original FLAC/WAV over a
  compressed source. Accept lossless derivatives only when their provenance
  points to an original lossless master.
- If no better licensed master is available, use the existing ranked YouTube
  match as the fallback after the current authorization confirmation.
- Rank source quality separately from recording identity. Verify title, artist,
  remix/version, and duration before comparing codec or technical quality.
- Compare source codec, provenance, sample rate, bit depth, clipping, true peak,
  loudness, spectral bandwidth, and duplicate fingerprint where practical.
- Preserve the selected source URL, license URL, attribution, source identifier,
  quality tier, and import date in the catalog.
- Present one recommended result with a short explanation, while keeping
  alternate candidates and diagnostic measurements in optional details.
- In bulk mode, resolve and rank every row independently, automatically choose
  the best eligible source, and continue processing the rest of the batch when
  one track cannot be resolved.
- Apply a minimum identity-confidence threshold before automatic bulk download.
  A higher-quality file must not override a stronger title/artist/version match.
- Prefer lossless licensed sources in bulk exactly as in single-track import;
  otherwise use the validated YouTube fallback when its download authorization
  is already established for that batch.
- Produce one completion report grouping imported lossless masters, imported
  compressed sources, YouTube fallbacks, duplicates skipped, ambiguous matches,
  missing licenses, and failed downloads.
- Put ambiguous, mismatched, or unlicensed rows into **Needs review** rather than
  silently downloading them or blocking successful rows.
- Never describe a lossy YouTube source decoded to WAV as lossless; label it
  **Lossy source converted to WAV**.
- Do not substitute a different recording merely because its file format looks
  better. When identity or licensing is uncertain, keep the result for review.

Initial catalog priority: Jamendo, ccMixter, Internet Archive items with explicit
license metadata, and Free Music Archive where the individual track license and
download permission are unambiguous.

Acceptance criteria:

- The default import flow remains one paste and one recommended source.
- Bulk imports require one batch action rather than per-track source selection.
- Every eligible bulk row receives the best verified version available at the
  time of import, with resumable progress and a final exception report.
- A licensed lossless master wins over a YouTube-derived version of the same
  recording.
- YouTube remains a usable fallback when no verified better source exists.
- Every automatic choice can explain both the identity match and quality choice.
- Importing never silently changes the requested mix, edit, live recording, or
  remaster.

## Stability and scale milestone

- [x] Introduce hierarchical electronic taxonomy (Electronic → Techno/House/
  Bass/D&amp;B/Trance/Garage/Breaks/Hardcore → subgenre) and reusable,
  stateful collapsible genre trees in Music Files and DJ Library.

- [x] Add a local audio playlist importer that converts existing MP3/lossless
  collections to tagged WAV files, classifies them into genre folders, retains
  playlist membership, and skips exact catalog duplicates without extending.

- [x] Serve the DJ Library from a compact latest-generation catalog instead of
  transferring the full job history, full report, and full download catalog on
  every visit. Version history now loads only when a track requests it.
- [x] Add bounded, status-filterable job paging and cache the parsed processing
  report until its file changes.

Pause major feature expansion and harden the current workflow before deepening
Set Builder:

`Import → Music Files → Process → DJ Library → Set Builder`

Review Queue and Analysis & Feedback remain supporting branches. The objective
is to make the existing system fast, predictable, recoverable, and consistent
for large real-world DJ collections.

### 1. Library-scale performance

Phase-one hardening completed September 21, 2026:

- Downloaded-catalog filesystem migration is no longer tied to page refreshes.
- [x] Catalog migration now has a durable SQLite version checkpoint, so app
  restarts skip the legacy sidecar scan entirely. A manual background
  **Reconcile files** action compares stored modification-time and size
  signatures and processes only new or changed source records.
- Latest and latest-completed analysis jobs are joined to catalog tracks in
  indexed SQLite queries instead of scanning up to 10,000 jobs in Python.
- Music Files and DJ Library audio sources load only when the user interacts
  with a player; opening either page no longer starts hundreds of audio range
  requests.
- Both collections show bounded 50- or 100-track pages with numbered navigation
  above and below the list. Off-page cards are detached from the live document;
  filtering, sorting, page-local **Select all visible**, and cross-page
  selections remain available.
- Music Files now requests only its current page. Search, genre, playlist,
  analysis status, and sorting execute in indexed SQLite queries; the response
  includes filtered totals and catalog-wide genre/playlist facets. Rapid search
  responses are sequence-guarded and selections persist across server pages.
- Repository coverage verifies latest versus completed analysis resolution;
  the full automated suite currently contains 122 passing tests.

Remaining scale work:

- Establish measurable targets for 1,000, 5,000, and 10,000-track collections.
- Stop rendering an audio element and a full detail body for every track at
  initial page load. Load players and expanded details only when requested.
- [x] Add bounded server-paginated lists to Music Files and DJ Library while
  preserving filters, sorting, page-local selection, and numbered navigation.
- [x] Move DJ Library filtering, sorting, pagination, and sidebar aggregation to
  an indexed SQLite search table using the server-page pattern established in
  Music Files. Only the requested 50/100 Library cards are transferred and
  rendered; generation history remains lazy.
- [x] Add catalog-wide **Analyze all matching** from Music Files and reuse the
  memory planner for up to three concurrent analysis-only jobs. Stem-enabled
  processing and extensions remain exclusive, and report writes are serialized.
- Cache Library Intelligence counts and compatibility inputs, then invalidate
  only the affected track when metadata or analysis changes.
- Add loading, partial-result, and retry states so a slow catalog never appears
  empty or frozen.

Acceptance criteria:

- Opening Music Files or DJ Library remains responsive with 10,000 tracks.
- Filtering and sorting produce visible results quickly without freezing audio
  playback or the rest of the interface.
- Selecting all visible tracks works across pagination or virtualization without
  selecting hidden tracks unintentionally.

### 2. Metadata authority and consistency

Deferred workflow: **Guided Needs attention triage**

- Split attention items into missing metadata, unmapped genre, missing file,
  failed artwork, and other maintenance failures.
- Show the exact track and reason for every item, with focused single-track and
  bulk repair actions.
- Offer automatic genre suggestions and sequential metadata review without
  hiding unresolved items across pages.
- Reconcile reports automatically so repaired or removed tracks disappear and
  resolved maintenance errors do not return after refresh or restart.

- Define one precedence policy for every editable value: manual user edits,
  trusted analyzed values, imported metadata, inferred values, then fallback.
- Apply the policy consistently to genre, subgenre, artist, title, remix/version,
  BPM, key, Camelot value, duration, playlist membership, and track roles.
- Store manual overrides explicitly instead of inferring them from a filename or
  current folder, so rescans cannot overwrite user decisions.
- Display the source of important values where useful: manual, analyzed,
  imported, or inferred.
- Make a metadata change propagate immediately to Music Files, DJ Library,
  filters, Set Builder, reports, exports, and physical genre folders when
  applicable.
- Add an audit/repair command for catalog values that disagree with their stored
  metadata or on-disk location.

Acceptance criteria:

- Refreshing, rescanning, restarting, or reanalyzing never reverses a manual
  metadata choice.
- Every page shows the same effective artist, title, genre, BPM, and key for a
  track unless it intentionally labels a historical value.

### 3. Stable track identity and duplicate control

- Introduce a stable recording identity separate from filenames, import rows,
  processing jobs, and generated versions.
- Combine available identifiers such as Spotify URI, YouTube ID, normalized
  artist/title/version, duration tolerance, and an audio fingerprint.
- Distinguish an exact duplicate from a remix, edit, radio version, live version,
  remaster, or alternate recording.
- Attach multiple playlist memberships and source references to one recording
  instead of duplicating its master WAV.
- Provide a duplicate review screen for uncertain matches with merge, keep
  separate, and replace-file actions.
- Preserve analysis, edits, feedback, playlist membership, and set usage when
  records are safely merged.

Acceptance criteria:

- Reimporting the same recording does not create another master track or WAV.
- Legitimate alternate versions remain independent and are clearly labeled.
- A merge never silently discards analysis, edits, feedback, or set references.

### 4. Durable background jobs

- Persist download, matching, analysis, extension, export, and review states in
  a unified job model.
- Recover queued and interrupted jobs after an application restart without
  duplicating output or leaving tracks permanently marked as processing.
- Define clear paused, awaiting-review, dismissed, canceled, retryable-failure,
  permanent-failure, and completed states.
- Add retry controls with retained configuration and an error explanation.
- Make pause and cancel cooperative at safe processing boundaries and keep a
  canceled track available for a later retry.
- Record structured stage timing and failure context for diagnostics without
  exposing secrets or excessive logs in the UI.

Acceptance criteria:

- Restarting the app during a batch leaves every job in a truthful, recoverable
  state.
- Retrying a failed or canceled job never creates an accidental duplicate
  generation or corrupts the original file.

### 5. UI and terminology consistency

- Create a small shared design system for dense track rows, expanded details,
  filters, badges, action menus, selection bars, empty states, and dialogs.
- Standardize primary, secondary, destructive, and disabled button hierarchy.
- Keep terminology aligned with the navigation: Process, Import, Music Files,
  DJ Library, Set Builder, Review Queue, Analysis & Feedback, and Settings.
- Use the same status labels and colors across queue rows, Music Files, DJ
  Library, Review Queue, and reports.
- Make bulk selection, card expansion, audio playback, and overflow menus behave
  consistently without click conflicts.
- Complete keyboard navigation, focus indicators, accessible names, and reduced
  motion support for every primary workflow.
- Add responsive checks for laptop, narrow desktop, tablet, and mobile widths.

Acceptance criteria:

- The same action or status looks and behaves the same everywhere it appears.
- All core workflows can be completed by keyboard and remain readable at the
  supported viewport sizes.

### 6. Set Builder maturity after stabilization

- Generate multiple explainable running-order proposals rather than a single
  answer, such as safest mix, strongest energy journey, and most adventurous.
- Support required, excluded, locked, and alternate tracks while preserving
  manual ordering.
- Add transition previews using the selected original or extended versions.
- Improve energy-curve, BPM, harmonic, vocal-spacing, timing, and role controls.
- Warn about abrupt tempo/key/energy changes, repeated artists, vocal clashes,
  timing risk, unavailable files, and insufficient duration.
- Track whether a song has already been used in the current or saved sets.
- Export portable playlists and DJ-platform-ready set metadata without copying
  duplicate audio unnecessarily.

Acceptance criteria:

- Every recommendation explains why the track and transition were chosen.
- Users can alter any proposal without losing locked choices or regenerating the
  entire set unnecessarily.
- Exported running orders point to the intended source or extended version of
  every track.

### Milestone completion gate

- Add performance fixtures and a repeatable large-library benchmark.
- [x] Add a repeatable lifecycle regression fixture covering reimport,
  analysis history, verified keys, feedback, library relocation, restart,
  reanalysis, and playlist export with real WAV files and a temporary catalog.
- Add migration and recovery tests against a copy of realistic catalog data.
- Add end-to-end tests for import, analyze, review, extend, organize, build set,
  restart, retry, and export workflows.
- [x] Document and implement validated backup and restore of the catalog,
  metadata, settings, presets, reports, playlists, library identity, and
  optional analysis cache, with a pre-restore safety snapshot.
- Do not begin another major product area until the scale, consistency,
  duplicate, recovery, and core UI acceptance criteria above are met.

## Regression listening suite

Keep a curated group of difficult tracks and compare algorithm revisions
against saved candidate decisions and listening feedback.

## Recently completed: genre review and folder expansion

- Split the broad Needs genre bucket into Missing metadata, Unmapped metadata,
  and Broad Latin so each group has a clear next action.
- Added those review states as direct Music Files filters with independent
  counts under a collapsible Needs genre folder.
- Expanded Latin classification with neoperreo, flamenco, Latin rock, Latin
  indie, Latin ska, Latin hip-hop, and Latin R&B.
- Expanded electronic classification with future bass, dubstep, moombahton,
  phonk, big beat, and trip hop, plus additional hip-hop and pop mappings.
- Preserve automatic folder creation: a genre rescan creates any newly needed
  hierarchy and moves the WAV while keeping catalog and analysis paths synced.
