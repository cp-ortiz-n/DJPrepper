# User guide

This guide covers the browser application, music-library workflows, processing controls, Set Builder, reports, and Rekordbox handoff. See the root README for installation and startup.

## Local web application

The AudioExtender CLI remains fully supported. DJ Library Studio is the broader
local interface over the same tested processing engine; it does not upload audio
to an external analysis service.

Start it from the project folder:

```bash
python3 -m audioextender.web
```

On macOS, you can instead double-click **Start AudioExtender.command** in the
project folder. The launcher starts Ollama when necessary, downloads the
configured local model on the first run, starts AudioExtender, and opens the
browser. Closing its Terminal window stops AudioExtender; Ollama may remain
available for the next launch.

Then open [http://localhost:8765](http://localhost:8765). The dashboard supports
multi-file drag and drop, edit settings, a persistent processing queue, live
stage progress, recent analysis results, full-length source and extended audio
players, contextual intro/outro preview players, and downloads for both WAV
versions. Web jobs run one at a time by design so Demucs and audio analysis remain
safe on a 16 GB Mac. The active track is pinned above pending tracks. It can be
paused and resumed at safe progress checkpoints; a long Demucs or analysis call
may briefly show **Pause requested** until that operation returns. Cancel applies
to queued jobs, and a canceled entry can be reprocessed without uploading the
song again. Closing the browser does not cancel a running job; closing the Python
server does.

The browser code is split by user-facing feature: Music Files, DJ Library, Set
Builder, Settings, and Analysis & Feedback each own their rendering and state.
`frontend/app.js` is the composition/navigation entry point; shared request state,
audio playback, and reusable controls live in dedicated modules. These features
receive one validated frontend-services contract for API access, feedback, DOM
access, and musical-identity editing. Direct global network calls are prohibited
inside the five feature modules, while overlapping search requests continue to
use the shared cancellation and stale-response controller. See
[`architecture.md`](../architecture/architecture.md) before making frontend changes.
Authorized source inspection, queue controls, progress polling, and completion
feedback are owned by `frontend/features/imports/import-workspace.js`, not the composition entry point.
Local-file imports are owned by `frontend/features/imports/local-audio-import.js`; playlist matching,
permissions, and Creative Commons verification are owned by
`frontend/features/imports/playlist-import.js`. Processing queue polling, request serialization,
generation/ETA derivation, filtering, and candidate-review routes are owned by
`frontend/features/processing/processing-workspace.js`, keeping those lifecycle rules independently
testable from page composition. Processing-card presentation and DOM action
binding are owned by `frontend/features/processing/processing-workspace-view.js`. Candidate decisions,
custom waveform regions, insertion previews, transition scoring, and review
reprocessing are owned by `frontend/features/processing/candidate-review.js`.

### Optional local AI for Set Builder

Set Builder can translate a natural-language DJ brief into a structured,
editable plan before it chooses any tracks. It also creates an editable musical
journey made of named sections, runtime percentages, catalog genres, musical
characteristics, purposes, and start/end energy targets. The default `auto`
provider order is local Ollama, optional OpenAI, and finally deterministic rules.

After reviewing an AI brief, confirm its **Planned journey** before building the
track list. Exact genre prompts are strict by default: “Create a Latin Techno
set” keeps Latin Techno in every section while allowing the energy and purpose
to evolve. Short names are canonicalized from relationships in your current
catalog: Set Builder groups each organized genre with the detailed genre names
found on its tracks. When one detailed name appears under several organized
genres, Set Builder first prefers the canonical family whose name contains that
phrase, then uses that specific alias's observed track count as a tie-breaker
instead of the unrelated size of the whole parent category. Broad catalog names
joined with `&` also expose their own components, so prompts such as “rock,”
“chill,” “funk,” and “soul” resolve without a source-code exception list.
For example, “disco” selects **Disco & Funk** when Disco is a detailed genre on
tracks organized there. No global list of genre exceptions is required, so new
genres become available as the library evolves. The written brief remains
authoritative even when the AI omits that genre from its structured response. The journey
starts as compact overview rows; expand only the section you want to edit. Use
**Use in every section** to apply the core genres at once.
Related catalog genres proposed by the model appear as unselected suggestions;
turn on **Allow related genres** and add only the bridges you actually want.
If Local AI proposes an unrequested genre, Set Builder moves it out of the
active section automatically and labels the journey **Adjusted · review**.
The idea remains available as a suggestion, but it cannot affect track selection
until you explicitly enable related genres and add it. A disabled **Confirm
journey** button means a duration, empty-section, or genre-boundary issue is
named in the journey footer and must be corrected first.
Editing any section marks the journey unconfirmed again. **Reset** restores
the reviewed proposal, while **Regenerate journey** creates another structure
from the current prompt.

Rules-based planning now treats those section genres as positional constraints,
not just overall set suggestions. It fills each section from matching analyzed
tracks and keeps transition optimization inside the section boundary. When a
strict section needs more unique matches than the catalog contains, the build
stops and names the scarce section instead of silently filling it with another
genre. Edit that section, enable related genres, or analyze and retag additional
matching tracks, then build again.

Set Builder separates direction authoring from track selection. Choose
**Describe what I want** to have Local AI turn natural language into an editable
brief, or **Configure the journey** to define genres, energy, flow, and
constraints yourself. Then choose **AI curated** to have the
configured model rank and order a bounded catalog shortlist, or **Rules-based**
to use local genre, BPM, key, energy, and constraint scoring only. The summary
above the build action always shows both choices. AI-curated results are still
validated against real catalog IDs,
available files, exclusions, required or locked tracks, duration, section
coverage, BPM jumps, keys, and vocal collisions. Invalid model plans receive up
to two bounded repair attempts, then fall back to a deterministic catalog-backed
plan. Planning runs as a cancellable background job so a stale response cannot
replace the current set. Ollama receives the text brief and bounded catalog
metadata; it never receives audio. When the optional OpenAI fallback is
configured, only that text context is sent and request storage is disabled.
Each completed AI plan now includes deterministic quality measurements for
scarcity tiers, requested-genre and journey coverage, duration accuracy,
repeated artists, and transition warnings. The generated-set screen shows this
disclosure, and saved sets retain the planning mode, provider/model, validation
warnings, evaluation, fallback reason, journey, and per-track selection reasons.
Planning jobs persist locally; an app restart marks interrupted work as safely
retryable instead of losing or silently applying it.

Choose **Curate track by track** when you want to build from an empty running
order. The catalog search is not limited to genre: enter an artist, title,
playlist/crate name, descriptor, role, vibe, detailed genre, audio profile, or
several keywords. Results rank all matching identity evidence and show the
specific playlist, tag, genre, or other source that matched. Turn on **Require
every keyword** for a narrower intersection. Preview any result with the same
seekable player used in the running order, then add it at the next position.
The catalog initially shows the 12 strongest matches; **Show more** reveals the
next ranked batch without changing the search or losing the current set.
**Suggest next** ranks unused tracks against the current last track, while
**Check transitions** opens mix health after at least two tracks exist.
The live running order stays in a sticky **Current set** rail beside the catalog,
so you can preview and add tracks without losing sight of the set you are shaping.
The rail scrolls independently and can be collapsed. On smaller screens it moves
above the catalog with a bounded height, keeping both the current set and search
results close at hand.

The rail also contains **Set Coach**. Choose an **Energy shape**—Gradual build,
Peak and release, Energy waves, or Hold the level—then select **Preview best
order**. Set Coach compares only the tracks already in the set, preserving
locked positions, journey-section boundaries, and set membership. The preview
shows both mix-health and energy-fit changes plus each proposed track's energy;
nothing moves until you choose **Apply order**, and the change remains undoable.
**Suggest next tracks** uses that same energy shape when ranking unused catalog
tracks against the current ending, intention, preferences, and compatibility,
then opens those candidates with their evidence and audio previews.

Only one version of a song family may occupy the set. After adding an original,
remix, edit, or duplicate import, other versions are labeled **Already in set**
in the catalog browser. Use **Alternatives** on the running-order row to
swap versions without creating a duplicate. Manual sets keep the normal
drag/reorder, Undo/Redo, transition editing, save/load, review, and export
behavior.

After a plan exists, use **Lock** on any track that must stay, then choose
**Regenerate unlocked** in the persistent workspace bar. Set Builder reuses the
current brief and journey rather than interpreting the intention again. Locked
tracks remain in their current journey sections; required tracks, exclusions,
available-file checks, and one-version-per-recording rules still apply. The
workspace reports how many tracks stayed or changed and how many locks were
preserved. **Undo** restores the complete previous revision, including its
track order, locks, transitions, revision number, and planning receipt.

The running order has a visible drag handle beneath each track number. Drag an
unlocked track before or after another row to reorder it, or focus the handle
and use the Up/Down arrow keys for precise keyboard movement. Reordering is
undoable and immediately recalculates the neighboring transition scores. A
locked track must be unlocked before it can be moved. Every compact track row
also keeps its audio preview visible: press **Play**, drag the seek bar to sample
another part of the track, and use the speaker control to mute or unmute it.
Starting another preview stops the previous track, and changing the running
order stops the current preview before the rows are rebuilt. **More** opens a fixed
track inspector whose close control remains visible; click outside the
inspector or press Escape to dismiss it. Opening **Edit mix** closes the
inspector first. The transition editor keeps its close control visible while
scrolling, also provides **Done editing** at the bottom, and accepts Escape.

Track feedback is available from **More** without crowding the compact row.
**Keep** saves a preference immediately and shows **Kept · saved**; it does not
lock the position. **Reject & replace** opens a short guided dialog where the
reason is optional and the scope is explicit: reject only that version, or the
song's complete recording family. Set Builder saves the feedback before
changing the running order, then chooses the strongest eligible replacement
for the same journey section. The replacement must pass the current hard rules,
must not duplicate another recording family, and is labeled **Replaced**. Undo
restores the prior track and retracts the saved rejection; Redo reapplies both.
Locked and required tracks explain why they must be unprotected before they can
be rejected. If no valid replacement exists, the original remains visibly
**Rejected · feedback saved**, Save and Export stay unavailable, and **Retry
replacement** becomes available after rules are relaxed. This prevents a
rejected track or a silent gap from being exported accidentally. Retry keeps
the already-saved reason and scope; use Undo first if the decision itself needs
to change.

Phase 2D compares every validated AI proposal with an independently generated
deterministic baseline. AI wins only when it improves the deterministic quality
score, preserves requested-genre coverage, and still passes every hard
validator. Track uniqueness is enforced by permanent recording family, not by
filename: an original, remix, alternate import, or spelling/spacing variant of
the same song can contribute at most one track to a set. This rule applies to
AI planning, deterministic planning, saved-set recovery, and manual add or
replace actions. Saving, undo/redo restoration, regeneration, CSV export, and
M3U8 export pass through the same recording-family invariant as a final safety
boundary. A protected version wins over an unprotected version; when two
locked or required tracks are versions of the same song, planning stops and
asks you to keep one instead of silently breaking a lock. Legacy saved sets are
reconciled when loaded, with unavailable tracks recovered separately so a
duplicate version is never replaced by an unrelated song. **Alternatives** on a recommended track still shows every
analyzed version in that recording family—such as the original, remix, extended
mix, or live version—before suggesting different songs. Choosing one replaces
the current version, so you can compare versions without creating a duplicate.
Exact-count schemas restrict model output to real candidate and
section IDs. A narrow structural repair boundary removes duplicates and fills
missing section slots from eligible candidates while preserving valid unique AI
choices; every repair is disclosed. The generated-set receipt shows both
scores, the winner, the reason, and any repair count.

Phase 2E adds local, explainable preference learning without retraining or
granting the model control over safety rules. Locking, removing, replacing,
adding, keeping, rejecting, saving, and exporting tracks record small catalog-feature signals in a
local JSON store. A signal must be supported by at least three distinct tracks
before it changes candidate ordering, the combined adjustment is capped at
eight points, and broad signals are damped so they do not hide distinctive
genre or musical-identity evidence. Preferences are scoped by set vibe and can
be inspected, paused, or reset from Set Builder. Exclusions, required tracks,
file availability, validation, and the deterministic Phase 2D comparison remain
authoritative.

Phase 2F adds a persistent human-review and calibration loop. A DJ can approve
or reject the running order, accept or reject individual tracks with structured
reasons, rate transitions, and leave notes. Reports compare personalized and
neutral acceptance, identify rank changes, direct versus expanded matches,
contradictory judgments, rejection patterns, and broad signals that may be
overfitting. Individual learned signals can be dismissed. Transition
preferences for BPM movement, harmonic compatibility, vocal spacing, energy
movement, blend length, and technique require three distinct track pairs before
they influence automatic transition optimization. The catalog evaluation tool
now runs the five checked-in musical scenarios with and without personalization
and reports changed tracks, order changes, and quality deltas.

Phase 2G is the production-acceptance boundary. Every planning receipt records
candidate retrieval, model/planning, validation/comparison, evaluation, and
total timing, together with provider attempts, repairs, outcome, model, and
fallback reason. Set Builder exposes aggregate local AI operations without
including audio or catalog contents. The evaluation command applies a strict
release gate: all selected scenarios must complete with valid catalog-backed
plans and full requested-genre coverage, and the DJ must explicitly confirm the
listening review with `--manual-listening-approved`. Automated success alone
can never mark AI Set Builder v1 released.
The production planner makes one bounded model attempt before using its
validated deterministic fallback; repeated slow retries cannot freeze a set
generation or multiply a provider outage into several minutes of waiting.
The model receives a section-balanced shortlist rather than the full candidate
cap. Filesystem paths, verbose score explanations, provenance records, and
other validator-only fields remain local. Ollama returns only catalog track IDs
and section IDs; readable reasons are rebuilt from verified local evidence.
This keeps real-catalog planning within the latency gate without weakening
validation. Missing requested genres pass coverage only when the candidate pool
proves that zero matching files are available and the result discloses the
scarcity explicitly.

Install the recommended local provider on macOS with:

```bash
brew install --cask ollama-app
open -a Ollama
ollama pull qwen3.5:4b
```

Set Builder continues to work without Ollama by using offline rules. Provider
behavior can be configured with:

```bash
export AUDIOEXTENDER_LLM_PROVIDER=auto  # auto, ollama, openai, or offline
export OLLAMA_SET_BUILDER_MODEL=qwen3.5:4b
export OLLAMA_HOST=http://127.0.0.1:11434
export OPENAI_SET_BUILDER_MODEL=gpt-5-mini
export OPENAI_API_KEY=...                # optional cloud fallback
```

The UI identifies results as Local AI, Cloud AI, or offline rules. Model output
is schema-constrained and sanitized against catalog vocabulary before the
browser uses it. The journey must total 100% of the target runtime; edits to its
section order, genres, and energy targets feed either safe planning mode.
While the brief or track order is being prepared, Set Builder shows the current
stage, elapsed time, validation boundary, and the remaining stages. AI planning
also shows backend progress when it is available. Journey sections are grouped
as complete cards so their name, duration, energy movement, genres, character,
and purpose can be reviewed together. If an AI response omits a section's end
energy, the UI safely keeps that section at its valid starting energy instead of
displaying an unknown target. Track **Keep** and **Reject** choices remain
visible after selection and are not submitted as learning evidence until the
set review is saved.

When AudioExtender starts, its Terminal prints the detected Set Builder AI
provider and model. Every interpreted brief also logs the provider, model,
response time, and vocabulary size without logging the brief or track metadata.
The Set Builder card shows the same live state as **Local AI ready**, **Cloud AI
ready**, or **Offline rules**.

For an opt-in acceptance run against the installed Ollama model—including real
structured track selection from controlled candidates—run:

```bash
AUDIOEXTENDER_RUN_LOCAL_LLM_TESTS=1 .venv/bin/python -m unittest tests.integration.set_builder.test_local_intention_acceptance
```

For a repeatable evaluation against the current exported catalog and the
checked-in DJ-brief scenarios, run:

```bash
.venv/bin/python scripts/benchmarks/evaluate_set_builder.py
```

The harness writes `workspace/output/reports/set_builder_evaluation.json`, compares the
new results with the prior run, and reports candidate scarcity, journey and
genre coverage, duration accuracy, warnings, repeated artists, planning time,
and the deterministic quality score. Set `AUDIOEXTENDER_LLM_PROVIDER=offline`
to measure the deterministic fallback or leave the configured provider active
to evaluate real AI track selection. The catalog and scenario paths can be
overridden with `--catalog` and `--scenarios`.
Use `--scenario latin-kickback` to iterate on one checked-in case without
running the complete model suite.
After listening to and approving every result in the complete suite, rerun with
`--manual-listening-approved`. A zero exit status then means the final Phase 2G
release gate passed; without explicit listening approval the report remains
truthfully pending even when every automated measurement succeeds.

Deterministic fallback plans use bounded transition optimization after track
selection. It cannot change selected tracks or their journey sections; it only
orders them for smoother BPM—including half/double-time compatibility—Camelot
key, vocal, and energy movement. Checked-in scenario thresholds cause the
evaluation command to fail when quality, coverage, or transition warnings
regress.

The **Import** tab can convert an individually confirmed, authorized YouTube
source to WAV. It can also read a Spotify playlist CSV and suggest a likely
YouTube URL for every track without Spotify credentials. The importer directly
recognizes exports with `Track Name`, `Artist Name(s)`, `Duration (ms)`,
`Genres`, and `Tempo`; only the track and artist columns are required.

Spotify matching does not extract audio from Spotify or automatically download
a playlist. Review each suggested title and duration; only pass a match to the
authorized importer when you own it, its license permits copying, it is public
domain, or you have direct permission.

The playlist results also provide **Download verified Creative Commons**. This
batch operation checks the license reported by each YouTube result, downloads
only recordings explicitly labeled Creative Commons, converts them to WAV
without running the extender, skips existing WAVs, and produces a ZIP plus a
JSON report of downloaded, existing, non-CC, and failed tracks.

The **Workspace** is an active-processing surface: it shows queued, running,
failed, or canceled jobs and moves successful results into Library. The
**Library** owns playback, downloads, latest full details, and version history.
Completed jobs that requested candidate auditions remain as compact
**Awaiting review** checkpoints in Workspace until their review is submitted or
dismissed, so the listening decision is not lost when processing reaches 100%.
Expand **Show full details** on a library track for synchronized source/extended
players, loudness-envelope waveforms, musical-feel and song-section timelines,
cue positions, boundary overrides, and every download. The waveform's beat-grid
anchor is a point marker derived from an
observed downbeat; loop regions remain visibly shaded, while point cues do not
cover the audio display. Original and extended waveforms are stacked for direct
visual comparison: gray is unplayed audio, lime is played audio, and orange is a
cue. The colored timeline bands distinguish detected musical labels rather than
quality; hovering one shows its name, timestamps, and confidence.

Settings includes a resumable **Audio Quality** scan for the complete music
library. It samples representative regions of each saved file and records an
explainable 0–100 estimate using sample rate, bit depth, spectral bandwidth,
clipping, and possible silence/dropouts. The score intentionally does not treat
a WAV container's high PCM bitrate as proof that its original download was
lossless. Music Files shows the stored score on each track, while Settings shows
coverage, the library average, and the Excellent, Good, Review, and Poor counts.

### Browse and maintain Music Files

Music Files keeps everyday browsing separate from catalog maintenance. Search
and sort are always available. Open **Filters** for genre, detailed genre,
playlist, analysis, artwork, and quality constraints; active constraints appear
as removable chips above the result count. **Library maintenance** contains
catalog-wide identity inference, file reconciliation, metadata, artwork, genre,
and reanalysis operations. Those actions may affect every matching track and do
not depend on the current page selection.

Use **Select page** to choose the visible tracks. A contextual action bar then
offers analysis, identity, genre, metadata synchronization, artwork, download,
and removal actions for only that selection. Clearing the selection removes the
bar. The count beside it calls out selected tracks that still need artwork.

Candidate auditions are opt-in because rendering six contextual audio files for
every song adds processing time and visual clutter. Enable **Review candidates**
before adding files, or click **Create review** on a completed track. The new
generation appears in the separate **Review** inbox with playable source,
selected edit, and ranked intro/outro candidates plus listening notes. A
normal job still evaluates and automatically selects its ranked candidates; it
simply does not export or display all of the audition files.

Every Music Files recording has a permanent readable identity such as
`HOU-000184-ORG`. Related versions share the `HOU-000184` family while the
three-letter prefix identifies the parent genre and suffixes identify
the original, extended edit, remix, radio edit, live recording, remaster,
instrumental, or acapella. Manually confirmed IDs survive renames, genre moves,
reanalysis, and library relocation. Catalog startup, import, metadata
correction, and reanalysis may repair an unlocked legacy family ID when another
catalog row has the same inferred song identity—for example, an original and a
credited remix. The generic inference uses canonical titles, explicit version
and feature labels, stable source IDs, exact audio fingerprints, and shared
named artist credits; it does not contain song-specific aliases or use broad
fuzzy title similarity. An unrelated cover with the same title remains a
separate family. **Keep as separate recording** or a manual family link prevents
future automatic reassignment. **Collection
integrity** presents conservative duplicate
matches for review; merging combines catalog references while deliberately
leaving the unused WAV on disk, and **Keep as separate recording** assigns a new
family when two similar tracks are genuinely different.
Exact normalized artist/title matches also converge automatically when a track
is imported, rescanned, or saved with corrected metadata. Harmless title
spacing differences such as `Funkytown` and `Funky Town` share one recording
family. Permanent catalog row IDs are never rewritten; the shared family ID is
the identity used to prevent the same song from appearing twice in Set Builder.
The Review page presents one **Accept option** button per candidate and permits
one selected intro plus one selected outro; choosing another option replaces the
earlier selection for that side. After both
sides are selected, **Reprocess with selected candidates** rebuilds the track and
removes that decision from Review. **Dismiss review** rejects an accidental or
unwanted review request without deleting the processed track from Library. If an
older review predates the audition-file behavior, use
**Regenerate auditions** once.

If none of the ranked options works, open **Build my own** beside the intro or
outro candidates. Enter a source start/end, optionally snap the region to an
approximate 4/4 bar grid from the detected BPM, choose 1–8 copies, and audition
that region through the source player. **Use custom candidate** makes the region
part of the combined reprocess decision; the normal boundary optimizer still
micro-adjusts the rendered splice. **Preserve original** disables extension for
that side, so a custom intro can be paired with an untouched outro or vice versa.
The approximate-bar field is editable in both directions: changing timestamps
recalculates bars, while changing bars resizes the selection end, waveform
region, duration, and added-audio estimate from the detected BPM.

The custom editor also supports one **Insert this section elsewhere** block per
generation. Its second waveform represents the current extended arrangement:
click or drag its orange destination marker, optionally snap that timestamp to
the detected bar grid, choose the number of source copies, and decide whether
the source region should also remain the custom intro/outro. The rendered
insertion uses short click-safe joins, shifts later exported cues, and adds an
`Inserted Section` loop marker to the cue sheet and Rekordbox XML.
Use **Preview placement** before reprocessing to hear destination context, every
selected copy of the inserted phrase, and the music that follows it.
The custom destination editor also calculates a cached **transition preflight**
score. Its grid, harmony, energy, bass, rhythm, and optional vocal checks cover
the entry into the inserted phrase, joins between copies, and the return to the
destination context. Treat the percentage as a warning aid and confirm the edit
with the placement preview before rendering.

The upload form also offers **Auto (recommended)** independently for intro and
outro length. Auto starts from the configured bar count but unlocks that side so
the musical analysis may shorten it to a safer supported length. Selecting a
number keeps that exact bar count locked; selecting **None** disables that side.

The **Model Insights** workspace separates **Diagnostics** from **Feedback**. It
renders persistent technical analysis as a searchable, filterable dashboard
with summary counts and expandable intro/outro scores, safeguards,
classifications, plus listening decisions and feedback trends. It deliberately does not
own versions or downloads; those remain in Library.
The JSON endpoint remains available at `/api/report` for integrations, but it is
not the primary user interface.

The **Downloads** workspace is the intake layer for the DJ library. Select any
available WAVs and choose **Analyze selected** to create analysis-only jobs in
Workspace. These jobs calculate BPM, beat grid, key, Camelot-compatible key
data, energy, timing, structure, cues, and compatibility signals, then add the
tracks to Library without generating extended WAVs. From Library, choose
**Extend track** later to configure an intro/outro generation using the cached
analysis.

The **Settings** workspace manages defaults for new web jobs, including preset,
bar counts, stems, automatic length selection, intro/outro quality floors, bit
depth, preview context, cue export, and the **Music Library Location** used by
newly downloaded WAV files. The default is
`~/Music/AudioExtender Library`; every imported master is organized below its
genre. Latin music uses a two-level hierarchy such as `Latin/Reggaeton`,
`Latin/Salsa`, `Latin/Cumbia`, `Latin/Merengue`, `Latin/Zapateado`,
`Latin/Corridos`, `Latin/Regional Mexican`, `Latin/Bachata`, `Latin/Dembow`,
`Latin/Latin House`, `Latin/Latin Jazz`, `Latin/Bolero`, `Latin/Vallenato`, and
`Latin/Brazilian`. Unresolved Latin tags use `Latin/Other`. Playlist
membership remains searchable metadata in the
app instead of creating duplicate playlist folders. Re-importing the same
YouTube recording reuses its existing WAV and adds the new playlist membership.
Single imports without genre metadata use `Other`. Changing
the location affects future imports and does not move existing files. Enter an
absolute path (a leading `~` is supported). Only values that differ from the Python
application defaults are saved. **Reset to application defaults** deletes those
web overrides, so removing a customization always falls back to the maintained
values in `audioextender/core/defaults.py`. Individual choices on the upload form still apply only
to that submitted batch.

Settings also includes **Backup & restore**. A recovery archive protects the
SQLite catalog and job history, settings, verified keys, feedback, recording
identities, processing report, presets, track overrides, library identity,
source sidecars, and saved playlists. Song WAVs are intentionally not copied;
their durable catalog paths allow the app to reconnect them after restoration
or library relocation. The rebuildable analysis cache can be included when a
larger, faster-to-resume backup is worth the extra space. Every archive contains
a SHA-256 manifest and is validated before it is offered for restore. Restoring
requires an explicit confirmation and first creates a new pre-restore backup,
so the operation always has a rollback point. Automatic retention can keep the
newest 3, 5, 10, or 25 archives under `workspace/output/backups`.

Import source metadata is kept under the hidden
`<Music Library Location>/.audioextender/sources` directory. Genre folders
therefore contain only playable WAV files; the hidden metadata remains available
for duplicate detection and catalog recovery.

Completed web jobs additionally provide:

- full source/extended playback with synchronized A/B switching;
- an RMS loudness-envelope waveform with generated cue markers and musical
  arrangement lanes;
- opt-in three-candidate intro/outro reviews with independent phrase, loop, and
  transition scores in the separate Review workspace;
- single-choice candidate feedback, tags, and notes, persisted in SQLite and appended to
  `Candidate Feedback.md`;
- combined candidate reprocessing and per-track generation history;
- retry, cancel, queue reordering, safe removal, estimated queue time, and a
  long-running-analysis notice;
- visual intro/outro boundary overrides backed by `track_overrides.json`;
- feedback acceptance analytics and common rejection tags; and
- downloadable cue sheets and per-generation Rekordbox XML files.

The web queue is stored locally in `workspace/output/reports/audioextender.sqlite3`. Audio
continues to use the existing `workspace/input/`, `workspace/output/wav/`, and `workspace/output/extended/`
folders, so web and CLI results stay compatible.

The processing queue shows active, queued, failed, and canceled jobs. The
separate **Library** workspace is the download archive: it
groups generations by track, plays the newest edit, shows whether its candidates
were automatic or manually chosen, exposes its latest scores and timestamp, and
keeps older generations inside a version-history disclosure. Select any number
of newest edits—or select all—then choose Extended WAV, Source WAV, cue sheet,
Rekordbox XML, previews, and/or a JSON analysis report. The selected files are
grouped by type in one ZIP archive with an export summary listing unavailable
files that were skipped.

Library filters support title search, detected editing category, preset, and
edit result. Categories such as `rhythm-forward`, `slow/dynamic`, or
`live/acoustic` are DJ Library Studio analysis classifications—not authoritative
commercial genre tags—so they remain useful even when a source file has no
embedded genre metadata.

New web generations are immutable under
`workspace/output/versions/<track>/job-<id>/`; the familiar file under `workspace/output/extended/`
remains the convenient latest-result alias. This prevents a later reprocess from
changing the audio served by an older generation. Jobs created before versioned
storage are labeled **Legacy shared output** because their historical bytes were
already overwritten and cannot be reconstructed without reprocessing.

An explicit candidate choice in Review is authoritative: automatic quality and
arrangement thresholds remain visible as warnings and scores, but no longer
discard the user's chosen option. Automatic processing continues to enforce all
safety thresholds normally.

## Usage

The easiest workflow is to place one or many songs in `workspace/input/`, then run:

```bash
python3 -m audioextender
```

Every MP3, WAV, FLAC, AIF, and AIFF file directly inside `workspace/input/` is processed.
Every completed track produces two 24-bit WAV files:

```text
workspace/output/wav/Song Name.wav
workspace/output/extended/Song Name (Extended Edit).wav
```

The file under `wav/` is a format conversion only: stereo, source sample rate,
and no arrangement edits or normalization beyond emergency clipping protection.
The file under `extended/` contains the generated DJ intro/outro.

### Candidate listening feedback

Run a focused listening review with:

```bash
python3 -m audioextender "workspace/input/Song.mp3" --review --overwrite
```

This generates contextual previews, asks which intro and outro candidate to use,
and captures optional reason tags and notes. Results are appended to
`workspace/output/reports/Candidate Feedback.md`.

The feedback file is append-only: DJ Library Studio never regenerates or rewrites an
existing section, so selections, checkboxes, and notes you edit by hand remain
intact. An unchanged candidate set is not duplicated. If an override or scoring
improvement produces different candidates, a new timestamped generation is
appended beneath the earlier review.

| Candidate measurement | Interpretation                                                                                                     |
| --------------------- | ------------------------------------------------------------------------------------------------------------------ |
| Phrase suitability    | Whether the material belongs in an intro/outro based on arrangement role, vocals, stability, and buildup behavior. |
| Loop compatibility    | Whether the candidate's end can repeat into its beginning without an obvious seam.                                 |
| Transition quality    | Whether it flows into the surrounding original song without a bass, chord, energy, or beat-grid discontinuity.     |

The `Checks` column explains risks such as an interrupted buildup, bass reset,
vocal pickup, harmonic resolution, or uncertain beat boundary. A style-aware
second-stage reranker uses these independent measurements: slow, vocal, and
subtle tracks emphasize phrase and transition quality, while club tracks give
more weight to rhythmic loop reliability. This reranker remains deterministic
and explainable; accumulated feedback can train a personalized statistical
reranker later.

### Command reference

All options can be combined in one command. Boundary timestamps are source-song
times expressed in seconds; decimals are accepted, such as `12.5`.

| Command or option                     |                    Accepted value |                               Default | What it does                                                                                                                                                          |
| ------------------------------------- | --------------------------------: | ------------------------------------: | --------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `python3 -m audioextender`            |                                 — |                                     — | Processes every supported song directly inside `workspace/input/`.                                                                                                    |
| `python3 -m audioextender "song.mp3"` |            One or more file paths |              `workspace/input/` batch | Processes only the named file or files. Quote paths containing spaces.                                                                                                |
| `--intro-bars`                        | `0`, `2`, `4`, `8`, `16`, or `32` | From `audioextender/core/defaults.py` | Sets the added intro length. `0` disables the intro extension.                                                                                                        |
| `--outro-bars`                        | `0`, `2`, `4`, `8`, `16`, or `32` | From `audioextender/core/defaults.py` | Sets the added outro length. `0` preserves the original ending without an added outro.                                                                                |
| `--auto-bars` / `--no-auto-bars`      |                    Flag; no value |                                    On | Enables automatic length selection for sides without an explicit bar count, or restores fixed defaults.                                                               |
| `--preset`                            |   `auto` or a named profile below |                                  None | Detects or applies a coordinated editing strategy. Explicit bar and stem options take priority.                                                                       |
| `--intro-before`                      |                  Positive seconds |                                  None | Requires selected intro material to end by this source timestamp.                                                                                                     |
| `--outro-after`                       |                  Positive seconds |                                  None | Requires selected outro material to begin at or after this source timestamp.                                                                                          |
| `--outro-before`                      |                  Positive seconds |                                  None | Requires selected outro material to end by this source timestamp.                                                                                                     |
| `--use-stems` / `--no-use-stems`      |                    Flag; no value |                  From preset/settings | Enables or disables Demucs vocal scoring and automatic sustained-vocal boundaries.                                                                                    |
| `--input-dir`                         |                       Folder path |                             `./input` | Changes the folder scanned when no individual input files are supplied.                                                                                               |
| `--output-dir`                        |                       Folder path |                            `./output` | Changes where completed WAV files are written.                                                                                                                        |
| `--bit-depth`                         |                      `16` or `24` |                                  `24` | Selects the output WAV PCM bit depth.                                                                                                                                 |
| `--workers`                           |          `auto`, `1`, `2`, or `3` |                                `auto` | Controls how many songs are processed concurrently. Automatic Demucs mode uses one worker.                                                                            |
| `--overwrite`                         |                    Flag; no value |                                   Off | Replaces existing extended-edit files instead of skipping them.                                                                                                       |
| `--overrides`                         |                    JSON file path |              `./track_overrides.json` | Loads musical boundaries from a different overrides file.                                                                                                             |
| `--no-cache`                          |                    Flag; no value |                                   Off | Runs without reading or writing cached analysis.                                                                                                                      |
| `--refresh-cache`                     |                    Flag; no value |                                   Off | Recomputes analysis and replaces the applicable cache entries.                                                                                                        |
| `--clear-cache`                       |                    Flag; no value |                                   Off | Deletes AudioExtender cache entries and exits without processing songs.                                                                                               |
| `--cache-dir`                         |                       Folder path |                             `./cache` | Uses a different analysis-cache folder.                                                                                                                               |
| `--previews`                          |                    Flag; no value |                                   Off | Writes intro/outro splice previews in addition to the full extended WAV.                                                                                              |
| `--preview-only`                      |                    Flag; no value |                                   Off | Writes splice previews without exporting the full extended WAV.                                                                                                       |
| `--preview-seconds`                   |                  Positive seconds |                                   `8` | Sets how much audio appears before and after each previewed splice.                                                                                                   |
| `--intro-candidate`                   |             `0`, `1`, `2`, or `3` |                                   `1` | Uses a ranked intro alternative; `0` rejects every intro candidate.                                                                                                   |
| `--outro-candidate`                   |             `0`, `1`, `2`, or `3` |                                   `1` | Uses a ranked outro alternative; `0` rejects every outro candidate.                                                                                                   |
| `--choose-candidates`                 |                    Flag; no value |                                   Off | Displays three ranked options at a time. Choose `1–3`, `0` for none, `R` for the next page, or `C` for a custom source-time range. Forces one worker.                 |
| `--review`                            |                    Flag; no value |                                   Off | Auditions candidates interactively, records reason tags and notes, and appends the generation to `workspace/output/reports/Candidate Feedback.md`. Forces one worker. |
| `--cues` / `--no-cues`                |                    Flag; no value |                                    On | Enables companion JSON cue sheets and Rekordbox XML, or disables both.                                                                                                |
| `--help` or `-h`                      |                                 — |                                     — | Displays the built-in command help.                                                                                                                                   |

### Common commands

| Goal                                        | Command                                                                                       |
| ------------------------------------------- | --------------------------------------------------------------------------------------------- |
| Process everything in `workspace/input/`    | `python3 -m audioextender`                                                                    |
| Process one song                            | `python3 -m audioextender "workspace/input/Song.mp3"`                                         |
| Process several named songs                 | `python3 -m audioextender "Song One.mp3" "Song Two.flac" "Song Three.aiff"`                   |
| Make an 8-bar intro and 8-bar outro         | `python3 -m audioextender --intro-bars 8 --outro-bars 8`                                      |
| Make a short 4-bar intro only               | `python3 -m audioextender --intro-bars 4 --outro-bars 0`                                      |
| Make a minimal 2-bar extension              | `python3 -m audioextender --intro-bars 2 --outro-bars 2`                                      |
| Make an intro only                          | `python3 -m audioextender --intro-bars 16 --outro-bars 0`                                     |
| Make an outro only                          | `python3 -m audioextender --intro-bars 0 --outro-bars 16`                                     |
| Preserve both sides and only convert to WAV | `python3 -m audioextender --intro-bars 0 --outro-bars 0`                                      |
| Keep intro material before 12 seconds       | `python3 -m audioextender "workspace/input/Song.mp3" --intro-before 12`                       |
| Keep outro material after 3:00              | `python3 -m audioextender "workspace/input/Song.mp3" --outro-after 180`                       |
| Keep outro material before 3:25             | `python3 -m audioextender "workspace/input/Song.mp3" --outro-before 205`                      |
| Restrict outro material to 3:00–3:25        | `python3 -m audioextender "workspace/input/Song.mp3" --outro-after 180 --outro-before 205`    |
| Enable Demucs vocal analysis                | `python3 -m audioextender --use-stems`                                                        |
| Rebuild existing results                    | `python3 -m audioextender --overwrite`                                                        |
| Process with two workers                    | `python3 -m audioextender --workers 2`                                                        |
| Use custom input and output folders         | `python3 -m audioextender --input-dir "/Music/Input" --output-dir "/Music/Edits"`             |
| Export 16-bit WAV                           | `python3 -m audioextender --bit-depth 16`                                                     |
| Use another override file                   | `python3 -m audioextender --overrides "/path/to/rules.json"`                                  |
| Use a vocal-safe profile                    | `python3 -m audioextender --preset vocal-safe`                                                |
| Detect the editing profile automatically    | `python3 -m audioextender --preset auto`                                                      |
| Ignore cached data once                     | `python3 -m audioextender --no-cache`                                                         |
| Rebuild cached analysis                     | `python3 -m audioextender --refresh-cache --overwrite`                                        |
| Delete all cached analysis                  | `python3 -m audioextender --clear-cache`                                                      |
| Export full edits and splice previews       | `python3 -m audioextender --previews`                                                         |
| Export only splice previews                 | `python3 -m audioextender --preview-only`                                                     |
| Use 10 seconds around each splice           | `python3 -m audioextender --previews --preview-seconds 10`                                    |
| Choose ranked alternatives interactively    | `python3 -m audioextender "workspace/input/Song.mp3" --choose-candidates`                     |
| Let the tool choose extension lengths       | `python3 -m audioextender "workspace/input/Song.mp3" --auto-bars`                             |
| Use the fixed configured defaults           | `python3 -m audioextender "workspace/input/Song.mp3" --no-auto-bars`                          |
| Use candidate 2 without prompting           | `python3 -m audioextender "workspace/input/Song.mp3" --intro-candidate 2 --outro-candidate 2` |
| Reject every ranked intro choice            | `python3 -m audioextender "workspace/input/Song.mp3" --intro-candidate 0`                     |

### Preset profiles

| Preset          |  Intro/outro |   Demucs |         Quality floor | Intended use                                                                                       |
| --------------- | -----------: | -------: | --------------------: | -------------------------------------------------------------------------------------------------- |
| `auto`          |     Detected | Optional | From selected profile | Chooses a profile from rhythmic, dynamic, harmonic, timing, and optional vocal analysis.           |
| `club`          | 16 / 16 bars |       No |                   45% | Longer, conventional DJ phrasing for rhythm-forward tracks.                                        |
| `subtle`        |   4 / 4 bars |       No |                   58% | Short additions with no repeated loop unit.                                                        |
| `slow-song`     |   4 / 0 bars |       No |                   62% | Conservative intro-only treatment for slower or less electronic music.                             |
| `vocal-safe`    |   8 / 0 bars |      Yes |                   60% | Demucs-aware intro with the original ending preserved.                                             |
| `melodic`       |   4 / 4 bars |       No |                   68% | Harmonic, steady material where short, non-repeating additions are safer.                          |
| `breakbeat`     |   8 / 8 bars |       No |                   67% | Syncopated or broken-beat tracks that need shorter repetition than four-on-the-floor club music.   |
| `peak-time`     | 16 / 16 bars |       No |                   65% | Fast, high-percussion, stable-grid tracks suited to conventional long DJ phrasing.                 |
| `live-acoustic` |   2 / 0 bars |       No |                   72% | Tempo-variable or live-feeling material; preserves the ending and permits only a very short intro. |
| `ambient`       |   2 / 0 bars |       No |                   72% | Sparse, low-percussion material where repetition is especially exposed.                            |
| `intro-only`    |   8 / 0 bars |       No |                   50% | General intro extension without altering the ending.                                               |
| `outro-only`    |   0 / 8 bars |       No |                   50% | General outro extension without altering the opening.                                              |

The quality floor is a safety rule: if the best candidate scores below it, that
side is disabled rather than forcing a questionable loop. Presets also limit how
many times a short unit may repeat. You can override lengths while retaining the
rest of a preset, for example:

```bash
python3 -m audioextender "workspace/input/Song.mp3" --preset slow-song --intro-bars 2
```

Automatic mode evaluates BPM, normalized percussion and harmonic strength,
beat-grid confidence, tempo drift, groove, onset activity and consistency, and
whole-track dynamic range. It can classify tracks as `peak-energy`,
`rhythm-forward`, `breakbeat/syncopated`, `melodic-steady`, `ambient/sparse`,
`live/acoustic`, `slow/dynamic`, or `mixed/subtle`. When Demucs is explicitly
enabled, vocal density can take priority and select `vocal-forward` / `vocal-safe`:

```bash
python3 -m audioextender --preset auto
python3 -m audioextender --preset auto --use-stems
```

Each new analysis also classifies three broad arrangement regions: **Opening**,
**Main body**, and **Ending**. Their boundaries are aligned to the inferred bar
grid, and each region is labeled from its local energy, percussion, harmonic,
onset, and optional vocal-stem measurements. These section profiles appear in
the processing report with timestamps and confidence scores. Older report
entries gain them the next time the track is reprocessed.

Candidate ranking uses the same regional measurements. Intro material is
compared with the detected Opening behavior and outro material with the Ending.
Candidates lose ranking weight when their energy, percussion, harmony, onset,
or vocals conflict with the target region, or when the candidate crosses a
broad musical boundary. The report exposes **regional compatibility** and
**regional boundary risk** so this decision remains explainable.

The web workspace displays these measurements as an arrangement timeline below
the interactive waveform. Separate color lanes show broad musical behavior,
bar-level structure, and generated intro/outro spans. Hover for timestamps and
confidence; click any segment to seek the shared audio player to its start.

The result report shows the detected style, chosen preset, and the measurements
that drove the decision. `--preset auto --intro-bars 4` still chooses the other
profile settings automatically but keeps the explicit four-bar intro.

### Track override reference

The default override file is
The optional root-level `track_overrides.json` file uses exact
filenames, including extensions. Filename matching is case-insensitive. Each song
can contain any of these fields:

| Field          |            Value | Meaning                                                                                                                            |
| -------------- | ---------------: | ---------------------------------------------------------------------------------------------------------------------------------- |
| `intro_before` | Positive seconds | The selected intro phrase must end at or before this source timestamp. Useful for protecting the first recognizable vocal.         |
| `outro_after`  | Positive seconds | The selected outro phrase must begin at or after this source timestamp. Useful for excluding a late verse or chorus.               |
| `outro_before` | Positive seconds | The selected outro phrase must end at or before this source timestamp. The original closing section after it then plays naturally. |

Example with several different rule styles:

```json
{
  "DtMF.mp3": {
    "intro_before": 12.0
  },
  "Song With Protected Ending.mp3": {
    "outro_before": 205.0
  },
  "Song With Exact Outro Range.flac": {
    "intro_before": 18.5,
    "outro_after": 180.0,
    "outro_before": 205.0
  }
}
```

Rules apply automatically during both individual and batch processing. A CLI
boundary overrides the matching JSON field for that run. For example,
`--intro-before 10` replaces every selected song's JSON `intro_before` value,
while its JSON outro fields remain active. When both `outro_after` and
`outro_before` are present, `outro_after` must be earlier than `outro_before`.
Bar counts are command options and are not currently stored in the overrides
file. Supported lengths are 2, 4, 8, 16, and 32 bars; use zero when you want to
disable that side of the extension.

### Analysis cache

DJ Library Studio caches expensive feature analysis in `workspace/cache/`. The first run still
performs normal analysis; later runs of the same unchanged source can reuse it and
proceed quickly to phrase selection and export. Demucs-derived vocal measurements
are cached separately, so they can also be reused without repeating stem
separation. Temporary full stem audio is still removed.

Changing intro/outro bars, presets, boundaries, bit depth, or the output folder
does not invalidate analysis because those choices do not change the underlying
audio features. Cache entries automatically change when any of these do:

- Source path, file size, or modification time
- Beats-per-bar setting
- Analysis hop length
- Internal cache schema version

Use `--refresh-cache` after changing analysis code or when you suspect stale
results. Use `--no-cache` for a one-off uncached run. Use `--clear-cache` to remove
all `.npz` entries from the selected cache folder and exit. The cache is optional,
ignored by Git, and safe to delete; it never contains your source audio.

### Splice previews

Use previews to audition edited transitions without searching through the full
song:

```bash
python3 -m audioextender "workspace/input/Song.mp3" --previews
python3 -m audioextender "workspace/input/Song.mp3" --preview-only
python3 -m audioextender "workspace/input/Song.mp3" --previews --preview-seconds 10
```

Review files are organized below the output folder while finished edits remain at
the top level:

```text
workspace/output/
├── Song (Extended Edit).wav
└── previews/
    └── Song/
        ├── Intro Preview.wav
        └── Outro Preview.wav
```

Every preview auditions the complete inserted section in musical context:

```text
Intro: original lead-in (if any) → complete added intro → original next section
Outro: original lead-in          → complete added outro → original ending (if any)
```

The original context on each side uses `--preview-seconds`. The inserted section
is always included in full, so a 16-bar preview can be substantially longer than
twice the context setting. This lets you judge entry into the loop, repetition
inside it, and the return to the untouched song. If one side is disabled or
rejected by a safety rule, no preview is created for that side. Preview-only mode
does not replace or write the full extended WAV.

### Ranked candidate choices

For every enabled intro and outro, DJ Library Studio ranks three musically distinct
locations by default. Normal runs automatically use candidate 1. Interactive
runs keep a larger pool available in pages of three. Overlapping
versions of the same location are filtered so alternatives represent genuinely
different parts of the song whenever enough options exist.

To see the choices and select them in the terminal:

```bash
python3 -m audioextender "workspace/input/Song.mp3" --choose-candidates
```

Each option shows its source timestamps, loop quality, energy shape, buildup
risk, bass-reset risk, and unique bar count. Before each prompt, DJ Library Studio
writes `Intro Candidate 1.wav` through candidate 3 inside
`workspace/output/previews/Song/`. Outro candidates use the same folder. Listen to them
while the prompt is waiting. Press Enter for the best option on the current page,
type `1`, `2`, or `3`, enter `0` for no extension, or type `R` to reject that page
and audition the next three. The same three preview filenames are overwritten on
each page, so the output folder does not accumulate every rejected option. Type
`C` to enter a preferred source start/end such as `12`, `12.5`, or `1:05`; the
tool snaps it to the nearest analyzed, bar-aligned candidate. Interactive mode
uses one worker to keep prompts readable.

For scripts and repeatable batches, select ranks without prompting:

```bash
python3 -m audioextender "workspace/input/Song.mp3" --intro-candidate 2
python3 -m audioextender --intro-candidate 2 --outro-candidate 3
python3 -m audioextender "workspace/input/Song.mp3" --intro-candidate 0 --outro-candidate 0
```

If fewer than the requested number of distinct candidates exist, the song fails
with a clear message instead of silently choosing a different rank. Candidate
ranking reuses cached analysis, so trying another rank normally avoids the
expensive feature and Demucs stages.

One bad or unusually short track will not stop the rest of a batch. A summary
reports created, skipped, and failed files. Existing outputs are skipped by
default so rerunning a batch does not waste time. Use `--overwrite` to rebuild
them.

Batch processing automatically chooses one, two, or three worker processes using
the Mac's physical memory plus each song's decoded duration, sample rate, channel
count, and estimated analysis working size. It keeps most memory available for
macOS and other applications. Automatic mode uses one worker with Demucs because
stem separation is substantially heavier. You can override the decision:

```bash
python3 -m audioextender --workers 1
python3 -m audioextender --workers 2
python3 -m audioextender --workers 3
```

Interactive terminals show a compact three-line display:

```text
Batch [████████░░░░░░░░░░░░░░] 2/5 · ETA ~03:41 · workers 3
Song  [██████████████░░░░░░░░] 64% · Babydoll.mp3 · Separating stems
✓ Load  ✓ Analyze  ◉ Stems  ○ Select  ○ Render  ○ Export
```

The batch ETA blends the current song's progress with measured times from songs
already completed, so it becomes better calibrated during a batch. Demucs gets a
dedicated stem bar and reports `Apple GPU (MPS)` or `CPU`. If a calculation makes
no percentage progress for 15 seconds, `still active` and its elapsed duration
appear instead of leaving a seemingly frozen spinner. Redirected/log output uses
sparse checkpoint lines rather than terminal cursor animation.

When automatic concurrency is lower than the normal three-worker target because
of estimated RAM requirements, the terminal prints a `Memory adjustment` notice
showing the worker reduction. Demucs still uses one automatic worker because its
memory and compute requirements are substantially heavier.

After the batch, the terminal prints only vital song outcomes and total wall-clock
time. The persistent report lists BPM, beat/bar details, selected phrase ranges,
scores, construction decisions, and output filenames.

The report also includes an estimated intro/outro loop-quality percentage, a
beat-grid confidence percentage, and suggested mix-in/mix-out cues. Cue times are
for the generated extended WAV and account for the inserted intro phrase. These
measurements are decision aids rather than guarantees; verify low-confidence grids
and cue positions by ear in Rekordbox.

Automatic bar selection compares every supported nonzero length up to the normal
configured maximum. It combines loop quality, phrase structure, surrounding
energy, stability, instrumentalness, section type, buildup risk, and bass-reset risk. Two-bar
fragments receive a small penalty; 8 bars or more are preferred only for stable,
rhythm-forward material. The results line marks the chosen extension as
`automatic length`. Supplying `--intro-bars` or `--outro-bars` always fixes that
side at the requested length, even while automatic selection remains enabled for
the other side.

### Understanding the processing report

| Report item                            | Meaning                                                                                                                               | How to interpret it                                                                                                                                                                              |
| -------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| `Time`                                 | Wall-clock processing time for that song.                                                                                             | Demucs, longer tracks, and lower analysis hop lengths increase it. It says nothing about edit quality.                                                                                           |
| `BPM`                                  | Estimated tempo used to construct the beat grid.                                                                                      | Compare it with Rekordbox. Half-time and double-time readings can describe the same pulse but change perceived phrase length.                                                                    |
| `Tempo drift`                          | Spread between the track's faster and slower local beat intervals, relative to its median tempo.                                      | Near zero suggests quantized timing. Larger values flag live playing, tempo automation, or an uncertain tracker; projected opening/ending bars use local timing rather than only the global BPM. |
| `beats / bars`                         | Detected beats and inferred 4/4 bars.                                                                                                 | Bars are groups of four beats. The count is approximate because sparse openings and endings may not provide detectable beats.                                                                    |
| `Beat-grid confidence`                 | Confidence that beats are regularly timed, supported by onsets, and assigned a plausible downbeat phase.                              | This measures timing placement—not whether the chosen loop is musically good.                                                                                                                    |
| `Groove`                               | Subdivision pattern inferred between the main beats: `straight`, `swing`, `syncopated`, `loose/syncopated`, or `undetermined`.        | This describes feel; swing and syncopation are not errors and are preserved rather than quantized.                                                                                               |
| `Timing`                               | Interpretation of local tempo movement combined with grid support: `steady`, `mildly variable`, `variable/live`, or `uncertain grid`. | Variable/live can be musically intentional. Uncertain grid indicates that beat evidence itself is weak.                                                                                          |
| `Downbeat continuity`                  | Consistency of beat placement, onset support, local timing, and recurring four-beat accent shape across bars.                         | Higher means inferred beat one remains convincing throughout the song.                                                                                                                           |
| `Preset`                               | Manual profile or profile selected by `--preset auto`.                                                                                | Automatic reports use the form `auto → club`. Explicit bar options may still override its lengths.                                                                                               |
| `Detected style`                       | Heuristic style used by automatic mode.                                                                                               | Its reason lists measurements such as percussion, grid confidence, and dynamics. It is an editing strategy, not a genre label.                                                                   |
| `Intro` / `Outro` times                | Start and end of the selected phrase in the original source.                                                                          | These are source timestamps, not positions in the longer exported WAV.                                                                                                                           |
| `Estimated key`                        | Global major/minor key inferred from the track's chroma distribution.                                                                 | Higher confidence means one tonal profile separated clearly from alternatives. Modulation, borrowed chords, sparse harmony, and percussion can reduce reliability.                               |
| `Loop quality`                         | Combined estimate of seam, harmony, chord return, timbre, bass, stability, structure, fills, pickups, and energy behavior.            | It evaluates the artificial loop-back transition, but cannot guarantee that repetition is artistically tasteful.                                                                                 |
| `Energy`                               | Arrangement shape across the selected phrase and its surrounding bars.                                                                | Reported as `stable`, `buildup`, `losing-bass`, `fading`, or `section-change`. Stable is normally preferred.                                                                                     |
| `Buildup risk`                         | Heuristic 0–100 measure that the phrase is progressing toward a drop or transition.                                                   | Lower is safer. Candidates above the configured limit are disabled.                                                                                                                              |
| `Bass-reset risk`                      | Estimated severity of low-end discontinuity when the phrase loops.                                                                    | Lower is safer. High values correspond to bass entering, withdrawing, or restarting conspicuously.                                                                                               |
| `Context`                              | Energy-flow agreement across four bars before, the candidate, and four bars after.                                                    | Higher means the phrase belongs naturally in its surrounding arrangement.                                                                                                                        |
| `Splice mode`                          | Automatically selected join treatment: `percussion-priority`, `bass-preserving`, `harmonic-tail`, `zero-crossing`, or `adaptive`.     | It controls micro-fade and sustained-tail behavior without moving the edit to different musical bars.                                                                                            |
| `Chord return`                         | Compatibility of the candidate's final-bar harmony with its first-bar harmony, including common cadence motion in the estimated key.  | Higher is safer. Unlike simple chord equality, a dominant-to-tonic return can score well because it forms a musically natural loop.                                                              |
| `Resolution risk`                      | How much more strongly the ending chord appears to lead into the original next bar than back to the loop's beginning.                 | Lower is safer. High risk identifies phrases that sound unfinished when reset, even if the cut itself is clean.                                                                                  |
| `Section`                              | Approximate arrangement role inferred bar by bar: `intro`, `verse`, `chorus`, `breakdown`, `buildup`, `drop`, `closing`, or `fade`.   | Intro selection favors `intro`; outro selection favors `closing` and gentle `fade` material. Peaks, drops, and buildups are penalized when used in the wrong role.                               |
| `Section confidence`                   | Strength and consistency of the dominant section label across the selected bars.                                                      | A low value means the candidate crosses labels or has ambiguous energy behavior, so treat the label cautiously.                                                                                  |
| `Arrangement fit`                      | Signed score showing whether that section type suits its intended intro/outro role.                                                   | Positive is favorable, zero is neutral, and negative means the candidate resembles the wrong part of the song. It is one ranking factor, not a hard rejection.                                   |
| `Local grid`                           | Average rhythmic-grid confidence across the candidate's bars.                                                                         | Lower values indicate sparse or ambiguous beats inside the phrase.                                                                                                                               |
| `Boundary grid`                        | Confidence of the weaker first or last candidate bar.                                                                                 | This specifically guards the loop splice from landing on a displaced or poorly supported bar boundary.                                                                                           |
| `Instrumental`                         | Percussion-to-mix ratio used as an instrumentalness proxy.                                                                            | Higher values favor drum-led material. It is not a probability that vocals are absent; Demucs is more reliable for vocals.                                                                       |
| `Vocal coverage`                       | Proportion of the selected candidate classified as sustained vocal activity.                                                          | Lower is safer for repetition. Candidates above the configured maximum are disabled.                                                                                                             |
| `Boundary risk`                        | Vocal activity immediately around the phrase's start or end.                                                                          | High values suggest a clipped lyric, sustained word, or vocal pickup crossing the artificial splice.                                                                                             |
| `Stem separation reliability`          | Similarity between the time-aligned sum of Demucs stems and the decoded source.                                                       | Instrumental construction requires the configured minimum; lower values keep the full mix. This measures reconstruction, not artistic isolation quality.                                         |
| `Construction`                         | Whether added copies use the `full mix` or `instrumental stems`.                                                                      | Only the repeated extension changes. Untouched portions always use the original source audio.                                                                                                    |
| `Instrumental construction quality`    | Loop-quality estimate with penalties caused solely by removed vocals excluded.                                                        | Use this instead of the full-mix quality when the report says `instrumental stems`.                                                                                                              |
| `Unique material / extension / copies` | Unique source length, total added length, and copy count.                                                                             | `8 / 16 / 2` means two compatible four-bar halves form an eight-bar unit that is copied twice. More unique bars and fewer copies usually sound less mechanical.                                  |
| `Protected vocal entrance`             | Active `intro_before` boundary, automatic or manual.                                                                                  | Intro material cannot extend beyond this source timestamp.                                                                                                                                       |
| `Protected vocal release`              | Active `outro_after` boundary, automatic or manual.                                                                                   | Outro material cannot begin before this source timestamp.                                                                                                                                        |
| `Protected closing section`            | Active `outro_before` boundary.                                                                                                       | Outro material must end by this time so the recognizable closing section continues naturally.                                                                                                    |
| `Suggested cues`                       | Suggested mix-in and mix-out positions in the completed WAV.                                                                          | These account for inserted audio. Confirm them in Rekordbox before performing.                                                                                                                   |
| `Created / Skipped / Failed`           | Batch result counts.                                                                                                                  | Skipped normally means an output existed; use `--overwrite` to rebuild it.                                                                                                                       |

#### Beat-grid confidence ranges

|  Confidence | Practical interpretation                                                                         |
| ----------: | ------------------------------------------------------------------------------------------------ |
|   `80–100%` | Strong, steady grid. Usually reliable, but still verify beat one.                                |
|    `60–79%` | Generally usable. Check the first downbeat and several later phrases in Rekordbox.               |
|    `40–59%` | Uncertain. Sparse drums, syncopation, live timing, or tempo movement may be affecting detection. |
| Below `40%` | Treat the grid as unreliable and verify it manually before trusting an edit.                     |

Downbeat phase is inferred from recurring four-beat accent patterns across many
bars, not simply the loudest individual beat. This is still an approximation;
syncopated music and songs whose first strong beat is not beat one should be
checked in Rekordbox.

#### Tempo-drift ranges

|      Drift | Practical interpretation                                                  |
| ---------: | ------------------------------------------------------------------------- |
| Below `3%` | Usually steady or quantized.                                              |
|     `3–8%` | Mild movement, expressive timing, or occasional tracker variation.        |
| Above `8%` | Variable-tempo/live material or a grid that deserves manual verification. |

These are diagnostics, not quality grades. Syncopation and sparse percussion can
inflate the measurement even when the recording itself has a steady tempo.

#### Arrangement-section limitations

Section labels are inferred from bar position, loudness, drums, harmonic energy,
onset activity, and short-term energy direction. They do not recognize lyrics or
know the artist's intended narrative. Unusual forms, ambient openings, repeated
choruses, and songs without clear energy changes can be mislabeled. Use
`--choose-candidates` when section confidence is low or the song has a distinctive
arrangement.

### Automatic fallback behavior

When automatically selected candidate 1 violates a vocal, buildup, bass-reset,
arrangement, or preset-quality safety rule, DJ Library Studio first checks the other
ranked locations at the same extension length. If the length was also selected
automatically, it then tries progressively shorter bar counts. Every replacement
must pass the normal safety rules and `MINIMUM_FALLBACK_LOOP_QUALITY`.

The report records both the rejected reason and the chosen recovery, for example:

```text
Fallback: rejected section chorus, fit -53%; alternate candidate 2 at the same length
```

If no safe recovery exists, that extension is disabled and the original audio is
preserved. A non-default rank selected with `--intro-candidate` or
`--outro-candidate`, or any choice made through `--choose-candidates`, is
considered intentional and is not silently replaced; existing hard safety checks
can still disable it.

#### Loop-quality ranges

|     Quality | Practical interpretation                                                                      |
| ----------: | --------------------------------------------------------------------------------------------- |
|   `85–100%` | Excellent measured seam compatibility. Still audition for repetition and recognizable lyrics. |
|    `70–84%` | Strong candidate that will usually splice cleanly.                                            |
|    `55–69%` | Potentially usable, but audition it carefully.                                                |
|    `40–54%` | Weak or context-dependent; a buildup, chord change, bass reset, or pickup may remain audible. |
| Below `40%` | Poor candidate. Prefer another range, a shorter edit, or disabling that side.                 |

#### Instrumentalness ranges

|        Value | Practical interpretation                                                               |
| -----------: | -------------------------------------------------------------------------------------- |
|  `0.75–1.00` | Strongly percussion-led according to the mix-only proxy.                               |
|  `0.55–0.74` | Mixed material with useful rhythm but potentially prominent harmonic or vocal content. |
|  `0.35–0.54` | Harmonic, melodic, vocal, or relatively drum-light material.                           |
| Below `0.35` | Usually a poor conventional DJ loop unless an ambient or very subtle edit is intended. |

The temporary `score=...` shown during candidate selection is an internal ranking
value, not a percentage. It can be negative and is only meaningful when comparing
candidates from the same song and position. Use `loop quality` for the calibrated
0–100 summary.

#### Automatic-style reason values

| Measurement     |               Scale | Practical interpretation                                                                                                                                                         |
| --------------- | ------------------: | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `percussion`    | Usually `0.00–1.00` | Mean normalized drum/percussion energy. Around `0.40` or higher supports a rhythm-forward classification; it is relative to that recording.                                      |
| `grid`          |            `0–100%` | The same beat-grid confidence described above. Automatic mode becomes more conservative below approximately 60%.                                                                 |
| `dynamics`      | Usually `0.00–1.00` | Difference between the track's quiet and loud energy percentiles. Lower values imply a steady arrangement; higher values imply larger builds, breakdowns, or acoustic variation. |
| `vocals occupy` |            `0–100%` | With Demucs, the proportion of analyzed frames containing sustained vocal energy. High density favors `vocal-safe`.                                                              |

The output retains the source sample rate whenever the decoder exposes it, is
always stereo, and is written as PCM WAV. Gain is unchanged unless a constructed
boundary exceeds digital full scale; in that case only the minimum global gain
needed to avoid clipping is applied.

## Rekordbox cues and cue sheets

Normal exports also create:

```text
workspace/output/
├── Song (Extended Edit).wav
├── rekordbox.xml
├── reports/
│   ├── Processing Report.md
│   └── processing_report.json
└── cue_sheets/
    └── Song (Extended Edit).json
```

The JSON file records exact seconds, purpose, confidence, BPM, key, groove, and
grid statistics. The Rekordbox XML contains a `DJ Library Studio Edits` playlist,
one basic 4/4 tempo-grid anchor per track, memory cues, and saved intro/outro
loops. Suggested points include the first reliable downbeat, mix in, return to
the original song, mix out, start of the added outro, and return to the natural
ending. Coincident memory cues are deduplicated, while a saved loop may share a
position with a named memory cue.
`rekordbox.xml` represents the successfully created tracks from the current run;
a later run replaces it rather than merging with an older XML collection.

To import it in Rekordbox, open Preferences and select the generated XML under
the Bridge/Imported Library setting. Open `rekordbox xml` in the browser tree,
open Playlists, and drag `DJ Library Studio Edits` into the normal Playlists area.
The XML uses documented memory cues (`Num=-1`) rather than Hot Cues, so it does
not assign Hot Cue A–H for you. Rekordbox should still analyze each WAV normally;
verify the imported grid and cues before performing. Disable companion exports
with `--no-cues`.

Format and import behavior follow the official
[rekordbox developer XML documentation](https://rekordbox.com/en/support/developer/).

## Persistent processing report

The terminal intentionally shows only the essentials for each completed song:
processing time, BPM, key, intro/outro length and quality, safety warnings, and
mix cues. Full diagnostics are stored in `workspace/output/reports/Processing Report.md`.
The adjacent `processing_report.json` is the durable backing record and can be
used by other tools.

Reports are updated by source filename:

- A newly processed song adds or replaces its record.
- `--overwrite` replaces that song's old measurements with the new result.
- A song skipped because its output already exists keeps its previous analysis
  and is marked `skipped` for the latest run.
- A skipped legacy output with no previous report receives a minimal record;
  processing it once with `--overwrite` fills in the complete analysis.
- Songs not involved in the current command remain in the report unchanged.

The Markdown report begins with a compact library table, followed by detailed
per-song sections covering grid, key, groove, arrangement, harmony, vocals,
construction method, safety decisions, and cue points.

## Optional Demucs support

Demucs is not needed for normal operation. To use vocal-stem analysis and optional
instrumental edit construction:

```bash
python -m pip install -r requirements-demucs.txt
python3 -m audioextender --use-stems
```

The first Demucs run may download a model. Separation is CPU-intensive and can
take several minutes. AudioExtender caches the aligned `drums + bass + other`
instrumental mix as a lossless floating-point WAV alongside the compact analysis
cache. Subsequent runs can therefore construct stem edits without rerunning
Demucs. `--clear-cache` removes both analysis entries and cached instrumentals.
AudioExtender supplies Demucs with the virtual environment's maintained `certifi`
certificate bundle for secure model downloads on Python.org macOS installations.
Demucs's own separation percentage is forwarded into AudioExtender's live progress
bar. On Apple Silicon, use a native ARM64 Python installation; an Intel Python
running through Rosetta can make stem separation dramatically slower and prevents
PyTorch from using Apple's MPS acceleration.
When PyTorch reports MPS as available, AudioExtender explicitly runs Demucs on the
Apple GPU. It falls back to CPU automatically on systems where MPS is unavailable.

When Demucs is enabled, AudioExtender also detects sustained vocal regions. Unless
a manual rule exists, the first sustained vocal entrance becomes the latest intro
boundary and the final sustained vocal release becomes the earliest outro boundary.
The detector smooths brief breaths, ad-libs, and stem leakage. If an automatically
detected boundary leaves no complete loopable phrase, the track falls back to its
normal musical search; explicit CLI and JSON boundaries remain strict.
The same vocal activity map is analyzed at every candidate's exact edges. The
selector distinguishes isolated short activity from sustained phrases, measures
how much of the candidate contains vocals, detects rising vocal pickups near its
end, and penalizes lyrics crossing either splice boundary. If the best remaining
candidate exceeds the safety limits in `audioextender/core/defaults.py`, that extension is disabled
instead of forcing a lyrically awkward repeat.

For audible construction, AudioExtender aligns the separated stems with the
original decode to compensate for MP3 encoder delay, then measures how accurately
all stems reconstruct the source. If reliability clears the configured threshold
and the candidate contains meaningful vocal activity, only `drums + bass + other`
is used for the added repetitions. The untouched original—including its vocals—
returns at the selected phrase boundary. Candidates with little vocal activity,
low separation reliability, or no Demucs data continue using the original full
mix. Reports distinguish `full-mix loop quality` from `instrumental construction
quality` and state which construction was used for each side.

## How it works

1. The source is decoded without resampling and retained as stereo floating-point
   samples for editing.
2. A mono analysis copy is split into harmonic/percussive components. Percussive
   onset strength drives BPM and beat detection.
3. The strongest recurring beat accent estimates the downbeat phase. Beats are
   grouped into 4/4 bars; four-bar candidate steps approximate phrase boundaries.
   When detection begins after a sparse opening, the stable bar period is projected
   backward so pre-vocal opening material remains available on the musical grid.
4. Complete bar-aligned regions in the early and late search windows are scored,
   including bar-smoothed energy, bass-band continuity, 32-band timbral similarity,
   final-bar energy trends, harmonic/chroma compatibility, ending fills, vocal
   pickups, and suitability as a seamless musical loop.
   The selector also compares the first and last four-bar blocks, the bar before
   entry, the bar after exit, and the natural post-phrase release. This helps
   distinguish a stable groove from a buildup intended to lead into another section.
   If a full requested phrase is progressive, a cleaner 4- or 8-bar unit may be
   repeated enough times to preserve the requested 8/16/32-bar extension length.
   When scores are close, the selector now prefers a compatible eight-bar unit
   (two adjacent four-bar phrases in their original order) over repeating one
   four-bar phrase twice. The same rule can prefer a safe 16-bar unit over two
   copies of eight bars. Configurable score, loop-quality, and structural limits
   ensure variety is chosen only when it remains musically competitive.
   Intro candidates are confined to the first 16 detected bars and outro candidates
   to the final 16 detected bars (expanded only when a 32-bar request requires it),
   keeping slower songs out of their first verse and inside their natural ending.
   An intro loop must also begin within the first eight detected bars, preventing a
   short unit from being chosen at the very end of the opening zone.
   Arrangement analysis also examines four bars before and four bars after every
   candidate. It compares energy direction, entry/exit levels, post-phrase jumps,
   and bass movement to classify stable grooves, buildups, bass withdrawals,
   fades, and section changes. High buildup or bass-reset risks can disable an
   extension even when its exact waveform seam appears clean.
5. The best early phrase is repeated immediately before its original occurrence.
   The best late phrase is repeated before the song's untouched natural tail. The
   original slow opening and natural ending therefore stay in the correct order.
   Short adaptive 10–30 ms complementary fades are used only at artificial loop
   seams. Each splice is first shifted by up to 20 ms to find a cleaner waveform
   match while preserving the exact phrase duration and beat alignment.
   Sustained content receives separate treatment: 250–750 ms of the song's real
   post-phrase synth, bass, and reverb continuation is carried across the loop and
   blended into the repeated phrase. Percussion is excluded from this longer blend
   so kicks and other drum transients remain sharp.
   With reliable Demucs stems, added copies containing vocals can instead use the
   aligned instrumental mix while every untouched portion of the song remains the
   original full stereo master.
6. The result is exported to a Rekordbox-friendly stereo PCM WAV.

## Known limitations

- Downbeat detection is heuristic. Syncopated music, live drums, non-4/4 meters,
  tempo changes, and beatless intros can produce an incorrect bar phase.
- Without stems, vocal avoidance is inferred only indirectly. Use `--use-stems`
  when clean instrumental selection matters.
- A phrase that scores well acoustically may not be the most tasteful musical
  choice. Audition the intro-to-song and song-to-outro boundaries before playing
  the edit live.
- The MVP copies source phrases; it does not synthesize drums, time-stretch audio,
  change tempo, or rebuild an instrumental from stems.
- Lossy inputs cannot regain quality when exported to WAV. WAV prevents another
  lossy encoding pass but does not undo MP3 compression.

## Rekordbox workflow

Import the generated WAV, analyze it in Rekordbox, and verify the first downbeat
and phrase grid by ear. Set a memory cue at the start of the added intro and near
the added outro. Because the edit adds audio before the source, previously saved
cue timestamps from the original file will not match the new file.

### Bring Rekordbox star ratings back into Set Builder

Rekordbox cue export and rating synchronization are separate flows. DJ Library
Studio writes cue/playlist XML, but it reads ratings only from a public
collection XML or tab-separated TXT export that you explicitly select; it never
opens or changes the private Rekordbox database.

1. Export the collection from Rekordbox after saving your 1–5 star ratings. XML
   gives the strongest identity matching; the UTF-16 TXT export is also
   supported and uses its exact artist, title, and `Time` duration fields.
2. Open **Settings → Rekordbox ratings** and choose the XML or TXT file.
3. Review exact matches, unchanged ratings, ambiguous rows, and tracks that were
   not found. Ambiguous and unmatched rows are never applied automatically.
4. Select **Apply ratings** to save the reviewed exact matches.

The Settings panel shows the rating distribution and synced tracks. Set Builder
uses `1=-4`, `2=-2`, `3=0`, `4=+2`, and `5=+4` only as bounded preference
evidence. Ratings cannot make an excluded, unavailable, duplicate-family, or
musically unsafe track eligible. Each version retains its own rating, and other
versions remain available as alternatives. **Clear imported ratings** removes
only Rekordbox evidence; local Set Builder feedback is preserved.
