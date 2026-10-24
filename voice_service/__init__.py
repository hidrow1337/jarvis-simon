"""
The local voice-service: Hearing and Speaking for the dashboard, over HTTP on
127.0.0.1 only. Runs in its own environment (WSL2 + CUDA on the user's machine),
so the heavy model dependencies never reach the dashboard. See ADR 0001.

    python3 -m voice_service --help
"""
