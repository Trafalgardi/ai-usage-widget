import json
import unittest

from diagnostics import build_diagnostics, format_diagnostics


class DiagnosticsTests(unittest.TestCase):
    def test_allow_list_excludes_paths_tokens_usernames_and_raw_errors(self):
        secret = "gho_super_secret"
        home = r"C:\Users\Alice"
        health = {"providers": {"codex": {
            "cli": {
                "state": "installed",
                "version": "codex-cli 1.2.3",
                "install_method": "standalone",
                "executable_path": home + r"\AppData\codex.exe",
                "path_selected": home + r"\AppData\codex.exe",
                "path_conflict": True,
                "detected_copies": [{
                    "path": home + r"\AppData\codex.exe",
                    "source": "PATH",
                    "works": True,
                    "error": secret,
                }, {
                    "path": r"D:\Tools\codex.exe",
                    "source": "known_path",
                    "works": True,
                }],
            },
            "auth": {"state": "valid", "access_token": secret},
        }}}
        providers = {"codex": {"usage": {
            "state": "network_error", "error_kind": "network",
            "error": f"request by Alice bearer {secret}", "last_success_at": 100,
        }}}

        diagnostics = build_diagnostics("2.1.0", health, providers, 200)
        text = format_diagnostics(diagnostics)
        self.assertNotIn(secret, text)
        self.assertNotIn(home, text)
        self.assertNotIn("Alice", text)
        self.assertNotIn("executable_path", text)
        self.assertEqual("multiple_working_copies", diagnostics["providers"]["codex"]["path_conflict_category"])
        self.assertEqual("network", diagnostics["providers"]["codex"]["last_error_code"])
        json.dumps(diagnostics)


if __name__ == "__main__":
    unittest.main()
