# jarvis-simon

## Agent skills

### Issue tracker

Issues live in GitHub Issues for hidrow1337/jarvis-simon, using the `gh` CLI. See `docs/agents/issue-tracker.md`.

### Triage labels

Default vocabulary: needs-triage, needs-info, ready-for-agent, ready-for-human, wontfix. See `docs/agents/triage-labels.md`.

### Domain docs

Single-context: one `GLOSSARY.md` and `docs/adr/` at the repo root. See `docs/agents/domain.md`.

## Tests

`python3 -m unittest` from the repo root (stdlib only). `tests/harness.py` starts the real dashboard (`server.py`) on a free port with the mock runtime and sends requests with the right Host/Origin/token — test through that HTTP API, not internals.

What has no HTTP surface (the voice-service's startup and its `hear` command) is tested by running `python3 -m voice_service` as a subprocess (`run_voice_service`, `VoiceService`). `tests/stubs/` holds stand-ins for torch and NeMo so the real Hearing model's code runs without a GPU (`stub_env()`).
