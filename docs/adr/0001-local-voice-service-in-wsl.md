# Local voice service in WSL2: Parakeet for Hearing, Kokoro for Speaking, English, no fallback

Hearing and Speaking run in a separate local voice service inside WSL2 on the user's RTX 4070 machine, with Parakeet TDT 0.6B v3 (NeMo) for Hearing and Kokoro-82M with a British male Voice for Speaking. The dashboard and Hermes stay native on Windows and reach the service over WSL2's localhost forwarding. We picked this setup for the best quality at the lowest latency, without cloud calls, while keeping the dashboard itself free of dependencies. The conversation is in English because no Danish Speaking model comes close to Kokoro's latency. There is deliberately no fallback to ElevenLabs or browser speech: if the voice service is down, voice is off and only typed chat works.

## Considered Options

- **Danish with Chatterbox Multilingual**: natural Danish, but noticeably slower per answer. We rejected it because latency was the priority.
- **Piper (Danish)**: instant, but robotic.
- **Loading the models inside `server.py`**: would force the dashboard into a torch environment and reload the models on every dashboard restart.
- **Moving the whole dashboard into WSL**: more disruption than needed, since the dashboard and Hermes already work natively.
- **Keeping ElevenLabs/browser fallbacks**: removed so there is a single voice path to debug. The original code is still in the first commit (upstream import).
