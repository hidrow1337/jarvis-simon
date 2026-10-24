import pathlib
import re
import tempfile
import unittest

from tests.harness import (Dashboard, VoiceService, audio_clip, free_port,
                           run_voice_service, stub_env)


class HearCommandTest(unittest.TestCase):
    def test_hear_prints_what_was_heard_and_how_long_hearing_took(self):
        with tempfile.TemporaryDirectory() as tmp:
            clip = pathlib.Path(tmp, "clip.webm")
            clip.write_bytes(audio_clip("webm"))

            res = run_voice_service("hear", str(clip), "--hearing", "fake",
                                    "--fake-heard", "open the pod bay doors")

        self.assertEqual(res.returncode, 0, res.stderr)
        self.assertIn("open the pod bay doors", res.stdout)
        self.assertRegex(res.stdout, re.compile(r"Hearing\b.*\d+(\.\d+)?\s*s", re.I))

    def test_hear_on_a_file_that_is_not_audio_fails_with_a_readable_error(self):
        with tempfile.TemporaryDirectory() as tmp:
            junk = pathlib.Path(tmp, "notes.txt")
            junk.write_text("not audio at all\n" * 50)

            res = run_voice_service("hear", str(junk), "--hearing", "fake")

        self.assertNotEqual(res.returncode, 0)
        self.assertIn("could not decode", res.stderr)


class CudaRequiredTest(unittest.TestCase):
    """The real Hearing model with stub torch/NeMo (tests/stubs) standing in."""

    def test_service_refuses_to_start_without_cuda(self):
        res = run_voice_service("--hearing", "parakeet", "--speaking", "fake",
                                "--port", str(free_port()),
                                env=stub_env(), timeout=20)

        self.assertEqual(res.returncode, 1, res.stdout)
        self.assertIn("CUDA", res.stderr)
        self.assertIn("JARVIS_VOICE_ALLOW_CPU", res.stderr)


class ParakeetOnCpuTest(unittest.TestCase):
    """CPU explicitly allowed, so the real Hearing model loads (on stub NeMo)."""

    @classmethod
    def setUpClass(cls):
        cls.voice = VoiceService(stub_env(JARVIS_VOICE_ALLOW_CPU="1",
                                          STUB_HEARD="parakeet heard you"),
                                 hearing="parakeet").start()
        cls.addClassCleanup(cls.voice.stop)
        cls.dashboard = Dashboard({"JARVIS_VOICE_URL": cls.voice.url}).start()
        cls.addClassCleanup(cls.dashboard.stop)

    def test_recording_is_heard_by_parakeet(self):
        res = self.dashboard.post("/api/listen", audio_clip("webm"),
                                  content_type="audio/webm;codecs=opus")

        self.assertEqual(res.status, 200, res.body)
        self.assertEqual(res.json()["text"], "parakeet heard you")

    def test_status_names_parakeet_on_cpu(self):
        service = self.dashboard.get("/api/status").json()["voice_service"]

        self.assertTrue(service["online"])
        self.assertEqual(service["hearing_model"], "parakeet-tdt-0.6b-v3")
        self.assertEqual(service["device"], "cpu")

    def test_startup_log_says_loading_device_ready_and_port(self):
        log = self.voice.output()

        self.assertIn("loading Hearing model parakeet", log)
        self.assertIn("device cpu", log)
        self.assertIn(f"ready on http://127.0.0.1:{self.voice.port}", log)


if __name__ == "__main__":
    unittest.main()
