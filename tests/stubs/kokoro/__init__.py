"""Stand-in for Kokoro in tests: only what the voice-service touches. The stub
pipeline says each word as a tenth of a second of a quiet hum at 24 kHz, and
refuses a Voice that isn't of its language (real Kokoro would just put on the
wrong accent)."""
import re

import torch

VOICES = {"af_heart", "am_adam", "bf_emma", "bm_george", "bm_lewis", "bm_daniel",
          "ff_siwis", "jf_alpha"}


class Result:
    def __init__(self, audio):
        self.audio = audio


class KPipeline:
    def __init__(self, lang_code, repo_id=None, model=True, trf=False, device=None):
        if repo_id != "hexgrad/Kokoro-82M":
            raise FileNotFoundError(f"no such model: {repo_id}")
        self.lang_code = lang_code
        self.voices = {}

    def load_voice(self, voice):
        if voice not in VOICES:
            raise FileNotFoundError(f"404 Client Error: voices/{voice}.pt not found")
        self.voices[voice] = voice
        return voice

    def __call__(self, text, voice=None, speed=1, split_pattern=r"\n+"):
        if self.load_voice(voice)[0] != self.lang_code:
            raise ValueError(f"{voice} is not a voice for lang_code {self.lang_code!r}")
        for chunk in re.split(split_pattern, text):
            words = chunk.split()
            if words:
                yield Result(torch.Tensor([0.25, -0.25] * 1200 * len(words)))
