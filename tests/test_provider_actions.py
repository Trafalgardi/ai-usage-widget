import unittest
from unittest.mock import MagicMock, patch

import provider_actions


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
            "provider_actions.subprocess.run"
        ) as run:
            result = provider_actions.install_provider("codex")
        self.assertTrue(result["success"])
        self.assertEqual("already_installed", result["status"])
        run.assert_not_called()


if __name__ == "__main__":
    unittest.main()
