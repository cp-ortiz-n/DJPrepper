# Operator guide

This guide covers starting, monitoring, verifying, and maintaining a local DJ
Library Studio installation. For everyday workflows, see the
[user guide](user-guide.md). For code and test ownership, see the
[developer guide](developer-guide.md).

## Start and stop the application

From the repository root, start the server with the project environment:

```sh
.venv/bin/python web_app.py
```

On macOS, `Start AudioExtender.command` performs the same application startup
and can also prepare the configured local Ollama model. Open
[http://localhost:8765](http://localhost:8765) after startup.

Closing a browser tab does not stop active work. Closing the server process
does. Persisted jobs are restored safely after restart; an interrupted running
operation is reported as interrupted or retryable instead of silently applied.

If the page opens but the tabs do nothing after an update or restart, use the
**Reload app** notice if it appears. If it does not, reload the tab or reopen
the app with `Start AudioExtender.command`. A browser may still hold an older
frontend module while the server is serving a newer one. The app preserves
basic tab switching during failed startup, but those views will not load data
until the frontend finishes initializing. If a reload does not restore data,
select **Copy diagnostics** before reloading. The copied JSON includes the
frontend revision, failed module URL or startup error, page URL, and browser
details. Preserve it with any bug report, then confirm the server is running at
the address above before troubleshooting the music library or Ollama.

## Verify the music library

The configured music-library folder is the authoritative destination for
managed audio. DJ Library Studio does not silently fall back to a temporary or
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

## Backups and recovery

Back up the configured music-library folder together with the application's
catalog and settings before moving a library or performing a large metadata
operation. Use the application's relocation and reconciliation workflows so
catalog paths and file writes remain coordinated.

Generated reports and cache files are reproducible and are not substitutes for
a catalog or audio backup.

## Health and release checks

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
.venv/bin/python scripts/clean_workspace.py
```

Apply the standard cleanup only after reviewing the list:

```sh
.venv/bin/python scripts/clean_workspace.py --apply
```

The runtime analysis cache is preserved by default because rebuilding it can be
expensive. Remove it explicitly when a clean re-analysis is intended:

```sh
.venv/bin/python scripts/clean_workspace.py --apply --include-analysis-cache
```

The cleaner is restricted to the repository root, skips dependency and source
control directories, and only removes its documented generated targets.
