"""
Test harness: runs the real dashboard (`server.py`) as a subprocess on a free
port and talks to it over HTTP the way the browser does — correct Host, Origin
and X-Jarvis-Token headers. `VoiceService` runs the real voice-service the same
way, with fake Hearing/Speaking models injected.

    python3 -m unittest

Stdlib only. The dashboard runs with the mock runtime, a Hermes command that
doesn't exist, its browser auto-open off and its state file in a temp dir, so
tests never launch Hermes or write the repo's state.json. Unless a test points
JARVIS_VOICE_URL at a running voice-service, it points at a closed port, so the
voice-service is offline. Inherited JARVIS_* and HERMES_* variables are
dropped; note that server.py still reads the repo's .env for any
key the harness doesn't set.
"""
import http.client
import json
import os
import pathlib
import re
import socket
import subprocess
import sys
import tempfile
import time
import unittest

ROOT = pathlib.Path(__file__).resolve().parent.parent
_TOKEN_META = re.compile(rb'<meta name="jarvis-token" content="([^"]+)">')
_OWN_ENV = ("JARVIS_", "HERMES_")


def free_port():
    # Racy (the port is free again before server.py binds it), but good enough
    # for tests; a stolen port shows up as "dashboard exited early".
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


class Response:
    def __init__(self, status, headers, body):
        self.status = status
        self.headers = headers
        self.body = body

    def json(self):
        return json.loads(self.body)


class _ServerProcess:
    """A server under test, run as a subprocess on a free port with its own temp
    dir. Subclasses say how to launch it and which GET answers once it is up."""

    name = "server"
    ready_path = "/"

    def __init__(self, env=None):
        self.port = free_port()
        self._env = env or {}
        self._proc = None
        self._log = None
        self._tmp = None

    def argv(self):
        raise NotImplementedError

    def child_env(self, tmp):
        return {}

    def on_ready(self, res):
        pass

    def start(self, timeout=10):
        self._tmp = tempfile.TemporaryDirectory()
        env = {k: v for k, v in os.environ.items() if not k.startswith(_OWN_ENV)}
        env["PYTHONUNBUFFERED"] = "1"
        env.update(self.child_env(self._tmp.name))
        env.update(self._env)
        self._log = open(os.path.join(self._tmp.name, "server.log"), "w+b")
        self._proc = subprocess.Popen(
            self.argv(), cwd=ROOT, env=env,
            stdout=self._log, stderr=subprocess.STDOUT)
        try:
            self.on_ready(self._wait_until_up(time.monotonic() + timeout))
        except BaseException:
            self.stop()
            raise
        return self

    def _wait_until_up(self, deadline):
        while True:
            if self._proc.poll() is not None:
                raise RuntimeError(f"{self.name} exited early:\n{self.output()}")
            left = deadline - time.monotonic()
            if left <= 0:
                raise RuntimeError(f"{self.name} did not start in time:\n{self.output()}")
            try:
                return self.request("GET", self.ready_path, timeout=left)
            except OSError:
                time.sleep(0.05)

    def output(self):
        """Everything the server has printed so far."""
        self._log.seek(0)
        return self._log.read().decode(errors="replace")

    def stop(self):
        if self._proc and self._proc.poll() is None:
            self._proc.terminate()
            try:
                self._proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                self._proc.kill()
                self._proc.wait()
        if self._log:
            self._log.close()
        if self._tmp:
            self._tmp.cleanup()
        self._proc = self._log = self._tmp = None

    def request(self, method, path, body=None, headers=None, timeout=30):
        """Raw request: only the Host header is set."""
        conn = http.client.HTTPConnection("127.0.0.1", self.port, timeout=timeout)
        try:
            conn.request(method, path, body=body,
                         headers={"Host": f"127.0.0.1:{self.port}", **(headers or {})})
            res = conn.getresponse()
            return Response(res.status, dict(res.getheaders()), res.read())
        finally:
            conn.close()


