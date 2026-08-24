import subprocess
import unittest
from unittest.mock import patch

import process_runner


class ProcessRunnerTests(unittest.TestCase):
    def test_timeout_has_normalized_shape(self):
        with patch("process_runner.subprocess.run", side_effect=subprocess.TimeoutExpired(["tool"], 5)):
            result = process_runner.run_process("tool.exe", timeout=5)
        self.assertTrue(result["started"])
        self.assertTrue(result["timed_out"])
        self.assertIsNone(result["exit_code"])

    def test_windows_command_shim_does_not_use_shell_true(self):
        with patch("process_runner.os.name", "nt"):
            command = process_runner.command_for(r"C:\Tools\codex.cmd", ["--version"])
        self.assertEqual(["cmd.exe", "/d", "/s", "/c"], command[:4])


if __name__ == "__main__":
    unittest.main()
