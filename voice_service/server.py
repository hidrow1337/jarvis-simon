"""HTTP front of the voice-service: /health, /hear and /speak."""
import json
import os
import subprocess
import tempfile
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse

HOST = "127.0.0.1"           # never the network: nobody else may use the models
MAX_AUDIO_BODY = 12 * 1024 * 1024
MAX_JSON_BODY = 1024 * 1024
FFMPEG_TIMEOUT = 30

# what the browser's MediaRecorder sends -> a file suffix ffmpeg can probe
_SUFFIX = {"audio/webm": ".webm", "audio/ogg": ".ogg", "audio/mp4": ".mp4",
           "audio/mpeg": ".mp3", "audio/wav": ".wav", "audio/x-wav": ".wav"}


class AudioError(ValueError):
    """The audio itself is unusable (empty, or ffmpeg can't decode it)."""


class ConversionError(RuntimeError):
    """The service can't convert audio at all (ffmpeg missing or hung)."""


def to_wav16k(audio, mime):
    """Any browser recording -> 16 kHz mono 16-bit WAV bytes, via ffmpeg.

    Goes through temp files rather than pipes: mp4 needs a seekable input, and
    a WAV written to a pipe has no real length in its header."""
    if not audio:
        raise AudioError("empty audio")
    with tempfile.TemporaryDirectory(prefix="jarvis-hear-") as tmp:
        src = os.path.join(tmp, "in" + _SUFFIX.get(mime, ".bin"))
        dst = os.path.join(tmp, "out.wav")
        with open(src, "wb") as f:
            f.write(audio)
        try:
            proc = subprocess.run(
                ["ffmpeg", "-hide_banner", "-loglevel", "error", "-nostdin",
                 "-i", src, "-ac", "1", "-ar", "16000", "-c:a", "pcm_s16le", dst],
                capture_output=True, timeout=FFMPEG_TIMEOUT)
        except FileNotFoundError:
            raise ConversionError("ffmpeg not found on PATH") from None
        except subprocess.TimeoutExpired:
            raise ConversionError(f"ffmpeg took over {FFMPEG_TIMEOUT}s") from None
        if proc.returncode != 0:
            msg = proc.stderr.decode(errors="replace").strip().splitlines()
            raise AudioError("ffmpeg could not decode the audio: "
                             + (msg[-1] if msg else f"exit {proc.returncode}"))
        with open(dst, "rb") as f:
            return f.read()


def make_server(port, hearing, speaking, voice):
    model_lock = threading.Lock()     # one model call at a time on the GPU

    class Handler(BaseHTTPRequestHandler):
        protocol_version = "HTTP/1.1"

        def log_message(self, fmt, *args):
            pass

        def _bytes(self, data, ctype, code=200):
            self.send_response(code)
            self.send_header("Content-Type", ctype)
            self.send_header("Content-Length", str(len(data)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(data)

        def _json(self, body, code=200):
            self._bytes(json.dumps(body).encode(), "application/json", code)

        def _host_ok(self):
            # same DNS-rebinding guard as the dashboard
            return self.headers.get("Host", "") in {f"127.0.0.1:{port}", f"localhost:{port}"}

        def do_GET(self):
            if not self._host_ok():
                return self._json({"error": "invalid host"}, 403)
            if urlparse(self.path).path == "/health":
                return self._json(dict(
                    ready=True,
                    hearing_model=hearing.name,
                    speaking_model=speaking.name,
                    voice=voice,
                    device=hearing.device))
            return self._json({"error": "no such endpoint"}, 404)

        def _body(self, limit):
            """The request body, or None after answering 413."""
            try:
                n = int(self.headers.get("Content-Length", 0))
            except ValueError:
                n = -1
            if n < 0 or n > limit:
                self.close_connection = True
                self._json({"error": "request body too large"}, 413)
                return None
            return self.rfile.read(n) if n else b""

        def do_POST(self):
            if not self._host_ok():
                return self._json({"error": "invalid host"}, 403)
            path = urlparse(self.path).path
            mime = self.headers.get("Content-Type", "").split(";", 1)[0].strip().lower()
            if path == "/hear":
                return self._hear(mime)
            if path == "/speak":
                return self._speak(mime)
            return self._json({"error": "no such endpoint"}, 404)

        def _hear(self, mime):
            if not mime.startswith("audio/"):
                return self._json({"error": "audio content type required"}, 415)
            audio = self._body(MAX_AUDIO_BODY)
            if audio is None:
                return
            try:
                wav = to_wav16k(audio, mime)
                with model_lock:
                    text = hearing.hear(wav)
            except AudioError as e:
                return self._json({"error": str(e)[:300]}, 400)
            except ConversionError as e:
                return self._json({"error": str(e)[:300]}, 500)
            except Exception as e:                        # noqa: BLE001
                return self._json({"error": f"Hearing model failed: {e}"[:300]}, 500)
            return self._json({"text": (text or "").strip()})

        def _speak(self, mime):
            if mime != "application/json":
                return self._json({"error": "application/json required"}, 415)
            raw = self._body(MAX_JSON_BODY)
            if raw is None:
                return
            try:
                text = json.loads(raw or b"{}").get("text")
            except (ValueError, AttributeError):
                return self._json({"error": "bad json"}, 400)
            text = text.strip() if isinstance(text, str) else ""
            if not text:
                return self._json({"error": "empty text"}, 400)
            try:
                with model_lock:
                    wav = speaking.speak(text)
            except Exception as e:                        # noqa: BLE001
                return self._json({"error": f"Speaking model failed: {e}"[:300]}, 500)
            return self._bytes(wav, "audio/wav")

    return ThreadingHTTPServer((HOST, port), Handler)
