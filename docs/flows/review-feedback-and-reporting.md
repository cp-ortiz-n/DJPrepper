# Review, feedback, and reporting flows

Human decisions are stored as evidence with provenance. They can influence
presentation and bounded ranking, but they never silently replace raw analysis
or bypass hard planning rules.

![Review, feedback, and reporting flowchart](diagrams/review-feedback-and-reporting.svg)

## Feedback families

| Family                       | Purpose                                                       | Durable owner                                   |
| ---------------------------- | ------------------------------------------------------------- | ----------------------------------------------- |
| Processing candidate review  | Choose, reject, audition, or reprocess intro/outro candidates | `JobReviewService` and job feedback persistence |
| BPM/key verification         | Apply a reviewed value while retaining analyzer provenance    | Verification records in persistence             |
| Track rating and notes       | Capture the user's opinion of a track                         | Track feedback records                          |
| Rekordbox star synchronization | Preview exact XML matches, then apply version-specific evidence | `external_track_ratings` and catalog projection |
| Set Builder preference event | Learn a bounded, context-specific ranking signal              | `DJPreferenceService`                           |
| Full set review              | Evaluate a saved plan, its tracks, transitions, and pacing    | `SetReviewService`                              |

## Trust rules

- Reprocessing creates a normal queue execution instead of modifying a completed
  result in place.
- Ratings and preference events do not rewrite raw BPM, key, or audio evidence.
- Rekordbox ratings enter only through an explicit public-XML preview/apply
  boundary; ambiguous and unmatched rows remain review-only.
- Personalized ranking cannot override availability, uniqueness, required,
  excluded, locked, or validation rules.
- Reusing an event ID is idempotent.
- Every action returns a saved or rejected receipt so persistence is visible.

## Reporting outputs

`ReportingService` projects queue/catalog analytics, processing reports, audio
availability, and job details. Relevant mutations invalidate report caches;
reviewed values remain distinguishable from analyzer output and can be removed.

## Verification

`tests/unit/set_builder/test_set_review_service.py`, preference-learning tests,
reporting tests, review JavaScript tests, and review/reporting browser scenarios
in `tests/browser/workflows.spec.js`.
