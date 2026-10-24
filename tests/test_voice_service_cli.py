import io
import pathlib
import re
import tempfile
import unittest
import wave

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


class KokoroOnCpuTest(unittest.TestCase):
    """CPU explicitly allowed, so the real Speaking model loads (on stub Kokoro)."""

    @classmethod
    def setUpClass(cls):
        cls.voice = VoiceService(stub_env(JARVIS_VOICE_ALLOW_CPU="1"),
                                 speaking="kokoro").start()
        cls.addClassCleanup(cls.voice.stop)
        cls.dashboard = Dashboard({"JARVIS_VOICE_URL": cls.voice.url}).start()
        cls.addClassCleanup(cls.dashboard.stop)

    def test_answer_is_spoken_by_kokoro_as_24khz_wav(self):
        res = self.dashboard.post("/api/speak", {"text": "Good evening, sir. Shall I begin?"})

        self.assertEqual(res.status, 200, res.body)
        self.assertEqual(res.headers["Content-Type"], "audio/wav")
        with wave.open(io.BytesIO(res.body)) as w:
            self.assertEqual((w.getframerate(), w.getnchannels(), w.getsampwidth()),
                             (24000, 1, 2))
            self.assertGreater(w.getnframes(), 0)

    def test_status_names_kokoro_and_the_default_voice(self):
        service = self.dashboard.get("/api/status").json()["voice_service"]

        self.assertTrue(service["online"])
        self.assertEqual(service["speaking_model"], "Kokoro-82M")
        self.assertEqual(service["voice"], "bm_george")


class VoiceFromConfigTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.voice = VoiceService(stub_env(JARVIS_VOICE_ALLOW_CPU="1", JARVIS_VOICE="af_heart"),
                                 speaking="kokoro").start()
        cls.addClassCleanup(cls.voice.stop)
        cls.dashboard = Dashboard({"JARVIS_VOICE_URL": cls.voice.url}).start()
        cls.addClassCleanup(cls.dashboard.stop)

    def test_status_names_the_configured_voice(self):
        service = self.dashboard.get("/api/status").json()["voice_service"]

        self.assertEqual(service["voice"], "af_heart")

    def test_configured_voice_speaks(self):
        res = self.dashboard.post("/api/speak", {"text": "Good evening."})

        self.assertEqual(res.status, 200, res.body)


class WrongVoiceTest(unittest.TestCase):
    def test_service_refuses_to_start_with_a_voice_it_cannot_speak(self):
        cases = [
            ("not English", "ff_siwis", "not an English Kokoro Voice"),
            ("no such voice", "bm_nobody", "cannot load Kokoro Voice bm_nobody"),
        ]
        for name, voice, reason in cases:
            with self.subTest(name):
                res = run_voice_service("--hearing", "fake", "--speaking", "kokoro",
                                        "--port", str(free_port()),
                                        env=stub_env(JARVIS_VOICE_ALLOW_CPU="1",
                                                     JARVIS_VOICE=voice), timeout=20)

                self.assertEqual(res.returncode, 1, res.stdout)
                self.assertIn(reason, res.stderr)


class RoundTripCommandTest(unittest.TestCase):
    def test_roundtrip_prints_said_and_heard_text_and_time_per_step(self):
        res = run_voice_service("roundtrip", "Good evening, sir.",
                                "--hearing", "fake", "--speaking", "fake",
                                "--fake-heard", "good evening sir")

        self.assertEqual(res.returncode, 0, res.stderr)
        self.assertIn("Good evening, sir.", res.stdout)
        self.assertIn("good evening sir", res.stdout)
        for step in ("Speaking", "Hearing"):
            self.assertRegex(res.stdout, re.compile(rf"{step}\s+\d+\.\d+\s*s"))
        self.assertIn("match", res.stdout)

    def test_roundtrip_fails_when_the_heard_text_differs_from_the_said_text(self):
        res = run_voice_service("roundtrip", "Good evening, sir.",
                                "--hearing", "fake", "--speaking", "fake",
                                "--fake-heard", "good heavens, sir")

        self.assertEqual(res.returncode, 1, res.stdout)
        self.assertIn("MISMATCH", res.stdout)


class RoundTripOnGpuTest(unittest.TestCase):
    """Both real models on a (stub) GPU, as the user runs it in WSL."""

    def test_roundtrip_through_both_real_models_reports_gpu_memory(self):
        res = run_voice_service("roundtrip", "--hearing", "parakeet", "--speaking", "kokoro",
                                env=stub_env(STUB_CUDA="1", STUB_HEARD="Good evening, sir. All systems are online and ready."))

        self.assertEqual(res.returncode, 0, res.stderr)
        self.assertIn("device cuda (Stub GPU)", res.stdout)
        self.assertIn("Kokoro-82M ready on cuda", res.stdout)
        self.assertIn("heard: 'Good evening, sir. All systems are online and ready.'", res.stdout)
        self.assertIn("GPU memory 3.0 of 12.0 GB in use", res.stdout)


if __name__ == "__main__":
    unittest.main()
