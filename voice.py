"""
Voice for the dashboard: a thin client to the local voice-service at
JARVIS_VOICE_URL (see voice_service/ and ADR 0001).

Hearing: the browser's recording is forwarded as-is and text comes back.
Speaking: Jarvis's answer goes out as text and the whole answer comes back as
WAV, which the browser plays. There is no fallback: if the service is down,
voice is off and only typed chat works.
"""
import json
import os
import urllib.error
import urllib.request


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


def _call(path, data, ctype, timeout):
    """POST to the voice-service; the response bytes, or raises with a reason."""
    req = urllib.request.Request(service_url() + path, data=data, method="POST",
                                 headers={"content-type": ctype})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.read()
    except Exception as e:                             # noqa: BLE001
        raise RuntimeError(_error_of(e)) from None


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
    body = _call("/hear", audio, mime, timeout=60)
    return (json.loads(body).get("text") or "").strip()


def speak(text):
    """Speaking via the voice-service. Returns WAV bytes of the whole answer,
    or raises with a readable reason (service offline, empty text, Speaking
    model failed). The service checks the text, so its reason comes through."""
    return _call("/speak", json.dumps({"text": text or ""}).encode(), "application/json",
                 timeout=60)
