import copy
import unittest
from unittest.mock import patch

import widget


class TrayManagerTests(unittest.TestCase):
    def setUp(self):
        with widget.STATE.lock:
            self.original = copy.deepcopy(widget.STATE.snapshot)

    def tearDown(self):
        with widget.STATE.lock:
            widget.STATE.snapshot = self.original

    def test_tooltip_and_icon_data_keep_stale_last_good_usage(self):
        with widget.STATE.lock:
            widget.STATE.snapshot = {
                "updated_at": 100,
                "providers": {
                    "claude": {
                        "ok": False,
                        "usage": {"stale": True},
                        "windows": [{
                            "id": "session",
                            "remaining_pct": 63,
                            "resets_at": None,
                        }],
                    },
                },
            }

        tray = widget.TrayManager()
        self.assertEqual(63, tray._get_session_pcts()["claude"])
        self.assertIn("Claude: 63%", tray._build_tooltip())

    def test_icon_update_is_safe_when_tray_dependencies_are_missing(self):
        with patch("widget.TRAY_AVAILABLE", False):
            widget.TrayManager()._update_icon_with_data()


if __name__ == "__main__":
    unittest.main()
