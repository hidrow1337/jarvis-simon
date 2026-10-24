"""
The local voice-service: Hearing and Speaking for the dashboard, over HTTP on
127.0.0.1 only. Runs in its own environment (WSL2 + CUDA on the user's machine),
so the heavy model dependencies never reach the dashboard. See ADR 0001.

    voice_service/install.sh      once, in WSL: own venv with torch (CUDA), NeMo, Kokoro
    voice_service/start.sh        start it; logs to the terminal
    voice_service/start.sh roundtrip   smoke test: a sentence through Speaking, then Hearing
    python3 -m voice_service --help
"""
