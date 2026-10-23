# DJ Library flow

DJ Library is a performance-oriented read view. It combines a derived search
projection with authoritative musical profiles and never owns catalog mutation
policy.

![DJ Library flowchart](diagrams/dj-library.svg)

## Key owners

| Owner                          | Responsibility                                                         |
| ------------------------------ | ---------------------------------------------------------------------- |
| `features/dj-library/index.js` | Feature composition and load coordination                              |
| `model.js` and `filters.js`    | Query state and filter presentation                                    |
| `view.js`                      | Grouped track rendering                                                |
| `intelligence.js`              | Compatibility explanations and recommendations                         |
| `selection.js`                 | Selected-track playback and processing handoff                         |
| `CatalogProjectionBuilder`     | Search projection from catalog and completed-job evidence              |
| `library/musical_profile.py`   | Key, Camelot, energy, role, vocals, timing, confidence, and provenance |

## Freshness rules

- Source signatures decide whether the search projection must be rebuilt.
- Normal page loads read one page and its facets, not the entire library.
- Every browser request has a generation; older responses cannot replace a
  newer query result.
- Frontend musical derivations are presentation fallbacks only. The backend
  profile remains authoritative.

## Inputs and output

The projection combines downloaded-track identity, file availability, completed
processing evidence, descriptors, playlist/genre state, and recording-family
relationships. The endpoint returns paginated tracks and facets for rendering,
selection, and compatibility insight.

## Verification

`tests/javascript/features/dj-library/`, catalog projection tests,
`tests/unit/library/test_musical_profile.py`, and DJ Library browser scenarios in
`tests/browser/workflows.spec.js`.
