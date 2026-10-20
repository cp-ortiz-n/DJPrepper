# Stylesheet ownership

`../styles.css` is the only browser entry point. Its imports preserve the exact
cascade order that existed before ARCH-013B; do not alphabetize them.

Directories record ownership; the numeric prefix records global cascade
position and must remain stable:

- `core/00-*`: tokens, native defaults, shell, and navigation.
- `shared/10-*`, `shared/21-*`, `shared/80-*`, `shared/81-*`, `shared/82-*`: shared collection or application
  primitives used by multiple feature modules.
- `features/processing/20-*` through `24-*`: processing, candidate review, and the historical
  collection foundations that must retain their position beside processing.
- `features/library/30-*` and `features/reporting/70-*`: DJ Library analysis and reporting.
- `features/settings/40-*` and `41-*`: Settings, backup, cleanup, and device preferences.
- `features/music-files/50-*` through `52-*`: Music Files workflows, rows, filters, and maintenance.
- `features/set-builder/60-*` and `61-*`: Set Builder brief, journey, planning, and transitions.

New feature rules belong in the latest fragment owned by that feature. Shared
placement requires the same semantic component to be used by at least two
features. A declaration that merely looks similar is not shared ownership.

Some owners have multiple fragments because later rules intentionally refine an
earlier foundation. Consolidate fragments only when computed-style and browser
tests prove that changing their cascade position is safe.

