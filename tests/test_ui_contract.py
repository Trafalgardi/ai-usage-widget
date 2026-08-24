import json
import unittest

from ui_contract import UI_CONTRACT_VERSION, action_result, serialize_snapshot


class UiContractTests(unittest.TestCase):
    def test_snapshot_has_version_and_safe_defaults(self):
        result = serialize_snapshot({"updated_at": 100})
        self.assertEqual(UI_CONTRACT_VERSION, result["contract_version"])
        self.assertEqual({}, result["providers"])
        self.assertEqual(2, result["provider_health"]["schema_version"])
        json.dumps(result)

    def test_action_result_is_versioned_and_redacted(self):
        result = action_result({"success": False, "status": "login_failed_to_start", "provider_id": "claude", "error": "Bearer secret-token"})
        self.assertEqual(UI_CONTRACT_VERSION, result["contract_version"])
        self.assertNotIn("secret-token", json.dumps(result))
        self.assertEqual("login_failed_to_start", result["status"])


if __name__ == "__main__":
    unittest.main()
