#!/usr/bin/env bash
# Starts the voice-service in WSL2 from the venv install.sh made, logging to
# this terminal. Ctrl+C stops it. Extra arguments go to the service:
#
#   voice_service/start.sh
#   voice_service/start.sh hear recording.webm      Hearing smoke test
#   voice_service/start.sh roundtrip ["text"]       Speaking -> Hearing smoke test
#
# Reads JARVIS_VOICE_URL (port), JARVIS_VOICE and JARVIS_VOICE_ALLOW_CPU from the
# repo's .env.
set -euo pipefail

root="$(cd "$(dirname "$0")/.." && pwd)"
venv="${JARVIS_VOICE_VENV:-$HOME/.venvs/jarvis-voice}"

if [ ! -x "$venv/bin/python" ]; then
  printf '  voice-service · no venv at %s — run voice_service/install.sh first\n' "$venv" >&2
  exit 1
fi
# shellcheck disable=SC1091
source "$venv/bin/activate"
# importable from anywhere, so relative paths (hear <file>) stay relative to here
export PYTHONPATH="$root${PYTHONPATH:+:$PYTHONPATH}"
exec python -m voice_service "$@"
