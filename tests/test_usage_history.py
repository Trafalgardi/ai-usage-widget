import json
import os
import tempfile
import unittest

from usage_history import HistoryStore, analyze_window, utc_iso


def provider(remaining, reset=20000):
    return {"claude": {"ok": True, "windows": [{
        "id": "session", "remaining_pct": remaining, "resets_at": reset,
        "raw_response": "must never be stored", "account_id": "private",
    }]}}


class HistoryCalculationTests(unittest.TestCase):
    def test_sparse_single_sample_is_unavailable(self):
        result = analyze_window([{"captured_at": utc_iso(1000), "remaining_pct": 90, "resets_at": 5000}], 1000)
        self.assertEqual("unavailable", result["state"])
        self.assertEqual("insufficient_samples", result["reason"])

    def test_burn_rate_and_exhaustion_are_calculated_from_comparable_samples(self):
        samples = [
            {"captured_at": utc_iso(1000), "remaining_pct": 80, "resets_at": 5000},
            {"captured_at": utc_iso(1600), "remaining_pct": 60, "resets_at": 5000},
        ]
        result = analyze_window(samples, 1600)
        self.assertEqual("available", result["state"])
        self.assertAlmostEqual(120, result["burn_pct_per_hour"])
        self.assertEqual("at_risk", result["pace_state"])
        self.assertLess(result["projected_exhaustion_at"], 5000)

    def test_reset_boundary_does_not_mix_cycles(self):
        samples = [
            {"captured_at": utc_iso(1000), "remaining_pct": 5, "resets_at": 1100},
            {"captured_at": utc_iso(1600), "remaining_pct": 99, "resets_at": 5000},
        ]
        result = analyze_window(samples, 1600)
        self.assertEqual("reset_boundary", result["reason"])


class HistoryStoreTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.path = os.path.join(self.temp.name, "history.json")
        self.config = {
            "history": {"enabled": True, "retention_days": 30},
            "alerts": {"enabled": False},
        }

    def tearDown(self):
        self.temp.cleanup()

    def test_atomic_write_contains_only_allow_list(self):
        store = HistoryStore(self.path)
        store.process(provider(80), self.config, 1000)
        self.assertFalse(os.path.exists(self.path + ".tmp"))
        with open(self.path, encoding="utf-8") as stream:
            text = stream.read()
        self.assertNotIn("raw_response", text)
        self.assertNotIn("account_id", text)
        value = json.loads(text)
        self.assertEqual(1, value["schema_version"])

    def test_corruption_is_recovered_without_crashing(self):
        with open(self.path, "w", encoding="utf-8") as stream:
            stream.write("{broken")
        store = HistoryStore(self.path)
        result = store.process(provider(70), self.config, 1000)
        self.assertTrue(result["recovered_from_corruption"].startswith("history.json.corrupt-"))
        self.assertEqual(1, result["snapshot_count"])

    def test_future_schema_is_preserved_as_recovery_file(self):
        with open(self.path, "w", encoding="utf-8") as stream:
            json.dump({"schema_version": 999, "snapshots": [{"secret": "unknown"}]}, stream)
        store = HistoryStore(self.path)
        result = store.process(provider(70), self.config, 1000)
        self.assertTrue(result["recovered_from_corruption"].startswith("history.json.corrupt-"))
        self.assertEqual(1, result["snapshot_count"])

    def test_v0_timestamp_migrates_to_utc(self):
        with open(self.path, "w", encoding="utf-8") as stream:
            json.dump({"schema_version": 0, "snapshots": [{
                "provider_id": "claude", "window_id": "session", "timestamp": 500,
                "remaining_pct": 90, "resets_at": 20000,
            }]}, stream)
        result = HistoryStore(self.path).process(provider(80), self.config, 1000)
        self.assertEqual(2, result["snapshot_count"])
        with open(self.path, encoding="utf-8") as stream:
            value = json.load(stream)
        self.assertTrue(value["snapshots"][0]["captured_at"].endswith("Z"))

    def test_retention_and_size_bounds(self):
        store = HistoryStore(self.path, retention_days=1, max_snapshots=10)
        for index in range(15):
            store.process(provider(100 - index), self.config, 200000 + index * 600)
        with open(self.path, encoding="utf-8") as stream:
            value = json.load(stream)
        self.assertLessEqual(len(value["snapshots"]), 10)

    def test_opt_out_does_not_create_file_and_clear_is_explicit(self):
        store = HistoryStore(self.path)
        disabled = {"history": {"enabled": False}, "alerts": {"enabled": False}}
        self.assertFalse(store.process(provider(50), disabled, 1000)["enabled"])
        self.assertFalse(os.path.exists(self.path))
        store.process(provider(50), self.config, 1000)
        store.clear()
        with open(self.path, encoding="utf-8") as stream:
            self.assertEqual([], json.load(stream)["snapshots"])

    def test_alert_is_opt_in_and_cooldown_is_persistent(self):
        config = {
            "history": {"enabled": True},
            "alerts": {"enabled": True, "remaining_threshold_pct": 15, "cooldown_sec": 3600},
        }
        store = HistoryStore(self.path)
        first = store.process(provider(10), config, 1000)
        second = store.process(provider(9), config, 1600)
        third = HistoryStore(self.path).process(provider(8), config, 2000)
        self.assertEqual(1, len(first["alerts"]))
        self.assertEqual([], second["alerts"])
        self.assertEqual([], third["alerts"])

    def test_low_alert_is_suppressed_when_reset_is_imminent(self):
        config = {
            "history": {"enabled": True},
            "alerts": {"enabled": True, "remaining_threshold_pct": 15},
        }
        result = HistoryStore(self.path).process(provider(5, reset=1200), config, 1000)
        self.assertEqual([], result["alerts"])


if __name__ == "__main__":
    unittest.main()
