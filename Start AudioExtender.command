#!/bin/zsh

set -euo pipefail

PROJECT_DIR="${0:A:h}"
APP_URL="http://127.0.0.1:8765"
APP_OPEN_URL="$APP_URL/?launch=$(date +%s)-$$"
OLLAMA_URL="http://127.0.0.1:11434"
MODEL="qwen3.5:4b"

cd "$PROJECT_DIR"

PYTHON="$PROJECT_DIR/.venv/bin/python"
if [[ ! -x "$PYTHON" ]]; then
  echo "DJPrepper's Python environment is missing."
  echo "Create it with: python3 -m venv .venv && .venv/bin/pip install -r requirements.txt"
  read "?Press Return to close…"
  exit 1
fi

export AUDIOEXTENDER_LLM_PROVIDER="ollama"
export OLLAMA_HOST="$OLLAMA_URL"
export OLLAMA_SET_BUILDER_MODEL="$MODEL"

if /usr/bin/curl -fsS "$APP_URL/" >/dev/null 2>&1; then
  EXPECTED_RUNTIME_REVISION="$("$PYTHON" -m audioextender.infrastructure.runtime_revision)"
  RUNNING_RUNTIME_REVISION="$(
    /usr/bin/curl -fsS "$APP_URL/api/diagnostics/runtime" 2>/dev/null |
      "$PYTHON" -c 'import json, sys; print(json.load(sys.stdin).get("revision", ""))' 2>/dev/null || true
  )"
  if [[ -n "$RUNNING_RUNTIME_REVISION" && "$RUNNING_RUNTIME_REVISION" == "$EXPECTED_RUNTIME_REVISION" ]]; then
    echo "DJPrepper is already running the current backend. Opening it now."
    /usr/bin/open "$APP_OPEN_URL"
    exit 0
  fi
  echo "DJPrepper is running an outdated backend. Restarting it now."
fi

# A process from an older checkout can keep the port open while serving a broken
# page after files move. Restart only a recognizable DJPrepper process; do
# not terminate an unrelated application that happens to use the same port.
STALE_APP_PID="$(/usr/sbin/lsof -tiTCP:8765 -sTCP:LISTEN 2>/dev/null | /usr/bin/head -n 1 || true)"
if [[ -n "$STALE_APP_PID" ]]; then
  STALE_APP_COMMAND="$(/bin/ps -p "$STALE_APP_PID" -o command= 2>/dev/null || true)"
  if [[ "$STALE_APP_COMMAND" == *"web_app.py"* || "$STALE_APP_COMMAND" == *"audioextender.web"* ]]; then
    echo "Restarting an outdated DJPrepper server…"
    /bin/kill "$STALE_APP_PID"
    for attempt in {1..20}; do
      if ! /usr/sbin/lsof -tiTCP:8765 -sTCP:LISTEN >/dev/null 2>&1; then
        break
      fi
      sleep 0.25
    done
  else
    echo "Port 8765 is being used by another application: $STALE_APP_COMMAND"
    echo "Stop that application or change its port, then run this launcher again."
    read "?Press Return to close…"
    exit 1
  fi
fi

if ! /usr/bin/curl -fsS "$OLLAMA_URL/api/tags" >/dev/null 2>&1; then
  echo "Starting Ollama…"
  /usr/bin/open -a Ollama
  for attempt in {1..30}; do
    if /usr/bin/curl -fsS "$OLLAMA_URL/api/tags" >/dev/null 2>&1; then
      break
    fi
    sleep 1
  done
fi

if ! /usr/bin/curl -fsS "$OLLAMA_URL/api/tags" >/dev/null 2>&1; then
  echo "Ollama did not become ready. Open Ollama and run this launcher again."
  read "?Press Return to close…"
  exit 1
fi

OLLAMA_BIN="$(command -v ollama || true)"
if [[ -z "$OLLAMA_BIN" ]]; then
  echo "The Ollama command was not found. Install Ollama, then run this launcher again."
  read "?Press Return to close…"
  exit 1
fi

if ! "$OLLAMA_BIN" list | /usr/bin/awk 'NR > 1 {print $1}' | /usr/bin/grep -Fxq "$MODEL"; then
  echo "Downloading $MODEL for the first launch…"
  "$OLLAMA_BIN" pull "$MODEL"
fi

echo "Starting DJPrepper with local AI: $MODEL"
(
  for attempt in {1..60}; do
    if /usr/bin/curl -fsS "$APP_URL" >/dev/null 2>&1; then
      /usr/bin/open "$APP_OPEN_URL"
      exit 0
    fi
    sleep 0.5
  done
) &

exec "$PYTHON" -m audioextender.web
