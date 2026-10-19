#!/bin/zsh

set -euo pipefail

PROJECT_DIR="${0:A:h}"
APP_URL="http://127.0.0.1:8765"
APP_OPEN_URL="$APP_URL/?launch=$(date +%s)-$$"
OLLAMA_URL="http://127.0.0.1:11434"
MODEL="qwen3.5:4b"

cd "$PROJECT_DIR"

export AUDIOEXTENDER_LLM_PROVIDER="ollama"
export OLLAMA_HOST="$OLLAMA_URL"
export OLLAMA_SET_BUILDER_MODEL="$MODEL"

if /usr/bin/curl -fsS "$APP_URL/api/set-builder/intention-provider" >/dev/null 2>&1; then
  echo "AudioExtender is already running. Opening it now."
  /usr/bin/open "$APP_OPEN_URL"
  exit 0
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

PYTHON="$PROJECT_DIR/.venv/bin/python"
if [[ ! -x "$PYTHON" ]]; then
  echo "AudioExtender's Python environment is missing."
  echo "Create it with: python3 -m venv .venv && .venv/bin/pip install -r requirements.txt"
  read "?Press Return to close…"
  exit 1
fi

echo "Starting AudioExtender with local AI: $MODEL"
(
  for attempt in {1..60}; do
    if /usr/bin/curl -fsS "$APP_URL" >/dev/null 2>&1; then
      /usr/bin/open "$APP_OPEN_URL"
      exit 0
    fi
    sleep 0.5
  done
) &

exec "$PYTHON" web_app.py
