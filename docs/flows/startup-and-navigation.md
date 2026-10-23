# Startup and navigation flow

Startup has one job: compose a recoverable backend and deliver one internally
consistent frontend revision before navigation is marked ready.

![Startup and navigation flowchart](diagrams/startup-and-navigation.svg)

## Key owners

| Owner                          | Responsibility                                                                  |
| ------------------------------ | ------------------------------------------------------------------------------- |
| `ApplicationPaths`             | Resolves workspace, database, reports, backups, library, and frontend roots.    |
| `ApplicationRuntime`           | Holds the repository, queue, registries, locks, caches, and composed services.  |
| `create_app()`                 | Installs middleware, error handlers, startup hooks, routers, and static assets. |
| `FrontendAssetService`         | Validates the manifest and applies one revision to the complete module graph.   |
| `frontend/app.js`              | Creates shared browser services and feature loaders.                            |
| `createNavigationController()` | Binds tabs and loads the selected feature.                                      |

`audioextender.web.application.app` is lazy: importing the module does not open
the database or run recovery. The production launcher uses `create_app` as an
application factory, while the lazy facade preserves compatibility for tests and
embedders.

## Recovery rules

- Startup changes interrupted jobs and operations to a recoverable state.
- A module-linking failure leaves the recovery banner visible with diagnostics.
- A warm-cache reload cannot mix modules from different asset revisions.
- Feature-load failures use shared notifications without breaking navigation.

## Main contracts

- Backend composition: `audioextender/web/application.py` and
  `audioextender/web/composition.py`
- Asset delivery: `audioextender/web/assets/frontend.py`
- Browser composition: `frontend/app.js`
- Navigation: `frontend/core/navigation-controller.js`

## Verification

`tests/unit/web/test_web_composition_contracts.py`,
`tests/browser/frontend-restart.spec.js`, and navigation cases in
`tests/browser/workflows.spec.js`.
