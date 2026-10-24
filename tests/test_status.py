import unittest

from tests.harness import DashboardTestCase


class StatusTest(DashboardTestCase):
    def test_status_answers_with_runtime_and_no_session(self):
        res = self.dashboard.get("/api/status")

        self.assertEqual(res.status, 200)
        self.assertEqual(res.json()["runtime"], "mock")
        self.assertIsNone(res.json()["session"])


if __name__ == "__main__":
    unittest.main()
