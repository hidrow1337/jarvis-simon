import io
import json
import unittest
import wave

from tests.harness import VoiceTestCase


class SpeakingTest(VoiceTestCase):
    def test_answer_is_spoken_as_wav(self):
        res = self.dashboard.post("/api/speak", {"text": "Good evening, sir."})

        self.assertEqual(res.status, 200, res.body)
        self.assertEqual(res.headers["Content-Type"], "audio/wav")
        with wave.open(io.BytesIO(res.body)) as w:
            self.assertGreater(w.getnframes(), 0)

    def test_service_refusing_the_text_fails_with_503_and_its_reason(self):
        res = self.dashboard.post("/api/speak", {"text": "   "})

        self.assertEqual(res.status, 503)
        self.assertEqual(res.json()["error"], "empty text")

    def test_speak_keeps_its_request_checks(self):
        cases = [
            ("no token", 401, dict(headers={"X-Jarvis-Token": ""})),
            ("foreign origin", 403, dict(headers={"Origin": "http://evil.example"})),
            ("not json", 415, dict(content_type="text/plain")),
            ("too large", 413, dict(headers={"Content-Length": str(1024 * 1024 + 1)})),
        ]
        for name, status, kwargs in cases:
            with self.subTest(name):
                res = self.dashboard.post("/api/speak", {"text": "Good evening, sir."}, **kwargs)

                self.assertEqual(res.status, status, res.body)

    def test_status_command_says_voice_is_local(self):
        res = self.dashboard.post("/api/run", {"message": "/status"})
        reply = "".join(ev.get("text", "") for ev in map(json.loads, res.body.splitlines()))

        self.assertIn("voice=local voice-service", reply)
        self.assertNotIn("ElevenLabs", reply)


class SpeakingWithServiceStoppedTest(VoiceTestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.voice.stop()

    def test_speak_fails_with_503_and_says_the_service_is_offline(self):
        res = self.dashboard.post("/api/speak", {"text": "Good evening, sir."})

        self.assertEqual(res.status, 503)
        self.assertIn("voice-service offline", res.json()["error"])


if __name__ == "__main__":
    unittest.main()
