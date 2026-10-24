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
import re
import tempfile
import warnings
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
        return _silence(24000, 0.25)


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


def gpu_memory():
    """How much of the GPU is in use (by every process, as nvidia-smi counts),
    or None when no real model runs on CUDA."""
    if _device != "cuda":
        return None
    import torch
    free, total = torch.cuda.mem_get_info()
    return f"{(total - free) / 2**30:.1f} of {total / 2**30:.1f} GB in use"


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


KOKORO = "hexgrad/Kokoro-82M"
DEFAULT_VOICE = "bm_george"    # British male


class Kokoro:
    """Kokoro-82M with one English Voice: loaded once, then kept warm."""

    name = KOKORO.split("/")[-1]
    rate = 24000

    def __init__(self, device, voice):
        # the conversation is English (ADR 0001): American (a) or British (b),
        # female or male; the first letter is also Kokoro's language code
        if not re.fullmatch(r"[ab][fm]_[a-z]+", voice):
            raise RuntimeError(f"{voice!r} is not an English Kokoro Voice — pick one "
                               f"named af_*, am_*, bf_* or bm_*, such as {DEFAULT_VOICE}")
        try:
            from kokoro import KPipeline
        except ImportError:
            raise RuntimeError("Kokoro is not installed in this environment — "
                               "run voice_service/install.sh") from None
        with warnings.catch_warnings():       # torch's deprecation notes on every load
            warnings.simplefilter("ignore")
            self._pipeline = KPipeline(lang_code=voice[0], repo_id=KOKORO, device=device)
        try:
            self._pipeline.load_voice(voice)
        except Exception as e:                            # noqa: BLE001
            raise RuntimeError(f"cannot load Kokoro Voice {voice}: {e}") from None
        self.device = device
        self.voice = voice
        self.speak("Ready.")   # first call pays CUDA warm-up, not the user

    def speak(self, text):
        pcm = b"".join(r.audio.cpu().clamp(-1, 1).mul(32767).short().numpy().tobytes()
                       for r in self._pipeline(text, voice=self.voice)
                       if r.audio is not None)
        return _wav(self.rate, pcm)


def _wav(rate, pcm):
    """16-bit mono PCM -> WAV bytes."""
    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(rate)
        w.writeframes(pcm)
    return buf.getvalue()


def _silence(rate, seconds):
    return _wav(rate, b"\0\0" * int(rate * seconds))


def load_parakeet(args):
    return Parakeet(pick_device(args.allow_cpu))


def load_kokoro(args):
    return Kokoro(pick_device(args.allow_cpu), args.voice)


# name -> loader(args). Real loaders do their heavy imports inside.
HEARING = {
    "parakeet": load_parakeet,
    "fake": lambda args: FakeHearing(args.fake_heard),
}
SPEAKING = {
    "kokoro": load_kokoro,
    "fake": lambda args: FakeSpeaking(),
}
