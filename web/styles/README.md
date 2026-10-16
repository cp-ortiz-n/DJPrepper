# Stylesheet ownership

`../styles.css` is the only browser entry point. Its imports preserve the exact
cascade order that existed before ARCH-013B; do not alphabetize them.

The numeric prefix records cascade position. The descriptive name records the
owner:

- `00-*`: tokens, native defaults, shell, and navigation.
- `10-*`, `21-*`, `80-*`, `81-*`, `82-*`: shared collection or application
  primitives used by multiple feature modules.
- `20-*` through `24-*`: processing, candidate review, and the historical
  collection foundations that must retain their position beside processing.
- `30-*` and `70-*`: DJ Library analysis and reporting.
- `40-*` and `41-*`: Settings, backup, cleanup, and device preferences.
- `50-*` through `52-*`: Music Files workflows, rows, filters, and maintenance.
- `60-*` and `61-*`: Set Builder brief, journey, planning, and transitions.

New feature rules belong in the latest fragment owned by that feature. Shared
placement requires the same semantic component to be used by at least two
features. A declaration that merely looks similar is not shared ownership.

Some owners have multiple fragments because later rules intentionally refine an
earlier foundation. Consolidate fragments only when computed-style and browser
tests prove that changing their cascade position is safe.

