# Set Builder workflow redesign plan

- Status: planned
- Owner: Set Builder
- Implementation item: `SET-UX-001`

## Goal

Make Set Builder feel like a fast editing workspace rather than one long form.
The user should be able to describe a set, generate it, keep the tracks that
work, reject or replace tracks that do not, regenerate only what needs to
change, and understand whether every action was saved.

This redesign preserves the existing bounded catalog, journey planner,
recording-family uniqueness, deterministic validation, AI-versus-baseline
comparison, undo/redo history, saved-set durability, and three-direction mix
health model. It changes workflow ownership and presentation before changing
musical policy.

## Current flow and confirmed friction

The current flow is:

1. Describe or manually define the set.
2. Interpret the intention and edit a detailed journey.
3. Generate tracks.
4. Choose among three directions.
5. Edit tracks, transitions, ratings, feedback, rules, and metadata in one long
   page.
6. Save the set, save a separate review, or export it.

The underlying capabilities are stronger than the workflow makes apparent:

- Saved-set deletion removes the backend and cached record but leaves the
  deleted plan rendered as the active workspace.
- Locked track IDs already reach deterministic and AI planning, but there is no
  first-class command explaining how to regenerate the remaining tracks.
- Keep and Reject only update an in-memory review draft. The choice is not
  durable until the user finds and submits the separate set-review form.
- Reject does not remove or replace the track, so its meaning is ambiguous.
- Mix health has a useful compact summary, but the page repeats the same issues
  as a long list of client and server warnings, sometimes with internal IDs.
- Journey inputs are editable, but the page does not show a dirty state or a
  clear action for applying the revised direction to the current track plan.
- Every track displays playback, explanations, transition controls, feedback,
  movement, locking, replacement, removal, insertion, and identity editing at
  once. This makes frequent actions harder to find.

## Target workflow

### 1. Direction

Keep the initial choice between natural-language and manual authoring, but
reduce the result to a compact, reviewable direction:

- set name and length;
- musical intention summary;
- a three-section journey timeline;
- required, excluded, and mixing constraints;
- one primary **Build set** action.

Detailed interpretation and section fields move into an **Edit direction**
drawer. Editing them marks the direction as changed and shows one explicit
**Update generated set** action. A track rerun must not call intention
interpretation or journey planning again unless the direction itself changed.

### 2. Generated-set workspace

After generation, replace the long form with a workspace containing:

- a sticky header with the set name, Draft/Saved state, current revision, mix
  health, undo/redo, Save, and Export;
- the existing three-direction selector and compact mix-health treatment;
- a compact running order in the main column;
- a track/transition inspector that opens only for the selected row;
- a persistent action bar with **Regenerate unlocked**, **Repair weak mixes**,
  and **Review set**.

Each collapsed track row should show only position, playback, title/artist,
genre, BPM, key, energy, match score, and visible state chips such as **Locked**,
**Kept**, **Rejected**, or **Changed**. The frequent actions are **Lock**,
**Replace**, and **More**. Explanations, transition editing, identity tags,
movement controls, ratings, and advanced metadata belong in the inspector.

### 3. Review and export

Keep overall listening notes and transition ratings as an optional final
**Review & teach Set Builder** step. Track-level Keep/Reject actions must no
longer depend on finding this final form. Export remains unavailable when the
existing hard validation or mix-health release policy says the plan is unsafe.

## Required behavior changes

### Saved-plan deletion

Deleting the currently loaded plan must be transactional:

1. Confirm that the saved plan will be deleted but Library audio will remain.
2. Delete the durable record.
3. Remove it from the saved-plan selector.
4. Clear the active saved-set ID, plan, proposals, locks, review drafts,
   planning receipt, history, and future stack.
5. Return to the clean Direction state and announce **Plan deleted**.

Deleting a different, inactive plan must not reset the current workspace. A
failed delete changes neither the selector nor the active plan.

### Regeneration and locking

Add an explicit **Regenerate unlocked tracks** command. It reuses the current
brief and journey, creates a new plan revision, and sends these constraints to
the existing validated planner:

- locked track IDs and their intended journey sections;
- required tracks;
- rejected or excluded track/version IDs;
- recording-family exclusions;
- the current planning mode and transition settings;
- the base plan revision for audit and conflict detection.

**Lock** means the track must remain in the regenerated set and in its current
journey section. The optimizer may move it within that section when necessary
for a safer transition. A later **Pin exact position** command may be added only
if listening tests show that section-level locking is insufficient.

Before applying a regenerated result, snapshot the current revision. Show how
many tracks stayed, changed, or could not be replaced. Undo restores the entire
prior revision. Locked tracks receive a persistent lock chip and remain locked
after save, reload, and application restart.

Provide two narrower repair commands:

- **Replace rejected tracks** fills only rejected/open slots.
- **Repair weak mixes** searches only positions adjacent to below-target
  transitions while honoring every lock and hard rule.

