import unittest
import urllib.error

from usage_health import LastGoodUsageStore, classify_http_error


class UsageHealthTests(unittest.TestCase):
    def test_http_statuses_are_machine_readable(self):
        cases = {
            401: ("auth_error", "auth"),
            403: ("auth_error", "auth"),
            429: ("rate_limited", "rate_limit"),
            500: ("server_error", "server"),
        }
        for status, expected in cases.items():
            with self.subTest(status=status):
                error = urllib.error.HTTPError("https://example.test", status, "", {}, None)
                usage = classify_http_error(error)
                self.assertEqual(expected, (usage["state"], usage["error_kind"]))

    def test_last_good_usage_is_preserved_and_marked_stale(self):
        store = LastGoodUsageStore()
        good = store.apply({
            "id": "claude",
            "ok": True,
            "windows": [{"id": "session", "remaining_pct": 63}],
            "meta": {"subscription": "max"},
            "error": None,
        }, now=100)
        self.assertFalse(good["usage"]["stale"])

        failed = store.apply({
            "id": "claude",
            "ok": False,
            "windows": [],
            "meta": {},
            "error": "timeout",
            "usage": {
                "state": "network_error",
                "last_success_at": None,
                "http_status": None,
                "error_kind": "network",
                "error": "timeout",
                "retry_after": None,
                "stale": False,
            },
        }, now=200)

        self.assertEqual(63, failed["windows"][0]["remaining_pct"])
        self.assertTrue(failed["usage"]["stale"])
        self.assertEqual(100, failed["usage"]["last_success_at"])


if __name__ == "__main__":
    unittest.main()
