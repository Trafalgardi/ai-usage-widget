import unittest
from unittest.mock import patch

import provider_health


class ProviderHealthTests(unittest.TestCase):
    def _spec(self, known=None):
        return {
            "command": "claude",
            "version_args": ["--version"],
            "known": known or [],
        }

    @patch("provider_health.os.path.isfile", return_value=False)
    @patch("provider_health.shutil.which", return_value=None)
    def test_missing_when_no_executable_exists(self, _which, _isfile):
        with patch("provider_health._provider_spec", return_value=self._spec()):
            health = provider_health.discover_cli("claude")
        self.assertEqual("missing", health["state"])
        self.assertIsNone(health["executable_path"])
        self.assertFalse(health["path_conflict"])

    @patch("provider_health.os.path.isfile", return_value=True)
    @patch("provider_health.shutil.which", return_value=r"C:\path\claude.exe")
    def test_path_executable_is_selected(self, _which, _isfile):
        spec = self._spec([
            (r"C:\other\claude.exe", "native", "known_path"),
        ])
        with patch("provider_health._provider_spec", return_value=spec), patch(
            "provider_health._run_version",
            return_value={"works": True, "version": "2.1.226", "error": None},
        ):
            health = provider_health.discover_cli("claude")
        self.assertEqual("installed", health["state"])
        self.assertTrue(health["executable_path"].endswith(r"path\claude.exe"))
        self.assertTrue(health["path_conflict"])
        self.assertEqual(2, len(health["detected_copies"]))

    @patch("provider_health.os.path.isfile", return_value=True)
    @patch("provider_health.shutil.which", return_value=None)
    def test_known_path_recovers_from_stale_path(self, _which, _isfile):
        spec = self._spec([
            (r"C:\Users\me\.local\bin\claude.exe", "native", "known_path"),
        ])
        with patch("provider_health._provider_spec", return_value=spec), patch(
            "provider_health._run_version",
            return_value={"works": True, "version": "2.1.226", "error": None},
        ):
            health = provider_health.discover_cli("claude")
        self.assertEqual("installed", health["state"])
        self.assertEqual("native", health["install_method"])
        self.assertIsNone(health["path_selected"])

    @patch("provider_health.os.path.isfile", return_value=True)
    @patch("provider_health.shutil.which", return_value=None)
    def test_broken_when_binary_exists_but_probe_fails(self, _which, _isfile):
        spec = self._spec([
            (r"C:\Users\me\.local\bin\claude.exe", "native", "known_path"),
        ])
        with patch("provider_health._provider_spec", return_value=spec), patch(
            "provider_health._run_version",
            return_value={"works": False, "version": None, "error": "exit code 1"},
        ):
            health = provider_health.discover_cli("claude")
        self.assertEqual("broken", health["state"])
        self.assertIsNone(health["executable_path"])


if __name__ == "__main__":
    unittest.main()
