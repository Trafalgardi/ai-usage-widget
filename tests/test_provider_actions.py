import unittest
from unittest.mock import MagicMock, patch

import provider_actions
import widget_v2


class ProviderActionTests(unittest.TestCase):
    def test_login_missing_cli_returns_installable_state(self):
        with patch("provider_actions.discover_cli", return_value={
            "state": "missing",
            "executable_path": None,
        }):
            result = provider_actions.login_provider("claude")
        self.assertFalse(result["success"])
        self.assertEqual("cli_missing", result["status"])

    def test_login_uses_discovered_absolute_path(self):
        process = MagicMock()
        process.pid = 42
        with patch("provider_actions.discover_cli", return_value={
            "state": "installed",
            "executable_path": r"C:\Users\me\.local\bin\claude.exe",
        }), patch("provider_actions.subprocess.Popen", return_value=process) as popen:
            result = provider_actions.login_provider("claude")
        self.assertTrue(result["success"])
        command = popen.call_args.args[0]
        self.assertEqual(r"C:\Users\me\.local\bin\claude.exe", command[0])
        self.assertEqual(["auth", "login"], command[1:])

    def test_install_does_not_run_when_already_installed(self):
        with patch("provider_actions.discover_cli", return_value={
            "state": "installed",
            "executable_path": r"C:\codex.exe",
        }), patch("provider_actions.os.name", "nt"), patch(
            "provider_actions.run_process"
        ) as run:
            result = provider_actions.install_provider("codex")
        self.assertTrue(result["success"])
        self.assertEqual("already_installed", result["status"])
        run.assert_not_called()

    def test_v2_action_returns_fresh_health_for_immediate_ui_update(self):
        api = widget_v2.V2JsApi()
        fresh = {"schema_version": 2, "providers": {"claude": {
            "cli": {"state": "installed"},
        }}}
        with patch("widget_v2.run_install_provider", return_value={
            "success": True,
            "status": "installed",
        }), patch.object(api, "_provider_health", return_value=fresh) as health:
            result = api.execute_provider_action("claude", "install")

        self.assertEqual(fresh, result["provider_health"])
        health.assert_called_once_with(force=True)


if __name__ == "__main__":
    unittest.main()
