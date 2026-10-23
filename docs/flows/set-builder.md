# Set Builder flow

Set Builder turns a natural-language intention or manual constraints into an
editable, validated running order. AI can propose; catalog safety, recording
identity, required tracks, and final validation remain deterministic authority.

![Set Builder flowchart](diagrams/set-builder.svg)

## Authoring paths

| Path                 | What the user controls                                 | Planning result                                       |
| -------------------- | ------------------------------------------------------ | ----------------------------------------------------- |
| Describe what I want | Intention text, then the interpreted brief and journey | AI-assisted interpretation with editable output       |
| Build manually       | Genres, energy, journey, constraints, and track rules  | Direct structured brief with the same validation path |

Both paths produce the same planning request. The browser never sends the full
database to a model; it sends a bounded set of validated catalog candidates.

Track selection is a separate decision from brief authoring:

| Track selection | What happens                                                                    |
| --------------- | ------------------------------------------------------------------------------- |
| AI curated      | AI ranks and orders a bounded candidate pool; deterministic validation follows |
| Rules-based     | Local genre, BPM, key, energy, and constraint scoring chooses and orders tracks |

The interface presents these two choices directly. Legacy saved-set values
(`ai-planned`, `interpreted`, and `classic`) remain an internal compatibility
contract and are migrated into the two-part workflow when a plan is loaded.

## Planning owners

| Owner                                                             | Responsibility                                                               |
| ----------------------------------------------------------------- | ---------------------------------------------------------------------------- |
| `BriefPreparationService` / `IntentionPlanner` / `JourneyPlanner` | Interpret and schema-check the editable direction                            |
| `SetCandidateRetriever`                                           | Apply availability, genre, BPM, key, vocal, timing, lock, and identity rules |
| `AITrackPlanner`                                                  | Produce bounded AI and deterministic proposals                               |
| `SetPlanValidator`                                                | Reject invented, duplicate, unavailable, excluded, or misplaced tracks       |
| Plan comparator                                                   | Select the strongest safe proposal and disclose fallback                     |
| Set Builder workspace                                             | Edit, lock, replace, reorder, undo/redo, and regenerate                      |
| `SavedSetService`                                                 | Persist the versioned brief, plan, locks, transitions, and receipt           |

## Revision and regeneration rules

- A lock protects the track identity and its journey section.
- Regeneration changes only eligible unlocked positions.
- `base_plan_revision` links the new draft to its parent.
- Failure restores the complete previous revision, including transitions.
- Undo/redo operates on atomic plan snapshots.
- Export preflight verifies every local audio path before writing a playlist.

## Trust and fallback

- Ollama being unavailable does not disable deterministic planning.
- Invalid or weaker AI output is replaced by the validated deterministic plan.
- Recording-family duplicates cannot occupy two set positions.
- Other versions of a recording may be shown as explicit alternatives.
- Plan health is an explanation signal; hard validation is the release gate.

## Verification

`tests/unit/set_builder/`, `tests/javascript/features/set-builder/`, Set Builder
route tests, and Set Builder scenarios in `tests/browser/workflows.spec.js`.