### Track rejection and replacement

Replace the ambiguous draft-only controls with a complete action:

1. Selecting **Reject** opens a small confirmation panel with an optional
   reason and scope: this version or this recording family.
2. The primary action is **Reject & replace**. A secondary **Reject and leave a
   gap** action remains available under More.
3. Persist the rejection with an idempotent event ID before mutating the plan.
4. Mark the selected version/family unavailable for this plan revision and
   future reruns according to the chosen scope.
5. Insert the highest-ranked validated alternative for the same section and
   recalculate adjacent transitions.
6. Show **Rejected and replaced · feedback saved** with an Undo action.

The replacement row should briefly label what changed. If no valid alternative
exists, keep a visible empty slot with a useful explanation; do not silently
restore the rejected track. If persistence or replacement fails, retain the
original track and show a retryable error.

**Keep** becomes an immediate durable preference event and adds a visible Kept
chip. It does not lock the track automatically: preference and plan structure
remain separate concepts.

### Editing an AI-created direction

The AI-created journey remains fully editable. The compact timeline shows
section name, duration, genres, character, purpose, and energy movement. **Edit
direction** opens all fields in one drawer with validation and reset-to-AI
controls.

After any edit:

- show **Direction changed** in the workspace header;
- preserve the active track plan until the user applies the change;
- offer **Update unlocked tracks** as the primary action;
- disclose which sections are affected;
- preserve locks, required/excluded tracks, and rejection history;
- create a new revision instead of overwriting the prior result.

### Mix-health and warning presentation

Keep the compact presentation shown in the preferred design: overall score,
target, status, and the weakest transitions ordered by severity.

- Show at most the five most important problems initially.
- Group remaining issues by cause: tempo, key, energy, vocals, availability, or
  validation.
- Deduplicate client and server reports by transition pair and issue code.
- Use track positions and names; keep internal catalog IDs in an Advanced
  details disclosure only.
- Clicking an issue selects and scrolls to the affected transition.
- Provide **Repair worst transition** and **Repair all eligible** actions.
- Keep the complete diagnostic list collapsed for troubleshooting and export.

The separate full-page warning wall should be removed after behavioral tests
confirm that the grouped health view exposes every actionable issue.

## State and ownership

Use one explicit planning-workspace state machine:

`direction` → `generating` → `draft-ready` → `direction-dirty` →
`regenerating` → `draft-ready` → `saved`

Failed and canceled operations return to the last stable state. Rendering must
not infer lifecycle state from button text or scattered DOM flags.

Responsibilities remain narrow:

- `planning-session.js`: generation, regeneration, partial repair, cancellation,
  and revision comparison.
- `saved-sets.js`: durable selection, save/load/delete, active-plan identity,
  and reset-after-delete behavior.
- `feedback.js`: durable Keep/Reject commands, reason/scope, and learning status.
- `plan-view.js`: running-order rendering and event delegation only; mutation
  commands move behind controllers.
- a focused workspace controller owns selected track, inspector state, dirty
  direction state, and top-level commands.
- a focused health presenter owns warning normalization, grouping, navigation,
  and repair affordances.

Backend services remain authoritative for candidate eligibility, recording-
family uniqueness, locked/required/excluded validation, and final plan
validation. The browser must never synthesize an invalid replacement merely to
keep the row count full.

## Performance plan

- Reuse the current interpretation and journey when only tracks are rerun.
- Cache bounded candidate pools by catalog revision plus brief/journey hash.
- Use partial replacement for a rejected track or isolated weak transition.
- Run a full AI planning call only for a full unlocked regeneration; local
  deterministic repair remains the fast path for one or two positions.
- Report real stages: preparing candidates, preserving locks, selecting
  replacements, validating, and comparing revisions.
- Keep cancellation available and leave the previous revision usable while a
  replacement plan is being prepared.

## Implementation sequence

### Slice A — characterization and immediate correctness

- **Status: complete (2026-10-21).**
- [x] Freeze current delete, lock, review-draft, journey-edit, warning, save/load,
  and undo behavior with tests.
- [x] Fix active-plan reset after deleting the loaded plan.
- [x] Fix the provider badge displaying `undefined` when model metadata is absent.
- [x] Introduce stable draft and plan-revision IDs.
- [x] Repair the saved-plan loading path exposed by the new browser workflow.
- [x] Keep reset and saved-plan lifecycle ownership outside the Set Builder
  composition hotspot.

Verification completed for this slice: the full repository quality gate, 451
Python tests, 114 JavaScript tests, all 17 browser workflows, the catalog
stability workflow, and refreshed Python/JavaScript coverage. Musical scoring
and candidate-selection policy were not changed.

### Slice B — workspace shell and compact presentation

- **Status: complete (2026-10-21).**
- [x] Add the sticky workspace header, compact rows, selected-track inspector,
  and persistent action bar.
