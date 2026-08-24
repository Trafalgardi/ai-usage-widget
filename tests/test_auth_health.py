import json
import os
import tempfile
import unittest
from unittest.mock import patch

import auth_health


class AuthHealthTests(unittest.TestCase):
    def _write_claude(self, root, oauth):
        path = os.path.join(root, ".claude", ".credentials.json")
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as stream:
            json.dump({"claudeAiOauth": oauth}, stream)
        return path

    def test_claude_expired_access_with_refresh_is_refreshable(self):
        now = 1_700_000_000
        with tempfile.TemporaryDirectory() as root, patch(
            "auth_health._claude_credential_paths",
            return_value=[self._write_claude(root, {
                "accessToken": "access",
                "refreshToken": "refresh",
                "expiresAt": (now - 60) * 1000,
                "refreshTokenExpiresAt": (now + 86400) * 1000,
                "scopes": ["user:profile", "user:inference"],
                "subscriptionType": "max",
            })],
        ):
            health = auth_health.inspect_claude_auth(now=now)
        self.assertEqual("access_expired_refreshable", health["state"])
        self.assertEqual(["user:profile", "user:inference"], health["scopes"])
        self.assertEqual("max", health["subscription_type"])
        self.assertNotIn("accessToken", health)
        self.assertNotIn("refreshToken", health)
        self.assertEqual("refresh_session", auth_health.recommended_action(
            {"state": "installed"}, health
        )["id"])
        self.assertEqual(
            ["refresh_session", "login"],
            [a["id"] for a in auth_health.recommended_actions(
                {"state": "installed"}, health
            )],
        )

    def test_claude_missing_cli_wins_over_auth(self):
        action = auth_health.recommended_action(
            {"state": "missing"},
            {"state": "login_required"},
        )
        self.assertEqual("install", action["id"])

    def test_claude_missing_expiry_does_not_force_login(self):
        with tempfile.TemporaryDirectory() as root, patch(
            "auth_health._claude_credential_paths",
            return_value=[self._write_claude(root, {
                "accessToken": "access",
                "refreshToken": "refresh",
            })],
        ):
            health = auth_health.inspect_claude_auth(now=1_700_000_000)
        self.assertEqual("session_present_metadata_incomplete", health["state"])
        self.assertEqual("refresh_session", auth_health.recommended_action(
            {"state": "installed"}, health
        )["id"])

    def test_claude_refresh_expired_requires_login(self):
        now = 1_700_000_000
        with tempfile.TemporaryDirectory() as root, patch(
            "auth_health._claude_credential_paths",
            return_value=[self._write_claude(root, {
                "accessToken": "access",
                "refreshToken": "refresh",
                "expiresAt": now - 1,
                "refreshTokenExpiresAt": now - 1,
            })],
        ):
            health = auth_health.inspect_claude_auth(now=now)
        self.assertEqual("login_required", health["state"])
        self.assertEqual("login", auth_health.recommended_action(
            {"state": "installed"}, health
        )["id"])

    def test_corrupted_claude_credentials_are_reported_without_content(self):
        with tempfile.TemporaryDirectory() as root:
            path = os.path.join(root, ".claude", ".credentials.json")
            os.makedirs(os.path.dirname(path), exist_ok=True)
            with open(path, "w", encoding="utf-8") as stream:
                stream.write('{"accessToken":"super-secret"')
            with patch("auth_health._claude_credential_paths", return_value=[path]):
                health = auth_health.inspect_claude_auth(now=1_700_000_000)
        self.assertEqual("credentials_broken", health["state"])
        self.assertNotIn("super-secret", health.get("error", ""))
        self.assertTrue(health["credential_path"].endswith(".credentials.json"))

    def test_codex_malformed_root_and_tokens_do_not_raise(self):
        with tempfile.TemporaryDirectory() as root:
            path = os.path.join(root, "auth.json")
            with patch("auth_health._codex_auth_path", return_value=path):
                with open(path, "w", encoding="utf-8") as stream:
                    json.dump([], stream)
                broken = auth_health.inspect_codex_auth(now=1_700_000_000)
                with open(path, "w", encoding="utf-8") as stream:
                    json.dump({"tokens": ["invalid"]}, stream)
                missing = auth_health.inspect_codex_auth(now=1_700_000_000)
        self.assertEqual("credentials_broken", broken["state"])
        self.assertEqual("login_required", missing["state"])

    def test_network_error_offers_retry_not_login(self):
        actions = auth_health.recommended_actions(
            {"state": "installed"},
            {"state": "valid"},
            {"state": "network_error"},
        )
        self.assertEqual(["retry"], [action["id"] for action in actions])

    def test_rate_limit_does_not_offer_login(self):
        actions = auth_health.recommended_actions(
            {"state": "installed"},
            {"state": "valid"},
            {"state": "rate_limited"},
        )
        self.assertEqual([], actions)


if __name__ == "__main__":
    unittest.main()
