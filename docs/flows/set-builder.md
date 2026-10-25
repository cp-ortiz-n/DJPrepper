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

An exact genre request is strict by default. For example, `Latin Techno` may
change energy, character, and purpose across sections, but it cannot silently
become Latin Pop, R&B, House, or Amapiano. Model-proposed catalog neighbors are
retained only as unselected suggestions. The DJ must enable **Allow related
genres** and add a suggestion deliberately before it enters the journey.
Specific catalog names also take precedence over nested parent names: writing
`Latin Techno` does not independently request `Techno` unless the brief names
Techno elsewhere. Both the server and the browser reconcile AI output against
the written brief, so a cached or older proposal cannot bypass this boundary.

Playlist names contribute lower-confidence musical-identity tags without
rewriting canonical genres. These tags are derived from the catalog's current
genre vocabulary rather than a fixed alias list. For example, a track whose
canonical genre remains Reggaeton can qualify as an identity match for `Latin
Techno` when it belongs to a crate such as `LATIN_bounce_TECHNO_Rave_Edition`.
Direct genre matches rank first; playlist-supported matches are labeled as
identity evidence and name the source playlist in the planning explanation.
Catalog-derived cultural descriptors are also available as planning identities.
For example, an `Indian / South Asian` descriptor lets an Indian party brief
find suitable tracks even when their canonical genre is Bollywood, Bhangra, or
another catalog label. This does not rewrite the track's genre.

Negative and positional language is enforced after AI interpretation. A phrase
such as `No rap` becomes a hard catalog exclusion and is removed from requested
genres, while `Latin House to warm up` moves Latin House before the remaining
genre sequence. Explicit `high energy` language establishes a minimum energy
floor; `throughout`, `all around`, or `start to finish` applies the stronger
floor to every journey section. These rules resolve through the current catalog
vocabulary and are not hard-coded to individual genre names.

AI-created journeys begin in **Needs confirmation** state. Editing a section,
changing genre expansion, or changing the prompt returns the journey to that
state. **Confirm journey** validates 100% duration coverage, non-empty genres,
and the strict genre boundary; the action is disabled and the affected genres
are named while a correction is required. Only then can track planning begin. Loaded saved
plans retain their already-reviewed journey for backward compatibility.

Track selection is a separate decision from brief authoring:

| Track selection | What happens                                                                    |
| --------------- | ------------------------------------------------------------------------------- |
| AI curated      | AI ranks and orders a bounded candidate pool; deterministic validation follows  |
| Rules-based     | Local genre, BPM, key, energy, and constraint scoring chooses and orders tracks |

The interface presents these two choices directly. Legacy saved-set values
(`ai-planned`, `interpreted`, and `classic`) remain an internal compatibility
contract and are migrated into the two-part workflow when a plan is loaded.

## Planning owners

| Owner                                                             | Responsibility                                                                   |
| ----------------------------------------------------------------- | -------------------------------------------------------------------------------- |
| `BriefPreparationService` / `IntentionPlanner` / `JourneyPlanner` | Interpret, schema-check, and enforce explicit genre expansion authority          |
| `SetCandidateRetriever`                                           | Apply genre, availability, mixing, lock, descriptor, and playlist-identity rules |
| `AITrackPlanner`                                                  | Produce bounded AI and deterministic proposals                                   |
| `SetPlanValidator`                                                | Reject invented, duplicate, unavailable, excluded, or misplaced tracks           |
| `journey-allocation.js`                                           | Reserve browser-planned positions for each confirmed section and detect scarcity |
| Plan comparator                                                   | Select the strongest safe proposal and disclose fallback                         |
| Set Builder workspace                                             | Edit, lock, replace, reorder, undo/redo, and regenerate                          |
| `SavedSetService`                                                 | Persist the versioned brief, plan, locks, transitions, and receipt               |

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
- Exact genre requests never expand through scarcity fallback; the DJ is asked
  to allow related genres explicitly instead.
- Rules-based planning selects against the genre list for the position's
  confirmed journey section. Transition optimization may reorder tracks only
  inside that section, never across its boundaries.
- If a strict section does not have enough unique analyzed matches, generation
  stops with the section name, required count, and available count. The existing
  plan remains unchanged.
- Plan health is an explanation signal; hard validation is the release gate.

## Verification

`tests/unit/set_builder/`, `tests/javascript/features/set-builder/`, Set Builder
route tests, and Set Builder scenarios in `tests/browser/workflows.spec.js`.
