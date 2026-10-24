import io
import unittest
import wave

from tests.harness import Dashboard, VoiceService, free_port, run_voice_service, stub_env


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


if __name__ == "__main__":
    unittest.main()
