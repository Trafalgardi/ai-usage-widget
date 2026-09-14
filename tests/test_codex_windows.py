import json
import unittest
from unittest.mock import mock_open, patch

import widget


class CodexWindowTests(unittest.TestCase):
    def fetch(self, primary, secondary=None):
        payload = {"plan_type": "prolite", "rate_limit": {"primary_window": primary, "secondary_window": secondary}}
        auth = json.dumps({"tokens": {"access_token": "test", "account_id": "test"}})
        with patch("widget.os.path.exists", return_value=True), patch("builtins.open", mock_open(read_data=auth)), patch("widget.http_get_json", return_value=payload):
            return widget.fetch_codex()

    def test_weekly_only_primary_is_not_five_hour_session(self):
        result = self.fetch({"limit_window_seconds": 604800, "used_percent": 18, "reset_at": 1900000000})
        self.assertTrue(result["ok"])
        self.assertEqual(["week"], [w["id"] for w in result["windows"]])
        self.assertEqual("Неделя", result["windows"][0]["label"])
        self.assertEqual(82, result["windows"][0]["remaining_pct"])

    def test_both_windows_and_minute_aliases(self):
        result = self.fetch({"limit_window_seconds": 18000, "used_percent": 0}, {"window_minutes": 10080, "used_percent": 23})
        self.assertEqual(["session", "week"], [w["id"] for w in result["windows"]])

    def test_null_primary_does_not_create_phantom_session(self):
        result = self.fetch(None, {"limit_window_seconds": 604800, "used_percent": 50})
        self.assertEqual(["week"], [w["id"] for w in result["windows"]])

    def test_unknown_and_unusual_durations_are_not_mislabeled(self):
        for duration in (None, "invalid", 0, float("nan"), 86400):
            with self.subTest(duration=duration):
                w = self.fetch({"limit_window_seconds": duration, "used_percent": 2})["windows"][0]
                self.assertNotEqual("session", w["id"])
                self.assertNotEqual("Сессия (5 ч)", w["label"])