- [x] Keep plan identity truthful with Draft/Saved and revision labels derived
  from explicit workspace state.
- [x] Preserve the existing three-direction selector, mix-health summary,
  planning evidence, journey curves, and all existing track mutations.
- [x] Keep selected-track presentation in a focused workspace-shell owner
  while `plan-view.js` remains responsible for running-order rendering and
  delegates existing commands without changing their payloads.
- [x] Verify desktop, narrow viewport, keyboard row navigation, inspector focus
  restoration, reduced motion, and warm-cache application startup.
- [x] Keep the inspector in a bounded viewport drawer, dismiss it on outside
  interaction or Escape, and close it before opening the transition editor.
- [x] Expose running-order drag handles with before/after drop feedback,
  keyboard reordering, undo integration, and locked-track protection.
- [x] Keep transition-editor exit controls reachable through a sticky header,
  bottom completion action, and Escape handling.

Verification completed for this slice: the full repository quality gate, 451
Python tests, 115 JavaScript tests, the catalog stability workflow, refreshed
coverage artifacts, and all 18 browser workflows pass. The browser gate covers
a loaded three-track saved revision at desktop and 390-pixel widths, inspector
selection and Escape handling, arrow-key navigation, horizontal overflow,
WCAG 2A/2AA serious-issue checks, reduced motion, warm-cache restart, and every
existing primary application workflow. Musical scoring, candidate retrieval,
and planning payloads were not changed.

### Slice C — regenerate with locks

- **Status: complete (2026-10-21).**
- [x] Add the explicit **Regenerate unlocked** contract and command.
- [x] Preserve locked tracks by journey section, required tracks, exclusions, and
  recording-family uniqueness.
- [x] Send the base revision with AI planning requests and keep the deterministic
  path on the same revision boundary.
- [x] Show stayed/changed/locked-preserved counts and mark newly selected tracks.
- [x] Restore the complete prior plan, lock state, transition settings, planning
  receipt, revision identity, and comparison through one Undo operation.

The backend now treats locked section placement as a hard validation rule.
Candidate retrieval emits a locked track only for its preserved section, both
AI and deterministic fallback receive section minimums, and an invalid result
cannot be applied. Required/excluded validation and recording-family uniqueness
remain authoritative in their existing services; the browser does not duplicate
those rules.

Verification completed for this slice: the full repository quality gate, 454
Python tests, 119 JavaScript tests, all 18 browser workflows, the catalog
stability workflow, and refreshed Python/JavaScript coverage pass. The browser
workflow regenerates a loaded saved revision, verifies its locked track and
base revision contract, checks changed-track presentation, and restores the
entire prior revision with Undo. Musical scoring weights were not changed.

### Slice D — durable reject-and-replace

- Add idempotent per-track review persistence.
- Add reason/scope confirmation, validated replacement, visible saved state,
  retry, and Undo.
- Keep overall review and transition learning as the optional final step.

### Slice E — editable direction lifecycle

- Add the direction drawer, dirty-state detection, affected-section summary,
  reset-to-AI, and update-unlocked workflow.

### Slice F — health repair and warning consolidation

- Normalize and deduplicate warnings.
- Add grouped issue navigation and partial repair commands.
- Remove the redundant warning wall.

### Slice G — release gate

- Update user, operator, developer, architecture, and browser-smoke documents.
- Run focused tests during every slice, then the full quality, coverage,
  stability, browser, and real-library listening gates.
- Compare generation time and interaction count against the current workflow
  before calling the redesign complete.

## Acceptance scenarios

1. Delete the loaded saved plan; the selector clears and the user returns to a
   clean Direction screen without refreshing the browser.
2. [x] Lock tracks, regenerate, and verify they remain in their sections
   while unlocked tracks change and the old revision can be restored.
3. Reject a track with a reason; the choice is visibly saved, the track is
   replaced with a valid non-family-duplicate alternative, and Undo restores
   both plan and feedback state intentionally.
4. Edit one AI journey section; the existing plan remains visible until **Update
   unlocked tracks** creates a new revision using the edited section.
5. Open a low-health plan; only the highest-priority grouped issues appear,
   clicking one opens the correct transition, and all raw diagnostics remain
   available under Advanced details.
6. Save, restart, and reload; plan revision, locks, feedback state, direction,
   transitions, and selected proposal remain truthful.
7. Cancel or fail regeneration; the previous plan remains usable and no partial
   review, lock, or saved-set state is committed.

## Explicit non-goals for the first release

- Do not change core musical weights while redesigning the workflow.
- Do not let rejection automatically delete audio or catalog records.
- Do not make Keep equivalent to Lock.
- Do not expose Rekordbox rating synchronization through this workflow until
  `SET-RB-001` is implemented separately.
- Do not add a framework or duplicate the existing Set Builder state store.
