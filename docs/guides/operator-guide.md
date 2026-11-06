# Operator guide

This guide covers starting, monitoring, verifying, and maintaining a local
DJPrepper installation. For everyday workflows, see the
[user guide](user-guide.md). For code and test ownership, see the
[developer guide](developer-guide.md).

## Start and stop the application

From the repository root, start the server with the project environment:

```sh
.venv/bin/python -m audioextender.web
```

On macOS, `Start DJPrepper.command` performs the same application startup and
can also prepare the configured local Ollama model. The legacy
`Start AudioExtender.command` file remains available for compatibility. Open
[http://localhost:8765](http://localhost:8765) after startup.

The launcher verifies both the rendered homepage and the lightweight runtime
identity endpoint. The identity is an immutable SHA-256 hash of backend and
frontend source captured when the server starts. If a process on port 8765 has a
different revision—or predates the endpoint—the launcher replaces that stale
DJPrepper process before starting the current package entry point. It never
terminates an unrelated application using the same port.

Closing a browser tab does not stop active work. Closing the server process
does. Persisted jobs are restored safely after restart; an interrupted running
operation is reported as interrupted or retryable instead of silently applied.

If the page opens but the tabs do nothing after an update or restart, use the
**Reload app** notice if it appears. If it does not, reload the tab or reopen
the app with `Start DJPrepper.command`. A browser may still hold an older
frontend module while the server is serving a newer one. The app preserves
basic tab switching during failed startup, but those views will not load data
until the frontend finishes initializing. If a reload does not restore data,
select **Copy diagnostics** before reloading. The copied JSON includes the
frontend revision, failed module URL or startup error, page URL, and browser
details. Preserve it with any bug report, then confirm the server is running at
the address above before troubleshooting the music library or Ollama.

## Verify the music library

The configured music-library folder is the authoritative destination for
managed audio. DJPrepper does not silently fall back to a temporary or
local folder when an external drive is unavailable.

After reconnecting an external drive:

1. Open **Settings → Library health**.
2. Confirm that the configured folder reports **Connected**.
3. Select **Verify library**.
4. Review missing files, files outside the configured folder, pending metadata
   writes, and failed tag or artwork operations.

Resolve the connection or path first if verification reports the library as
unavailable. Re-running a write while the destination is disconnected cannot
repair it.

## Monitor background operations

Imports, analysis, metadata updates, relocation, artwork changes, and Set
Builder planning use persisted operations. Their receipts report what was
requested, what changed, where files were written, what failed, and whether the
result survives restart.

Use the operation's cancel or retry controls rather than stopping the server
when practical. A long external process such as FFmpeg, Demucs, or Ollama may
take a short time to reach a safe cancellation checkpoint.

## Operate optional local AI

Set Builder works without Ollama by using deterministic rules. When Ollama is
enabled, only text briefs and bounded catalog metadata are sent to the local
model; audio is not sent.

Useful checks:

```sh
ollama list
curl -fsS http://127.0.0.1:11434/api/tags
```

The Set Builder planning receipt records the selected mode, provider, model,
attempts, validation result, fallback reason, and whether the deterministic
plan was retained. A provider outage must fall back rather than make the app
unusable. See [Optional local AI](user-guide.md#optional-local-ai-for-set-builder)
for configuration details.

Regeneration requests also record the base plan revision and section assignment
for every locked track. A completed revision reports stayed, changed, and
locked-preserved counts. If the planner drops a lock or moves it to another
journey section, validation rejects the result; the previous revision remains
usable and can be restored with Undo.

## Operate Rekordbox rating synchronization

Rating synchronization is an explicit two-step import under **Settings →
Rekordbox ratings**. Preview is read-only. Apply writes only exact catalog
matches to SQLite and leaves ambiguous or unmatched export rows untouched.

- Export a public collection XML or UTF-16 tab-separated TXT file from
  Rekordbox; do not grant access to its private database. XML can carry stable
  paths or DJPrepper identities. TXT matching is deliberately limited
  to exact normalized artist, title, and duration.
- Review match counts before applying, especially after moving a library or
  changing metadata.
- Re-importing the same ratings is idempotent and reports zero changes.
- Use **Clear imported ratings** to roll back the signal without deleting local
  Set Builder feedback or analyzed musical facts.
- Back up the catalog before the first large real-library application. If many
  rows are unmatched, reconnect/reconcile the library and preview again rather
  than accepting weaker matching.

## Backups and recovery

Back up the configured music-library folder together with the application's
catalog and settings before moving a library or performing a large metadata
operation. Use the application's relocation and reconciliation workflows so
catalog paths and file writes remain coordinated.

Generated reports and cache files are reproducible and are not substitutes for
a catalog or audio backup.

## Health and release checks

Routine library status is cached for five minutes, while **Verify library**
always performs the authoritative filesystem scan. Opening the application no
longer starts the deeper health and orphaned-storage inventory; those checks are
loaded when Settings is opened. Waveform previews are generated with one
sequential audio pass and then served from the revision-aware cache. Catalog
projection rebuilds retain the last known-good JSON until the atomic replacement
is complete, so readers do not see a missing file during publication.

For a source checkout, these commands verify the supported runtime and major
workflows:

```sh
make quality
make stability
make browser
make coverage
```

The CI workflow runs the relevant gates on pushes and pull requests. See the
[developer guide](developer-guide.md#automated-tests) for details.

## Clean generated workspace artifacts

Preview the known generated files that can be removed:

```sh
.venv/bin/python scripts/maintenance/clean_workspace.py
```

Apply the standard cleanup only after reviewing the list:

```sh
.venv/bin/python scripts/maintenance/clean_workspace.py --apply
```

The runtime analysis cache is preserved by default because rebuilding it can be
expensive. Remove it explicitly when a clean re-analysis is intended:

```sh
.venv/bin/python scripts/maintenance/clean_workspace.py --apply --include-analysis-cache
```

The cleaner is restricted to the repository root, skips dependency and source
control directories, and only removes its documented generated targets.
