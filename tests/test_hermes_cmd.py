import os
import stat
import sys
import tempfile
import unittest

from tests.harness import Dashboard

# Answers `--version` and `tools list` the way the dashboard asks Hermes at startup.
_FAKE_HERMES = f"""#!{sys.executable}
print("hermes fake 0.0")
"""


def fake_hermes(path):
    """Writes an executable stand-in for the Hermes CLI at `path`."""
    with open(path, "w", encoding="utf-8") as f:
        f.write(_FAKE_HERMES)
    os.chmod(path, os.stat(path).st_mode | stat.S_IXUSR)
    return path


class HermesCmdTest(unittest.TestCase):
    """HERMES_CMD as the user writes it in .env, with JARVIS_RUNTIME=auto so the
    dashboard really tries to start it."""

    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.tmp = tmp.name

    def dashboard(self, hermes_cmd):
        dash = Dashboard({"JARVIS_RUNTIME": "auto", "HERMES_CMD": hermes_cmd}).start()
        self.addCleanup(dash.stop)
        return dash

    def test_path_with_backslashes_and_spaces_starts_hermes(self):
        # A Windows path, as one file name: Linux can't have C:\ folders, but the
        # backslashes and the space are what HERMES_CMD used to mangle.
        exe = fake_hermes(os.path.join(self.tmp, r"Program Files\Hermes\hermes.exe"))

        res = self.dashboard(exe).get("/api/status")

        self.assertEqual(res.json()["runtime"], "hermes")

    def test_command_with_arguments_starts_hermes(self):
        # like `python3 -m hermes_cli.main`: an interpreter plus what it runs
        script = fake_hermes(os.path.join(self.tmp, "hermes_cli.py"))

        res = self.dashboard(f"{sys.executable} {script}").get("/api/status")

        self.assertEqual(res.json()["runtime"], "hermes")

    def test_banner_names_a_hermes_cmd_that_does_not_start(self):
        missing = os.path.join(self.tmp, r"Program Files\Hermes\hermes.exe")

        banner = self.dashboard(missing).output()

        self.assertIn(f"MOCK — could not start Hermes with HERMES_CMD={missing}", banner)
        self.assertIn("No such file or directory", banner)
        self.assertNotIn("Hermes CLI not reachable", banner)


if __name__ == "__main__":
    unittest.main()
