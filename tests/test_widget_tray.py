import copy
import os
import tempfile
import unittest
from unittest.mock import MagicMock, patch

import widget


class TrayManagerTests(unittest.TestCase):
    def setUp(self):
        self.config_patch = patch.object(widget, "CFG", copy.deepcopy(widget.DEFAULT_CONFIG))
        self.config_patch.start()
        self.addCleanup(self.config_patch.stop)
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
        self.assertEqual(63, tray._get_tray_pcts()["claude"])
        self.assertIn("Claude 5h: 63%", tray._build_tooltip())

    def usage_snapshot(self):
        with widget.STATE.lock:
            widget.STATE.snapshot = {
                "updated_at": 1,
                "providers": {pid: {"ok": True, "windows": [
                    {"id": "session", "remaining_pct": 99.9, "resets_at": 86340},
                    {"id": "week", "remaining_pct": 12.5, "resets_at": 604740},
                ]} for pid in ("claude", "codex")},
            }

    def test_both_limits_and_reset_times_fit_windows_tooltip(self):
        self.usage_snapshot()
        tray = widget.TrayManager()
        for language in ("en", "ru"):
            widget.CFG["language"] = language
            with patch("widget.time.time", return_value=0):
                title = tray._build_tooltip()
            self.assertLessEqual(len(title), 127)
            self.assertEqual(2, title.count("99.9%"))
            self.assertEqual(2, title.count("12.5%"))
            self.assertIn("23h59m" if language == "en" else "23ч59м", title)
            self.assertIn("6d23h" if language == "en" else "6д23ч", title)

    def test_independent_choices_survive_restart_and_other_settings_save(self):
        self.usage_snapshot()
        with tempfile.TemporaryDirectory() as directory:
            store = widget.ConfigStore(os.path.join(directory, "config.json"), widget.DEFAULT_CONFIG)
            with patch.object(widget, "SETTINGS_STORE", store), patch("widget.TRAY_AVAILABLE", False):
                tray = widget.TrayManager()
                self.assertTrue(tray._set_limit("claude", "week"))
                self.assertEqual({"claude": 12.5, "codex": 99.9}, tray._get_tray_pcts())
                self.assertTrue(widget.JsApi().save_config_api({"refresh_interval_sec": 90}))
                with patch.object(widget, "CFG", widget.load_config()):
                    restarted = widget.TrayManager()
                    self.assertEqual({"claude": 12.5, "codex": 99.9}, restarted._get_tray_pcts())
                    self.assertTrue(restarted._set_limit("codex", "week"))
                    self.assertEqual({"claude": "week", "codex": "week"}, store.load()["tray_limits"])

    def test_failed_save_does_not_change_selection(self):
        with patch("widget.save_config", return_value=False):
            tray = widget.TrayManager()
            self.assertFalse(tray._set_limit("claude", "week"))
            self.assertEqual("session", tray._selected_limit("claude"))

    def test_missing_week_does_not_fall_back_to_session(self):
        self.usage_snapshot()
        widget.CFG["tray_limits"]["claude"] = "week"
        widget.STATE.snapshot["providers"]["claude"]["windows"].pop()
        tray = widget.TrayManager()
        self.assertIsNone(tray._get_tray_pcts()["claude"])
        self.assertIn("Claude 7d: —", tray._build_tooltip())

    @unittest.skipUnless(widget.TRAY_AVAILABLE, "pystray is optional")
    def test_menu_selection_updates_icons_and_checked_state(self):
        self.usage_snapshot()
        tray = widget.TrayManager()
        tray.icon_app = MagicMock()
        tray.icon_claude = MagicMock()
        tray.icon_codex = MagicMock()
        menu = tray._limit_menu("claude", True)
        session, weekly = menu.items
        self.assertTrue(session.checked)
        self.assertFalse(weekly.checked)
        with patch("widget.save_config", return_value=True), patch.object(
            tray, "_create_icon_image", return_value="image"
        ) as render:
            weekly(tray.icon_claude)
        self.assertTrue(weekly.checked)
        self.assertFalse(session.checked)
        self.assertEqual("12", render.call_args_list[0].args[0])
        self.assertEqual("99", render.call_args_list[1].args[0])
        tray.icon_codex.update_menu.assert_called_once()

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
