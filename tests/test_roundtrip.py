import re
import unittest

from tests.harness import run_voice_service, stub_env


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


class RoundTripOnGpuTest(unittest.TestCase):
    """Both real models on a (stub) GPU, as the user runs it in WSL."""

    def test_roundtrip_through_both_real_models_reports_gpu_memory(self):
        res = run_voice_service("roundtrip", "--hearing", "parakeet", "--speaking", "kokoro",
                                env=stub_env(STUB_CUDA="1", STUB_HEARD="good evening sir"))

        self.assertEqual(res.returncode, 0, res.stderr)
        self.assertIn("device cuda (Stub GPU)", res.stdout)
        self.assertIn("Kokoro-82M ready on cuda", res.stdout)
        self.assertIn("heard: 'good evening sir'", res.stdout)
        self.assertIn("GPU memory 3.0 of 12.0 GB in use", res.stdout)


if __name__ == "__main__":
    unittest.main()
