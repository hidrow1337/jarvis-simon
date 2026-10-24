"""nemo.collections.asr as far as Parakeet goes. The stub model hears
STUB_HEARD in any 16 kHz mono WAV file, and refuses anything else."""
import os
import types
import wave


class Hypothesis:
    def __init__(self, text):
        self.text = text


class ASRModel:
    @classmethod
    def from_pretrained(cls, model_name, map_location=None):
        if model_name != "nvidia/parakeet-tdt-0.6b-v3":
            raise FileNotFoundError(f"no such model: {model_name}")
        return cls()

    def eval(self):
        return self

    def transcribe(self, audio, batch_size=4, verbose=True, **kwargs):
        out = []
        for path in audio:
            with wave.open(path) as w:
                if (w.getframerate(), w.getnchannels()) != (16000, 1):
                    raise ValueError("expected 16 kHz mono")
            out.append(Hypothesis(os.environ.get("STUB_HEARD", "stub hearing")))
        return out


models = types.SimpleNamespace(ASRModel=ASRModel)
