"""
The local voice-service: Hearing and Speaking for the dashboard, over HTTP on
127.0.0.1 only. Runs in its own environment (WSL2 + CUDA on the user's machine),
so the heavy model dependencies never reach the dashboard. See ADR 0001.

    python3 -m voice_service [options]             serve
    python3 -m voice_service hear <file> [options]  hear one audio file, print the text
    python3 -m voice_service roundtrip [text]       say a sentence, then hear it back
"""
import argparse
import os
import pathlib
import re
import sys
import time
from urllib.parse import urlparse

from voice_service import models, server

# Settings come from the environment, then the repo's .env (as for the
# dashboard), then the defaults below; command-line flags override all three.
_env = pathlib.Path(__file__).resolve().parent.parent / ".env"
if _env.exists():
    for line in _env.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            k, v = line.split("=", 1)
            os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))


def _hearing_options(p):
    p.add_argument("--hearing", choices=sorted(models.HEARING), default="parakeet",
                   help="Hearing model (default: parakeet)")
    p.add_argument("--fake-heard", default="fake hearing",
                   help="what the fake Hearing model hears")
    p.set_defaults(allow_cpu=os.environ.get("JARVIS_VOICE_ALLOW_CPU", "0") == "1")


def _speaking_options(p):
    p.add_argument("--speaking", choices=sorted(models.SPEAKING), default="kokoro",
                   help="Speaking model (default: kokoro)")
    voice = os.environ.get("JARVIS_VOICE") or models.DEFAULT_VOICE
    p.add_argument("--voice", default=voice,
                   help=f"Kokoro Voice (default: JARVIS_VOICE, else "
                        f"{models.DEFAULT_VOICE}; now {voice})")


def _log(msg):
    print(f"  voice-service · {msg}", flush=True)


def _load_hearing(args):
    _log(f"loading Hearing model {args.hearing}")
    t0 = time.monotonic()
    hearing = models.HEARING[args.hearing](args)
    _log(f"Hearing model {hearing.name} ready on {hearing.device} "
         f"in {time.monotonic() - t0:.1f} s")
    return hearing


def _load_speaking(args):
    _log(f"loading Speaking model {args.speaking} ({args.voice})")
    t0 = time.monotonic()
    speaking = models.SPEAKING[args.speaking](args)
    _log(f"Speaking model {speaking.name} ready on {speaking.device} "
         f"in {time.monotonic() - t0:.1f} s")
    return speaking


def _load_models(args):
    hearing, speaking = _load_hearing(args), _load_speaking(args)
    mem = models.gpu_memory()
    if mem:
        _log(f"GPU memory {mem}")
    return hearing, speaking


def serve(argv):
    p = argparse.ArgumentParser(prog="python3 -m voice_service",
                                description="Local Hearing and Speaking for Jarvis. "
                                            "Subcommand: hear <file>.")
    try:
        url_port = urlparse(os.environ.get("JARVIS_VOICE_URL", "")).port or 8731
    except ValueError:
        p.error(f"JARVIS_VOICE_URL has no valid port: {os.environ['JARVIS_VOICE_URL']}")
    p.add_argument("--port", type=int, default=url_port,
                   help=f"default: the port of JARVIS_VOICE_URL ({url_port})")
    _hearing_options(p)
    _speaking_options(p)
    args = p.parse_args(argv)

    try:
        hearing, speaking = _load_models(args)
    except Exception as e:                                # noqa: BLE001
        print(f"  voice-service · cannot start: {e}", file=sys.stderr, flush=True)
        return 1
    srv = server.make_server(args.port, hearing, speaking, args.voice)
    _log(f"ready on http://{server.HOST}:{args.port} · device {hearing.device}")
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        print("\n  voice-service · down.")
        srv.shutdown()


def hear(argv):
    """Smoke test for the Hearing model alone: one file in, its text out."""
    p = argparse.ArgumentParser(prog="python3 -m voice_service hear",
                                description="Hear one audio file and print the text.")
    p.add_argument("file", type=pathlib.Path, help="any audio file ffmpeg can read")
    _hearing_options(p)
    args = p.parse_args(argv)

    try:
        audio = args.file.read_bytes()
        hearing = _load_hearing(args)
        t0 = time.monotonic()
        wav = server.to_wav16k(audio, "audio/" + args.file.suffix.lstrip(".").lower())
        t1 = time.monotonic()
        text = (hearing.hear(wav) or "").strip()
        t2 = time.monotonic()
    except Exception as e:                                # noqa: BLE001
        print(f"  voice-service · hear failed: {e}", file=sys.stderr, flush=True)
        return 1
    print(f"\n  heard: {text!r}")
    print(f"  ffmpeg {t1 - t0:.2f} s · Hearing {t2 - t1:.2f} s")
    return 0


ROUNDTRIP_TEXT = "Good evening, sir. All systems are online and ready."


def roundtrip(argv):
    """Smoke test for both models at once: a sentence goes through Speaking,
    and the audio comes back through Hearing."""
    p = argparse.ArgumentParser(prog="python3 -m voice_service roundtrip",
                                description="Say a sentence with the Speaking model, "
                                            "hear it back with the Hearing model.")
    p.add_argument("text", nargs="?", default=ROUNDTRIP_TEXT,
                   help=f"what to say (default: {ROUNDTRIP_TEXT!r})")
    _hearing_options(p)
    _speaking_options(p)
    args = p.parse_args(argv)

    try:
        hearing, speaking = _load_models(args)
        t0 = time.monotonic()
        spoken = speaking.speak(args.text)
        t1 = time.monotonic()
        wav = server.to_wav16k(spoken, "audio/wav")
        t2 = time.monotonic()
        text = (hearing.hear(wav) or "").strip()
        t3 = time.monotonic()
    except Exception as e:                                # noqa: BLE001
        print(f"  voice-service · roundtrip failed: {e}", file=sys.stderr, flush=True)
        return 1
    print(f"\n  said:  {args.text!r}")
    print(f"  heard: {text!r}")
    print(f"  Speaking {t1 - t0:.2f} s · ffmpeg {t2 - t1:.2f} s · Hearing {t3 - t2:.2f} s")
    if _words(text) != _words(args.text):
        print("  MISMATCH: the heard words differ from the said ones")
        return 1
    print("  match: heard word for word what was said")
    return 0


def _words(text):
    """Text as its words, ignoring case and punctuation."""
    return re.findall(r"[a-z0-9']+", text.lower())


def main(argv=None):
    argv = sys.argv[1:] if argv is None else argv
    if argv[:1] == ["hear"]:
        return hear(argv[1:])
    if argv[:1] == ["roundtrip"]:
        return roundtrip(argv[1:])
    return serve(argv)


if __name__ == "__main__":
    sys.exit(main())
