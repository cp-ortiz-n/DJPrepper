# Browser workflow and accessibility smoke testing

ARCH-011B adds a real-browser release check without making every fast local
quality run launch Chromium. The browser server composes DJ Library Studio with
a temporary project, catalog, and connected music-library directory. It serves
the repository's real frontend assets but never reads or writes the configured
user catalog or music library.

## Run the release check

Install the pinned Chromium runtime once:

```bash
npm run check:browser:install
```

Run the smoke suite:

```bash
npm run check:browser
```

Failure artifacts are written to ignored `test-results/` paths. Screenshots and
Playwright traces are retained only for failed checks.

## Coverage map

| Critical behavior | Release evidence |
| --- | --- |
| Settings survive save and refresh | Playwright persists settings through the real API, reloads the browser, checks both search-window fields, and rejects duplicate DOM IDs. |
| Settings survive application restart | `tests/test_behavior_workflows.py` reopens the same repository and checks every persisted value. |
| Search retains every character during overlapping requests | Playwright delays real catalog responses while typing; `tests/request_state_controller.test.js` covers cancellation and stale-response rejection. |
| External drive reconnect clears stale offline state | Playwright switches between missing and connected library paths and verifies the rendered banner and health state; the Python workflow checks catalog availability. |
| Imports never silently fall back to local or temporary folders | `tests/test_import_service.py` verifies a disconnected configured drive rejects the import and leaves a possible local fallback untouched. |
| Dialog and keyboard behavior | Playwright verifies initial dialog focus, Escape dismissal, and focus restoration. |
| Supported layouts and accessibility | Playwright checks 1440 px and 720 px layouts and fails on serious or critical WCAG A/AA axe findings in navigation and Settings. |

The browser gate is deliberately complementary: deterministic unit and API
tests retain restart, path-safety, and failure-edge coverage that would be less
reliable or less safe to reproduce through a live browser.
