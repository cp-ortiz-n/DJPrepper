#!/bin/zsh

# Canonical DJPrepper launcher. Keep the historical launcher as the implementation
# so existing shortcuts and automation continue to work.
SCRIPT_DIR="${0:A:h}"
exec "$SCRIPT_DIR/Start AudioExtender.command" "$@"
