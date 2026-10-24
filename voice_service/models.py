"""
Hearing and Speaking models, each behind one small interface so the service
doesn't care which one it runs:

    hearing.hear(wav) -> text      wav: 16 kHz mono WAV bytes
    speaking.speak(text) -> wav    whole answer as WAV bytes

Both also carry `name` and `device` for /health. Loaders for the real models
import torch/NeMo/Kokoro inside themselves, only when chosen, so the service can
start with fakes on a machine that has none of them.
"""
import io
import wave


class FakeHearing:
    """Hears the same text every time. Refuses anything that isn't 16 kHz mono
    WAV, so a test through it proves the conversion happened."""

    name = "fake"
    device = "cpu"

    def __init__(self, heard="fake hearing"):
        self.heard = heard

    def hear(self, wav):
        with wave.open(io.BytesIO(wav)) as w:
            if (w.getframerate(), w.getnchannels()) != (16000, 1):
                raise ValueError(f"expected 16 kHz mono, got {w.getframerate()} Hz "
                                 f"x{w.getnchannels()}")
        return self.heard


class FakeSpeaking:
    """Says everything as a quarter second of silence."""

    name = "fake"
    device = "cpu"

    def speak(self, text):
        buf = io.BytesIO()
        with wave.open(buf, "wb") as w:
            w.setnchannels(1)
            w.setsampwidth(2)
            w.setframerate(24000)
            w.writeframes(b"\0\0" * 6000)
        return buf.getvalue()


def _not_yet(model):
    def load(args):
        raise RuntimeError(f"the real {model} model is not wired up yet — "
                           f"run with fakes (--hearing fake --speaking fake)")
    return load


# name -> loader(args). Real loaders do their heavy imports inside.
HEARING = {
    "parakeet": _not_yet("Parakeet Hearing"),
    "fake": lambda args: FakeHearing(args.fake_heard),
}
SPEAKING = {
    "kokoro": _not_yet("Kokoro Speaking"),
    "fake": lambda args: FakeSpeaking(),
}
