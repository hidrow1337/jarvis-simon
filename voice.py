"""
Voice for the dashboard.

Hearing goes to the local voice-service at JARVIS_VOICE_URL (see voice_service/
and ADR 0001): the browser's recording is forwarded as-is and text comes back.

Speaking is still ElevenLabs when a key is present, browser speechSynthesis
otherwise. The key stays here, server-side. The browser asks /api/speak for
audio and gets mp3 bytes back — it never sees the key, so nothing leaks into
devtools, the page source, or a screen recording.
"""
import json
import os
import urllib.error
import urllib.request

# Rachel — calm, British-adjacent. Override with ELEVENLABS_VOICE_ID.
DEFAULT_VOICE = "21m00Tcm4TlvDq8ikWAM"
MODEL = os.environ.get("ELEVENLABS_MODEL", "eleven_turbo_v2_5")


def available():
    return bool(os.environ.get("ELEVENLABS_API_KEY"))


def voice_id():
    return os.environ.get("ELEVENLABS_VOICE_ID", DEFAULT_VOICE)


def speak(text):
    """Returns mp3 bytes, or raises. Caller decides what to do on failure."""
    if not available():
        raise RuntimeError("no ELEVENLABS_API_KEY")
    text = (text or "").strip()
    if not text:
        raise ValueError("empty text")

    req = urllib.request.Request(
        f"https://api.elevenlabs.io/v1/text-to-speech/{voice_id()}",
        data=json.dumps({
            "text": text[:2500],
            "model_id": MODEL,
            "voice_settings": {
                "stability": 0.42,          # a little variation; 0.5+ goes flat
                "similarity_boost": 0.85,
                "style": 0.25,
                "use_speaker_boost": True,
            },
        }).encode(),
        method="POST",
        headers={
            "content-type": "application/json",
            "accept": "audio/mpeg",
            "xi-api-key": os.environ["ELEVENLABS_API_KEY"],
        },
    )
    with urllib.request.urlopen(req, timeout=30) as r:
        return r.read()


def service_url():
    return os.environ.get("JARVIS_VOICE_URL", "http://127.0.0.1:8731").rstrip("/")


def _error_of(e):
    """A readable reason from a failed voice-service call."""
    if isinstance(e, urllib.error.HTTPError):
        try:
            return json.loads(e.read()).get("error") or f"HTTP {e.code}"
        except Exception:                              # noqa: BLE001
            return f"HTTP {e.code}"
    if isinstance(e, urllib.error.URLError):
        return f"voice-service offline ({e.reason})"
    return str(e)


def health():
    """The voice-service's /health, or None when it is offline or not ready.
    Short timeout: this runs on every status poll."""
    try:
        with urllib.request.urlopen(service_url() + "/health", timeout=1.5) as r:
            h = json.loads(r.read())
    except Exception:                                  # noqa: BLE001
        return None
    return h if isinstance(h, dict) and h.get("ready") else None


def transcribe(audio, mime="audio/webm"):
    """Hearing via the voice-service. Returns the text, or raises with a
    readable reason (service offline, bad audio, Hearing model failed)."""
    if not audio:
        raise ValueError("empty audio")
    req = urllib.request.Request(
        service_url() + "/hear", data=audio, method="POST",
        headers={"content-type": mime})
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            return (json.loads(r.read()).get("text") or "").strip()
    except Exception as e:                             # noqa: BLE001
        raise RuntimeError(_error_of(e)) from None


def voices():
    """List the account's voices, so you can find an id to put in .env."""
    if not available():
        return []
    req = urllib.request.Request(
        "https://api.elevenlabs.io/v2/voices",
        headers={"xi-api-key": os.environ["ELEVENLABS_API_KEY"]},
    )
    try:
        with urllib.request.urlopen(req, timeout=20) as r:
            body = json.loads(r.read())
    except Exception:                                  # noqa: BLE001
        return []
    return [dict(id=v.get("voice_id"), name=v.get("name"),
                 labels=v.get("labels", {}))
            for v in body.get("voices", [])]
