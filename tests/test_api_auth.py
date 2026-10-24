import unittest

from tests.harness import DashboardTestCase


class ApiAuthTest(DashboardTestCase):
    def test_post_with_origin_and_token_is_accepted(self):
        res = self.dashboard.post("/api/new", {})

        self.assertEqual(res.status, 200)
        self.assertEqual(res.json(), {"ok": True})

    def test_post_with_empty_token_is_rejected(self):
        res = self.dashboard.post("/api/new", {}, headers={"X-Jarvis-Token": ""})

        self.assertEqual(res.status, 401)

    def test_post_from_foreign_origin_is_rejected(self):
        res = self.dashboard.post("/api/new", {}, headers={"Origin": "http://evil.example"})

        self.assertEqual(res.status, 403)


if __name__ == "__main__":
    unittest.main()
