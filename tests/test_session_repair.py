import unittest
from unittest.mock import patch

import session_repair


class SessionRepairTests(unittest.TestCase):
    def test_refresh_not_needed_for_valid_session(self):
        with patch("session_repair.inspect_claude_auth", return_value={"state": "valid"}), patch(
            "session_repair.run_process"
        ) as run:
            result = session_repair.refresh_claude_session()
        self.assertTrue(result["success"])
        self.assertEqual("refresh_not_needed", result["status"])
        run.assert_not_called()

    def test_refresh_uses_discovered_absolute_executable(self):
        states = [
            {
                "state": "access_expired_refreshable",
                "access_expires_at": 100,
            },
            {
                "state": "valid",
                "access_expires_at": 200,
            },
        ]
        proc = {
            "started": True,
            "timed_out": False,
            "exit_code": 0,
            "stdout": "OK\n",
            "stderr": "",
            "error": None,
        }
        with patch("session_repair.inspect_claude_auth", side_effect=states), patch(
            "session_repair.discover_cli",
            return_value={
                "state": "installed",
                "executable_path": r"C:\Users\me\.local\bin\claude.exe",
            },
        ), patch("session_repair.run_process", return_value=proc) as run:
            result = session_repair.refresh_claude_session()
        self.assertTrue(result["success"])
        self.assertEqual("session_refreshed", result["status"])
        self.assertEqual(r"C:\Users\me\.local\bin\claude.exe", run.call_args.args[0])
        self.assertEqual(["-p", "Reply exactly OK."], run.call_args.args[1])

    def test_missing_cli_does_not_launch_probe(self):
        with patch(
            "session_repair.inspect_claude_auth",
            return_value={"state": "access_expired_refreshable"},
        ), patch(
            "session_repair.discover_cli",
            return_value={"state": "missing", "executable_path": None},
        ), patch("session_repair.run_process") as run:
            result = session_repair.refresh_claude_session()
        self.assertFalse(result["success"])
        self.assertEqual("cli_missing", result["status"])
        run.assert_not_called()


if __name__ == "__main__":
    unittest.main()
