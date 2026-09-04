import copy
import unittest
from unittest.mock import MagicMock, patch

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

    def test_application_icon_remains_when_all_provider_usage_is_missing(self):
        tray = widget.TrayManager()
        tray.window_ref = MagicMock()
        application_icon = MagicMock()
        tray.icon_app = application_icon
        with patch("widget.TRAY_AVAILABLE", True):
            tray._update_icon_with_data()
        self.assertIs(application_icon, tray.icon_app)

    def test_icon_is_published_before_it_is_reported_available(self):
        class FakeIcon:
            def __init__(self):
                self.visible = False
                self.stopped = False

            def run(self, setup):
                setup(self)

            def stop(self):
                self.stopped = True

        tray = widget.TrayManager()
        icon = FakeIcon()

        self.assertTrue(tray._run_icon(icon, "icon_app", "_thread_app"))
        self.assertTrue(icon.visible)
        self.assertIs(icon, tray.icon_app)
        self.assertFalse(icon.stopped)

    def test_minimize_hides_only_after_a_tray_icon_is_available(self):
        tray = widget.TrayManager()
        tray.window_ref = MagicMock()
        with patch.object(widget, "TRAY", tray), patch("widget.TRAY_AVAILABLE", True), patch.object(
            tray, "ensure_available", return_value=False
        ):
            self.assertFalse(widget.JsApi().minimize_to_tray())
        tray.window_ref.hide.assert_not_called()

        with patch.object(widget, "TRAY", tray), patch("widget.TRAY_AVAILABLE", True), patch.object(
            tray, "ensure_available", return_value=True
        ):
            self.assertTrue(widget.JsApi().minimize_to_tray())
        tray.window_ref.hide.assert_called_once()

    def test_failed_application_icon_creation_leaves_window_visible(self):
        tray = widget.TrayManager()
        tray.window_ref = MagicMock()
        pystray = MagicMock()
        pystray.Icon.side_effect = RuntimeError("tray unavailable")
        with patch("widget.TRAY_AVAILABLE", True), patch.object(
            widget, "pystray", pystray, create=True
        ), patch.object(widget, "TRAY", tray):
            self.assertFalse(tray.ensure_available())
            self.assertFalse(widget.JsApi().minimize_to_tray())
        tray.window_ref.hide.assert_not_called()

    def test_show_and_exit_from_application_menu_control_window(self):
        tray = widget.TrayManager()
        tray.window_ref = MagicMock()
        tray.icon_app = MagicMock()
        tray._on_show(None, None)
        tray._on_quit(None, None)
        tray.window_ref.show.assert_called_once()
        tray.window_ref.destroy.assert_called_once()
        tray.icon_app.stop.assert_called_once()


if __name__ == "__main__":
    unittest.main()
