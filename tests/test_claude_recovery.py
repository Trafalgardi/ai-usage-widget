import threading
import unittest
import urllib.error
from unittest.mock import patch

import session_repair
import widget


def _http_error(code=401):
    return urllib.error.HTTPError("https://usage.example.test", code, "", {}, None)


class ClaudeRecoveryTests(unittest.TestCase):
    def setUp(self):
        session_repair.reset_automatic_recovery_for_tests()

    def tearDown(self):
        session_repair.reset_automatic_recovery_for_tests()

    def test_expired_session_recovers_once_then_fetches_with_new_credentials(self):
        auth = {"state": "access_expired_refreshable", "access_expires_at": 10,
                "refresh_expires_at": 100, "credential_path": "~/.claude/.credentials.json"}
        credentials = [("old-token", "max", False), ("new-token", "max", False)]
        with patch("widget.inspect_claude_auth", return_value=auth), patch(
            "widget._read_claude_credentials", side_effect=credentials
        ), patch("widget.attempt_automatic_claude_recovery", return_value={
            "success": True, "status": "session_refreshed", "attempted": True,
        }) as repair, patch("widget.http_get_json", return_value={
            "five_hour": {"utilization": 25},
        }) as usage:
            result = widget.fetch_claude()

        self.assertTrue(result["ok"])
        self.assertEqual("session_recovered", result["meta"]["session_recovery"])
        repair.assert_called_once_with(auth, trigger="auth_metadata")
        self.assertEqual("Bearer new-token", usage.call_args.args[1]["Authorization"])

    def test_401_recovers_then_retries_usage_once(self):
        valid = {"state": "valid", "credential_path": "~/.claude/.credentials.json"}
        recoverable = {"state": "access_expired_refreshable", "access_expires_at": 10,
                       "refresh_expires_at": 100, "credential_path": "~/.claude/.credentials.json"}
        with patch("widget.inspect_claude_auth", side_effect=[valid, recoverable]), patch(
            "widget._read_claude_credentials", side_effect=[("old", None, False), ("new", None, False)]
        ), patch("widget.attempt_automatic_claude_recovery", return_value={
            "success": True, "status": "session_refreshed", "attempted": True,
        }) as repair, patch("widget.http_get_json", side_effect=[
            _http_error(401), {"five_hour": {"utilization": 10}},
        ]) as usage:
            result = widget.fetch_claude()

        self.assertTrue(result["ok"])
        self.assertEqual(2, usage.call_count)
        repair.assert_called_once_with(recoverable, trigger="usage_401")
        self.assertEqual("Bearer new", usage.call_args.args[1]["Authorization"])

    def test_failed_401_recovery_does_not_retry_or_loop(self):
        valid = {"state": "valid", "credential_path": "~/.claude/.credentials.json"}
        recoverable = {"state": "access_expired_refreshable", "access_expires_at": 10,
                       "refresh_expires_at": 100, "credential_path": "~/.claude/.credentials.json"}
        with patch("widget.inspect_claude_auth", side_effect=[valid, recoverable]), patch(
            "widget._read_claude_credentials", return_value=("old", None, False)
        ), patch("widget.attempt_automatic_claude_recovery", return_value={
            "success": False, "status": "refresh_failed", "attempted": True,
        }) as repair, patch("widget.http_get_json", side_effect=_http_error(401)) as usage:
            result = widget.fetch_claude()

        self.assertFalse(result["ok"])
        self.assertEqual(1, usage.call_count)
        repair.assert_called_once()
        self.assertEqual("refresh_failed", result["meta"]["session_recovery"])

    def test_login_required_never_starts_automatic_repair(self):
        auth = {"state": "login_required", "credential_path": "~/.claude/.credentials.json"}
        with patch("widget.inspect_claude_auth", return_value=auth), patch(
            "widget._read_claude_credentials", return_value=("old", None, False)
        ), patch("widget.attempt_automatic_claude_recovery") as repair, patch(
            "widget.http_get_json", side_effect=_http_error(401)
        ):
            widget.fetch_claude()
        repair.assert_not_called()

    def test_valid_session_never_starts_automatic_repair(self):
        auth = {"state": "valid", "credential_path": "~/.claude/.credentials.json"}
        with patch("widget.inspect_claude_auth", return_value=auth), patch(
            "widget._read_claude_credentials", return_value=("token", None, False)
        ), patch("widget.attempt_automatic_claude_recovery") as repair, patch(
            "widget.http_get_json", return_value={"five_hour": {"utilization": 10}}
        ):
            widget.fetch_claude()
        repair.assert_not_called()

    def test_concurrent_automatic_repairs_run_the_cli_once(self):
        auth = {"state": "access_expired_refreshable", "access_expires_at": 10,
                "refresh_expires_at": 100, "credential_path": "credential-a"}
        entered = threading.Event()
        release = threading.Event()

        def repair():
            entered.set()
            release.wait(2)
            return {"success": False, "status": "refresh_failed"}

        with patch("session_repair.refresh_claude_session", side_effect=repair) as runner:
            first = threading.Thread(target=session_repair.attempt_automatic_claude_recovery, args=(auth,))
            first.start()
            self.assertTrue(entered.wait(1))
            second = session_repair.attempt_automatic_claude_recovery(auth)
            release.set()
            first.join(2)

        self.assertEqual("recovery_already_running", second["status"])
        self.assertEqual(1, runner.call_count)

    def test_failed_automatic_repair_is_cooled_down_until_credentials_change(self):
        auth = {"state": "access_expired_refreshable", "access_expires_at": 10,
                "refresh_expires_at": 100, "credential_path": "credential-a"}
        with patch("session_repair.refresh_claude_session", return_value={
            "success": False, "status": "refresh_failed",
        }) as runner:
            first = session_repair.attempt_automatic_claude_recovery(auth)
            second = session_repair.attempt_automatic_claude_recovery(auth)
            changed = session_repair.attempt_automatic_claude_recovery({**auth, "access_expires_at": 11})

        self.assertTrue(first["attempted"])
        self.assertEqual("recovery_cooldown", second["status"])
        self.assertTrue(changed["attempted"])
        self.assertEqual(2, runner.call_count)


if __name__ == "__main__":
    unittest.main()
