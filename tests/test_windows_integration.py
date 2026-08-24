import sys
import types
import unittest
from unittest.mock import patch

import windows_integration


class _Key:
    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False


class WindowsIntegrationTests(unittest.TestCase):
    def _winreg(self, value):
        module = types.SimpleNamespace(HKEY_CURRENT_USER=1)
        module.OpenKey = lambda *_args: _Key()
        module.QueryValueEx = lambda *_args: (value, 1)
        return module

    def test_startup_status_detects_stale_command_without_exposing_it(self):
        fake = self._winreg(r"C:\Old\AI-CLI-Control-Center.exe")
        with patch("windows_integration.os.name", "nt"), patch.dict(sys.modules, {"winreg": fake}), patch(
            "windows_integration._startup_command", return_value=r"C:\New\AI-CLI-Control-Center.exe"
        ):
            result = windows_integration.startup_status()
        self.assertFalse(result["enabled"])
        self.assertTrue(result["stale_entry"])
        self.assertNotIn("command", result)

    def test_startup_status_accepts_current_command_case_insensitively(self):
        fake = self._winreg(r"C:\APP\CENTER.EXE")
        with patch("windows_integration.os.name", "nt"), patch.dict(sys.modules, {"winreg": fake}), patch(
            "windows_integration._startup_command", return_value=r"c:\app\center.exe"
        ):
            result = windows_integration.startup_status()
        self.assertTrue(result["enabled"])
        self.assertFalse(result["stale_entry"])


if __name__ == "__main__":
    unittest.main()
