# CSS ownership and responsive-accessibility audit

Date: 2026-10-15  
Scope: `frontend/styles.css`, the browser-rendered markup in `frontend/index.html` and
`frontend/*.js`, and the Playwright release workflow.

## Result

The stylesheet has working accessibility safeguards, but its ownership and
cascade are no longer sufficiently bounded. A behavior-preserving split is
justified; a framework or visual redesign is not.

The investigation found:

- 1,690 maintained lines and 207,780 bytes in one stylesheet.
- 656 distinct class selectors.
- 68 media-query blocks representing 15 normalized conditions. Equivalent
  breakpoints appear both with and without whitespace and feature overrides are
  distributed throughout the file.
- 17 class selectors with no static reference in `frontend/index.html`, `frontend/*.js`,
  tests, or backend templates. These are removal candidates, not automatic
  deletions, because runtime-composed class names require manual confirmation.
- Feature-prefixed selectors are already substantial: Set Builder 96, Music
  Files 71, imports/processing 69, DJ Library 51, and Settings 41. Another 328
  selectors are shared or do not communicate an owner through their name.
- Two animations exist. One global `prefers-reduced-motion: reduce` rule reduces
  animation and transition duration and limits iteration count.
- A shared `:focus-visible` rule provides a two-pixel accent outline for buttons,
  links, form controls, summaries, and explicit tab stops.

The static-reference candidates at the time of the audit are:

```text
downloaded-bulk-identity, downloaded-duration, downloaded-group,
import-boundary, import-guidance, import-layout, inspector-identity,
library-bulk-identity, optional-metric, performance-diagnostics-head,
preset-manager-head, set-identity-editor-actions, status-danger, status-info,
status-success, status-warning, track-quality
```

`status-*` has an active attribute-based equivalent (`data-tone`) and may be
intentional compatibility vocabulary. Every candidate must be traced before
removal.

## Ownership map

| Layer | Owns | Does not own |
| --- | --- | --- |
| Tokens/base | custom properties, box sizing, typography, native element defaults | feature layout |
| Shared components | controls, focus, dialogs, toasts, audio controls, pagination, empty/loading states | Music Files, Library, Settings, or Set Builder structure |
| Shell/layout | top bar, navigation, page containers, global responsive shell | feature-specific cards and editors |
| Imports/processing | import methods, queues, source matching, jobs, candidate review | library/catalog presentation |
| Music Files | downloaded catalog filters, cards, maintenance, metadata and identity editors | DJ Library matching |
| DJ Library | library filters, result rows, inspectors, analysis panels | downloaded-file maintenance |
| Set Builder | brief, journey, proposals, track rows, transitions, saved sets | shared dialog and playback primitives |
| Settings/reporting | settings groups, health, backup, cleanup, diagnostics, reports | global controls |

Future selectors should have one owner. Cross-feature selectors belong in the
shared layer only when at least two features use the same semantic component,
not merely because declarations look similar.

## Supported interaction matrix

The release browser gate now checks Settings at desktop (1440 × 900), compact
tablet (720 × 900), and narrow mobile (390 × 844) widths. At every width the
primary form and save action must remain visible and the document must not
overflow horizontally. The same gate verifies the visible keyboard focus ring,
computed reduced-motion durations, dialog focus/restore behavior, and serious
or critical WCAG A/AA findings.

These widths are the maintained Chromium baseline. Other engines are not yet a
release guarantee. Feature-specific horizontal scrollers, such as diagnostic
tables, remain allowed inside their bounded containers.

## Decision

Create ARCH-013B to split the stylesheet by the ownership map above. The work
must preserve load order and computed behavior, remove only confirmed dead
rules, consolidate equivalent media conditions within each owner, and add a
single CSS entry point so `index.html` does not learn feature ordering.

The split is complete only when the existing unit, browser, accessibility,
responsive, and reduced-motion gates pass without snapshot-driven restyling.

## Implementation

ARCH-013B completed the split behind the unchanged `frontend/styles.css` public
entry point. Numbered owner fragments preserve the original cascade order, and
`frontend/styles/README.md` defines placement rules. All 17 confirmed static-reference
candidates were removed; active attribute-based status tones remain supported.
The entry order and removed-selector set are protected by a fast frontend test.

## 2026-10-27 follow-up

The Set Builder consistency pass removed a cross-feature ownership leak found
after ARCH-013B: searchable-select controls were still defined by
`features/set-builder/61-set-builder-workspace.css` even though Music Files,
DJ Library, Reporting, Settings, and Set Builder all instantiate the component.
The component now lives in `shared/11-shared-searchable-select.css`, after the
shared collection foundation and before feature overrides.

The same pass established shared readable-type tokens in the base layer and
made Set Builder consume them through feature aliases. Primary, secondary,
tertiary, and destructive Set Builder actions now use the shared button
hierarchy in both static and dynamically rendered surfaces. A focused frontend
test protects the shared owner, prevents independent micro-type declarations,
and verifies the action hierarchy.
