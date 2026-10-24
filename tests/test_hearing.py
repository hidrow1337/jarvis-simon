import unittest

from tests.harness import FAKE_HEARD, VoiceTestCase, audio_clip


class HearingTest(VoiceTestCase):
    def test_webm_recording_is_heard_as_text(self):
        res = self.dashboard.post("/api/listen", audio_clip("webm"),
                                  content_type="audio/webm;codecs=opus")

        self.assertEqual(res.status, 200, res.body)
        self.assertEqual(res.json()["text"], FAKE_HEARD)

    def test_ogg_and_mp4_recordings_are_heard_as_text(self):
        for fmt in ("ogg", "mp4"):
            with self.subTest(fmt):
                res = self.dashboard.post("/api/listen", audio_clip(fmt),
                                          content_type=f"audio/{fmt}")

                self.assertEqual(res.status, 200, res.body)
                self.assertEqual(res.json()["text"], FAKE_HEARD)

    def test_undecodable_recording_fails_with_a_readable_error(self):
        res = self.dashboard.post("/api/listen", b"not audio at all" * 200,
                                  content_type="audio/webm")

        self.assertEqual(res.status, 503)
        self.assertIn("could not decode", res.json()["error"])

    def test_status_reports_voice_service_online_with_health_details(self):
        service = self.dashboard.get("/api/status").json()["voice_service"]

        self.assertEqual(service, {
            "online": True,
            "hearing_model": "fake",
            "speaking_model": "fake",
            "voice": "bm_george",
            "device": "cpu",
        })

    def test_voice_service_poll_reports_the_same_as_status(self):
        res = self.dashboard.get("/api/voice-service")

        self.assertEqual(res.status, 200)
        self.assertEqual(res.json(), self.dashboard.get("/api/status").json()["voice_service"])
        self.assertTrue(res.json()["online"])

    def test_listen_keeps_its_request_checks(self):
        clip = audio_clip("webm")
        cases = [
            ("no token", 401, dict(headers={"X-Jarvis-Token": ""})),
            ("foreign origin", 403, dict(headers={"Origin": "http://evil.example"})),
            ("not audio", 415, dict(content_type="application/json")),
            ("too large", 413, dict(headers={"Content-Length": str(12 * 1024 * 1024 + 1)})),
        ]
        for name, status, kwargs in cases:
            with self.subTest(name):
                res = self.dashboard.post("/api/listen", clip,
                                          **{"content_type": "audio/webm", **kwargs})

                self.assertEqual(res.status, status, res.body)


class HearingWithServiceStoppedTest(VoiceTestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.service.stop()

    def test_status_reports_voice_service_offline(self):
        service = self.dashboard.get("/api/status").json()["voice_service"]

        self.assertEqual(service, {"online": False})

    def test_voice_service_poll_reports_offline(self):
        self.assertEqual(self.dashboard.get("/api/voice-service").json(), {"online": False})

    def test_listen_fails_with_503_and_says_the_service_is_offline(self):
        res = self.dashboard.post("/api/listen", audio_clip("webm"),
                                  content_type="audio/webm")

        self.assertEqual(res.status, 503)
        self.assertIn("voice-service offline", res.json()["error"])


if __name__ == "__main__":
    unittest.main()