class Dashboard(_ServerProcess):
    """The dashboard server under test. `env` overrides its environment."""

    name = "dashboard"

    def __init__(self, env=None):
        super().__init__(env)
        self.token = None

    @property
    def origin(self):
        return f"http://127.0.0.1:{self.port}"

    def argv(self):
        return [sys.executable, "server.py"]

    def child_env(self, tmp):
        return {
            "JARVIS_PORT": str(self.port),
            "JARVIS_OPEN": "0",
            "JARVIS_RUNTIME": "mock",
            "HERMES_CMD": os.path.join(tmp, "no-hermes"),
            "JARVIS_STATE": os.path.join(tmp, "state.json"),
            "JARVIS_VOICE_URL": f"http://127.0.0.1:{free_port()}",
        }

    def on_ready(self, page):
        match = _TOKEN_META.search(page.body)
        if not match:
            raise RuntimeError(f"no jarvis-token on / (HTTP {page.status})")
        self.token = match.group(1).decode()

    def _api_headers(self, headers):
        return {"Origin": self.origin, "X-Jarvis-Token": self.token, **(headers or {})}

    def get(self, path, headers=None):
        return self.request("GET", path, headers=self._api_headers(headers))

    def post(self, path, body=b"", content_type="application/json", headers=None):
        """POST with Origin + token. A dict/list body is sent as JSON."""
        if isinstance(body, (dict, list)):
            body = json.dumps(body).encode()
        return self.request("POST", path, body=body,
                            headers=self._api_headers({"Content-Type": content_type, **(headers or {})}))


FAKE_HEARD = "the fake hearing model heard you"


class VoiceService(_ServerProcess):
    """The real voice-service, with fake Hearing and Speaking models injected.
    The fake Hearing model answers FAKE_HEARD for any 16 kHz mono WAV.
    `hearing="parakeet"` runs the real Hearing model instead (with stub_env(),
    against the stub NeMo)."""

    name = "voice-service"
    ready_path = "/health"

    def __init__(self, env=None, hearing="fake"):
        super().__init__(env)
        self.hearing = hearing
        self.url = f"http://127.0.0.1:{self.port}"

    def argv(self):
        return [sys.executable, "-m", "voice_service",
                "--hearing", self.hearing, "--speaking", "fake", "--fake-heard", FAKE_HEARD]

    def child_env(self, tmp):
        # the same setting the dashboard reads; the service listens on its port
        return {"JARVIS_VOICE_URL": self.url}


def run_voice_service(*args, env=None, timeout=60):
    """Runs `python3 -m voice_service <args>` to completion and returns the
    CompletedProcess (text stdout/stderr). Inherited JARVIS_* variables are
    dropped, as for the servers."""
    full_env = {k: v for k, v in os.environ.items() if not k.startswith(_OWN_ENV)}
    full_env["PYTHONUNBUFFERED"] = "1"
    full_env.update(env or {})
    return subprocess.run([sys.executable, "-m", "voice_service", *args],
                          cwd=ROOT, env=full_env, capture_output=True, text=True,
                          timeout=timeout)


STUBS = ROOT / "tests" / "stubs"


def stub_env(**env):
    """Environment that puts the stub torch and NeMo packages (tests/stubs) on
    the voice-service's import path, plus `env`. CPU is not allowed unless
    `env` says so, whatever the repo's .env holds."""
    return {"PYTHONPATH": str(STUBS), "JARVIS_VOICE_ALLOW_CPU": "0", **env}


def audio_clip(fmt, seconds=1.0):
    """A short tone encoded the way a browser's MediaRecorder might send it:
    fmt is "webm" (opus), "ogg" (opus) or "mp4" (aac). Needs ffmpeg on PATH."""
    codec = {"webm": "libopus", "ogg": "libopus", "mp4": "aac"}[fmt]
    with tempfile.TemporaryDirectory() as tmp:
        out = os.path.join(tmp, f"clip.{fmt}")
        subprocess.run(
            ["ffmpeg", "-hide_banner", "-loglevel", "error", "-f", "lavfi",
             "-i", f"sine=frequency=440:duration={seconds}:sample_rate=48000",
             "-ac", "2", "-c:a", codec, out],
            check=True)
        return pathlib.Path(out).read_bytes()


class DashboardTestCase(unittest.TestCase):
    """One dashboard per test class, as `self.dashboard`."""

    dashboard_env = None

    @classmethod
    def setUpClass(cls):
        cls.dashboard = Dashboard(cls.dashboard_env).start()
        cls.addClassCleanup(cls.dashboard.stop)


class VoiceTestCase(unittest.TestCase):
    """A voice-service with fake models (`self.service`) and a dashboard pointed
    at it (`self.dashboard`), one of each per test class."""

    @classmethod
    def setUpClass(cls):
        cls.service = VoiceService().start()
        cls.addClassCleanup(cls.service.stop)
        cls.dashboard = Dashboard({"JARVIS_VOICE_URL": cls.service.url}).start()
        cls.addClassCleanup(cls.dashboard.stop)
