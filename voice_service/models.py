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
import logging
import os
import tempfile
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
                           f"run with --speaking fake for now")
    return load


_device = None


def pick_device(allow_cpu):
    """"cuda" if torch sees a GPU, else "cpu" when allow_cpu, else raises:
    a Jarvis silently running on CPU is too slow to talk to. Decided once and
    shared by every real model."""
    global _device
    if _device is None:
        try:
            import torch
        except ImportError:
            raise RuntimeError("torch is not installed in this environment — "
                               "run voice_service/install.sh") from None
        if torch.cuda.is_available():
            _device = "cuda"
            print(f"  voice-service · device cuda ({torch.cuda.get_device_name(0)})",
                  flush=True)
        elif allow_cpu:
            _device = "cpu"
            print("  voice-service · device cpu (CUDA not available; "
                  "JARVIS_VOICE_ALLOW_CPU=1) — expect slow Hearing", flush=True)
        else:
            raise RuntimeError("CUDA is not available: torch sees no GPU. Check that "
                               "`nvidia-smi` works in WSL, or set JARVIS_VOICE_ALLOW_CPU=1 "
                               "to run on the CPU (slow)")
    return _device


PARAKEET = "nvidia/parakeet-tdt-0.6b-v3"


class Parakeet:
    """Parakeet TDT 0.6B v3 through NeMo: loaded once, then kept warm."""

    name = PARAKEET.split("/")[-1]

    def __init__(self, device):
        import torch
        try:
            import nemo.collections.asr as nemo_asr
        except ImportError:
            raise RuntimeError("NeMo is not installed in this environment — "
                               "run voice_service/install.sh") from None
        from nemo.utils import logging as nemo_logging
        nemo_logging.setLevel(logging.WARNING)   # else every config key at INFO on load
        self.device = device
        self._model = nemo_asr.models.ASRModel.from_pretrained(
            model_name=PARAKEET, map_location=torch.device(device)).eval()
        self.hear(_silence(16000, 0.5))   # first call pays CUDA warm-up, not the user

    def hear(self, wav):
        # NeMo reads files most reliably across versions; the WAV is already 16 kHz mono
        with tempfile.TemporaryDirectory(prefix="jarvis-parakeet-") as tmp:
            path = os.path.join(tmp, "heard.wav")
            with open(path, "wb") as f:
                f.write(wav)
            out = self._model.transcribe([path], batch_size=1, verbose=False)
        if isinstance(out, tuple):        # older RNNT/TDT models: (best, all)
            out = out[0]
        first = out[0] if out else ""
        return getattr(first, "text", first) or ""


def _silence(rate, seconds):
    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(rate)
        w.writeframes(b"\0\0" * int(rate * seconds))
    return buf.getvalue()


def load_parakeet(args):
    return Parakeet(pick_device(args.allow_cpu))


# name -> loader(args). Real loaders do their heavy imports inside.
HEARING = {
    "parakeet": load_parakeet,
    "fake": lambda args: FakeHearing(args.fake_heard),
}
SPEAKING = {
    "kokoro": _not_yet("Kokoro Speaking"),
    "fake": lambda args: FakeSpeaking(),
}
