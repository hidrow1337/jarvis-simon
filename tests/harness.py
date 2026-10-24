"""
Test harness: runs the real dashboard (`server.py`) as a subprocess on a free
port and talks to it over HTTP the way the browser does — correct Host, Origin
and X-Jarvis-Token headers.

    python3 -m unittest

Stdlib only. The dashboard runs with the mock runtime, a Hermes command that
doesn't exist, its browser auto-open off and its state file in a temp dir, so
tests never launch Hermes or write the repo's state.json. Inherited JARVIS_*,
HERMES_* and ELEVENLABS_* variables are dropped; note that server.py still
reads the repo's .env for any key the harness doesn't set.
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
_OWN_ENV = ("JARVIS_", "HERMES_", "ELEVENLABS_")


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


class Dashboard:
    """The dashboard server under test. `env` overrides its environment."""

    def __init__(self, env=None):
        self.port = free_port()
        self.token = None
        self._env = env or {}
        self._proc = None
        self._log = None
        self._tmp = None

    @property
    def origin(self):
        return f"http://127.0.0.1:{self.port}"

    def start(self, timeout=10):
        self._tmp = tempfile.TemporaryDirectory()
        env = {k: v for k, v in os.environ.items() if not k.startswith(_OWN_ENV)}
        env.update({
            "JARVIS_PORT": str(self.port),
            "JARVIS_OPEN": "0",
            "JARVIS_RUNTIME": "mock",
            "HERMES_CMD": os.path.join(self._tmp.name, "no-hermes"),
            "JARVIS_STATE": os.path.join(self._tmp.name, "state.json"),
            "PYTHONUNBUFFERED": "1",
        })
        env.update(self._env)
        self._log = open(os.path.join(self._tmp.name, "server.log"), "w+b")
        self._proc = subprocess.Popen(
            [sys.executable, "server.py"], cwd=ROOT, env=env,
            stdout=self._log, stderr=subprocess.STDOUT)
        try:
            page = self._wait_until_up(time.monotonic() + timeout)
            match = _TOKEN_META.search(page.body)
            if not match:
                raise RuntimeError(f"no jarvis-token on / (HTTP {page.status})")
            self.token = match.group(1).decode()
        except BaseException:
            self.stop()
            raise
        return self

    def _wait_until_up(self, deadline):
        while True:
            if self._proc.poll() is not None:
                self._log.seek(0)
                out = self._log.read().decode(errors="replace")
                raise RuntimeError(f"dashboard exited early:\n{out}")
            left = deadline - time.monotonic()
            if left <= 0:
                raise RuntimeError("dashboard did not start in time")
            try:
                return self.request("GET", "/", timeout=left)
            except OSError:
                time.sleep(0.05)

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
        """Raw request: only the Host header is set. Use get/post for API calls."""
        conn = http.client.HTTPConnection("127.0.0.1", self.port, timeout=timeout)
        try:
            conn.request(method, path, body=body,
                         headers={"Host": f"127.0.0.1:{self.port}", **(headers or {})})
            res = conn.getresponse()
            return Response(res.status, dict(res.getheaders()), res.read())
        finally:
            conn.close()

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


class DashboardTestCase(unittest.TestCase):
    """One dashboard per test class, as `self.dashboard`."""

    dashboard_env = None

    @classmethod
    def setUpClass(cls):
        cls.dashboard = Dashboard(cls.dashboard_env).start()
        cls.addClassCleanup(cls.dashboard.stop)
