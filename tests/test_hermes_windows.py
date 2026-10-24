import json
import os
import sys
import tempfile
import unittest

from tests.harness import Dashboard
from tests.test_hermes_cmd import fake_hermes

# Behaves like Hermes Agent v0.22.5 as #8 found it on Windows: it writes UTF-8
# whatever the locale, and `chat` refuses a --source it doesn't know.
_HERMES_0_22_5 = f"""#!{sys.executable}
import sys

def say(text):
    sys.stdout.buffer.write((text + "\\n").encode("utf-8"))

args = sys.argv[1:]
if args == ["--version"]:
    say("Hermes Agent v0.22.5")
elif args[:2] == ["tools", "list"]:
    say("─── Enabled toolsets ───")
    say("✓ web — Web Search & Scraping")
    say("✓ browser — Browser Automation")
elif args[:1] == ["chat"]:
    source = args[args.index("--source") + 1] if "--source" in args else "cli"
    if source not in ("tool", "cli"):
        say("Hermes couldn't start the model connection: invalid_params")
        raise SystemExit(1)
    say(f"Online — source {{source}} ─ at your service")
"""

# A locale that isn't UTF-8, as on a Danish Windows (cp1252): the dashboard
# must not decode Hermes with it. The console stays UTF-8, as on Windows.
# Chat can't run in it on Linux: there the locale also encodes argv, and the
# persona's dashes don't fit (Windows passes argv as Unicode).
_NOT_UTF8 = {"LC_ALL": "C", "PYTHONUTF8": "0", "PYTHONCOERCECLOCALE": "0",
             "PYTHONIOENCODING": "utf-8"}


def reply(res):
    evs = [json.loads(line) for line in res.body.decode().splitlines()]
    errors = [e["message"] for e in evs if e["t"] == "error"]
    if errors:
        raise AssertionError(f"run failed: {errors}")
    return "".join(e.get("text", "") for e in evs if e["t"] == "delta")


class HermesOnWindowsTest(unittest.TestCase):
    """The dashboard against a Hermes that acts like v0.22.5."""

    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.hermes = fake_hermes(os.path.join(tmp.name, "hermes"), _HERMES_0_22_5)

    def dashboard(self, **env):
        dash = Dashboard({"JARVIS_RUNTIME": "auto", "HERMES_CMD": self.hermes,
                          **env}).start()
        self.addCleanup(dash.stop)
        return dash

    def test_chat_reply_with_non_ascii_comes_through(self):
        res = self.dashboard().post("/api/run", {"message": "Say online"})

        self.assertIn("Online — source tool ─ at your service", reply(res))

    def test_does_not_send_source_jarvis_dashboard(self):
        # Hermes v0.22.5 rejects any --source it doesn't know, this one included
        text = reply(self.dashboard().post("/api/run", {"message": "Say online"}))

        self.assertIn("source tool", text)

    def test_hermes_source_still_sets_the_source(self):
        res = self.dashboard(HERMES_SOURCE="cli").post("/api/run", {"message": "Say online"})

        self.assertIn("source cli", reply(res))

    def test_tool_list_with_non_ascii_comes_through(self):
        tools = self.dashboard(**_NOT_UTF8).get("/api/status").json()["tools"]

        self.assertIn("✓ web — Web Search & Scraping", tools)
        self.assertIn("✓ browser — Browser Automation", tools)

    def test_tools_command_with_non_ascii_comes_through(self):
        res = self.dashboard(**_NOT_UTF8).post("/api/run", {"message": "/tools"})

        self.assertIn("✓ web — Web Search & Scraping", reply(res))

    def test_starts_without_syntax_warning(self):
        # a fresh bytecode cache, so every module is compiled (and warned about) again
        with tempfile.TemporaryDirectory() as cache:
            output = self.dashboard(PYTHONPYCACHEPREFIX=cache).output()

        self.assertNotIn("SyntaxWarning", output)


if __name__ == "__main__":
    unittest.main()
