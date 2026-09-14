import json
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

from local_usage import LocalUsageCollector, estimate, read_events


class LocalUsageTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.now = datetime.now().astimezone()
        self.stamp = (self.now - timedelta(seconds=1)).isoformat()

    def write(self, rows, name="usage.jsonl"):
        path = self.root / name
        path.write_text("\n".join(json.dumps(r) for r in rows) + "\n", encoding="utf-8")
        return path

    def claude(self, output=10, model="claude-opus-5"):
        return {"timestamp": self.stamp, "type": "assistant", "requestId": "r", "message": {
            "id": "m", "model": model, "content": "secret prompt text",
            "usage": {"input_tokens": 20, "output_tokens": output, "cache_read_input_tokens": 100,
                      "cache_creation_input_tokens": 40, "cache_creation": {"ephemeral_1h_input_tokens": 40}}}}

    def codex(self, total, last, stamp=None):
        return {"timestamp": stamp or self.stamp, "type": "event_msg", "payload": {"type": "token_count", "info": {
            "total_token_usage": {"input_tokens": total, "cached_input_tokens": total // 2, "output_tokens": total // 10},
            "last_token_usage": {"input_tokens": last, "cached_input_tokens": last // 2, "output_tokens": last // 10,
                                 "reasoning_output_tokens": last // 20}}}}

    def test_claude_streaming_and_copied_sessions_are_deduplicated(self):
        path = self.write([self.claude(5), self.claude(10)])
        self.write([self.claude(5)], "copy.jsonl")
        result = LocalUsageCollector({"claude": [self.root]}).collect(now=self.now)
        s = result["providers"]["claude"]["today"]
        self.assertEqual((160, 10, 1), (s["input_tokens"], s["output_tokens"], s["event_count"]))
        self.assertAlmostEqual(.0008, s["estimated_usd"])
        self.assertNotIn("secret", json.dumps(result))
        self.assertNotIn(str(path), json.dumps(result))

    def test_codex_cumulative_repeats_and_inherited_first_total(self):
        rows = [{"type": "turn_context", "payload": {"model": "gpt-6-astra"}},
                self.codex(1000, 100), self.codex(1000, 100), self.codex(1200, 200)]
        events, errors = read_events(self.write(rows), "codex")
        self.assertEqual(0, errors)
        self.assertEqual(300, sum(e["input_tokens"] for e in events.values()))
        self.assertEqual(30, sum(e["output_tokens"] for e in events.values()))

    def test_cache_refresh_truncation_unknown_price_and_opt_out(self):
        collector = LocalUsageCollector({"claude": [self.root]})
        self.write([self.claude()])
        self.assertEqual(10, collector.collect(now=self.now)["providers"]["claude"]["today"]["output_tokens"])
        self.write([self.claude(20, "future-model")])
        result = collector.collect(now=self.now)["providers"]["claude"]["today"]
        self.assertEqual(20, result["output_tokens"])
        self.assertIsNone(result["estimated_usd"])
        self.assertEqual(1, result["unpriced_events"])
        self.assertEqual({"enabled": False}, collector.collect(enabled=False))
        self.assertFalse(collector.cache)

    def test_dates_invalid_lines_and_missing_logs(self):
        old = self.claude()
        old["timestamp"] = (self.now - timedelta(days=8)).isoformat()
        path = self.write([old])
        with path.open("a") as stream:
            stream.write('{"unfinished":')
        result = LocalUsageCollector({"claude": [self.root]}).collect(now=self.now)["providers"]["claude"]
        self.assertEqual("partial", result["state"])
        self.assertEqual(0, result["seven_days"]["event_count"])
        empty = LocalUsageCollector({"codex": [self.root / "missing"]}).collect(now=self.now)
        self.assertEqual("no_data", empty["providers"]["codex"]["state"])

    def test_cost_separates_cached_input_and_output(self):
        events, _ = read_events(self.write([{"type": "turn_context", "payload": {"model": "gpt-6-astra"}}, self.codex(100, 100)]), "codex")
        self.assertAlmostEqual(.00105, estimate(next(iter(events.values()))))

    def test_yesterday_counts_in_seven_days_but_not_today(self):
        yesterday = self.claude()
        yesterday["timestamp"] = (self.now - timedelta(days=1)).isoformat()
        self.write([yesterday])
        result = LocalUsageCollector({"claude": [self.root]}).collect(now=self.now)["providers"]["claude"]
        self.assertEqual(0, result["today"]["event_count"])
        self.assertEqual(1, result["seven_days"]["event_count"])

    def test_mixed_known_unknown_models_marks_partial_cost(self):
        other = self.claude(model="unknown-model")
        other["message"]["id"] = "another-message"
        self.write([self.claude(), other])
        result = LocalUsageCollector({"claude": [self.root]}).collect(now=self.now)["providers"]["claude"]["today"]
        self.assertEqual(1, result["unpriced_events"])
        self.assertAlmostEqual(.0008, result["estimated_usd"])
        self.assertEqual(320, result["input_tokens"])

    def record(self, response, tokens=100):
        return {"type": "token_usage_record", "timestamp": self.stamp, "payload": {
            "response_id": response, "usage": {"input_tokens": tokens,
            "cached_input_tokens": tokens // 2, "output_tokens": tokens // 10}}}

    def test_direct_responses_include_calls_missing_from_ui_counters(self):
        rows = [{"type": "turn_context", "payload": {"model": "gpt-6-astra"}},
                self.record("a"), self.codex(100, 100), self.record("b", 200),
                self.record("b", 200), self.record("c", 100)]
        self.write(rows)
        self.write(rows, "copied-session.jsonl")
        s = LocalUsageCollector({"codex": [self.root]}).collect(now=self.now)["providers"]["codex"]["today"]
        self.assertEqual((400, 40, 3), (s["input_tokens"], s["output_tokens"], s["event_count"]))

    def test_legacy_prefix_survives_upgrade_to_direct_records(self):
        rows = [self.codex(100, 100), self.record("new", 200), self.codex(300, 200)]
        events, skipped = read_events(self.write(rows), "codex")
        self.assertEqual(0, skipped)
        self.assertEqual(300, sum(e["input_tokens"] for e in events.values()))

    def test_model_switches_and_reasoning_do_not_change_output_totals(self):
        rows = [{"type": "turn_context", "payload": {"model": "gpt-6-astra"}}, self.record("a"),
                {"type": "turn_context", "payload": {"model": "gpt-5.6-sol"}}, self.record("b")]
        rows[-1]["payload"]["usage"]["reasoning_output_tokens"] = 8
        events, _ = read_events(self.write(rows), "codex")
        self.assertEqual(["gpt-6-astra", "gpt-5.6-sol"], [e["model"] for e in events.values()])
        self.assertEqual(20, sum(e["output_tokens"] for e in events.values()))

    def test_zeroed_claude_auxiliary_blocks_do_not_mark_usage_partial(self):
        zero = self.claude(0)
        for k in ("input_tokens", "cache_creation_input_tokens", "cache_read_input_tokens"):
            zero["message"]["usage"][k] = 0
        events, skipped = read_events(self.write([zero, self.claude()]), "claude")
        self.assertEqual((1, 0), (len(events), skipped))

    def test_explicit_timezone_and_seven_day_boundary(self):
        zone = timezone(timedelta(hours=7))
        now = datetime(2026, 9, 14, 1, tzinfo=zone)
        rows = []
        for i,stamp in enumerate(("2026-09-13T16:59:59Z", "2026-09-13T17:00:00Z",
                                  "2026-09-07T16:59:59Z", "2026-09-07T17:00:00Z",
                                  "2026-09-14T12:00:00Z")):
            row = self.record(str(i)); row["timestamp"] = stamp; rows.append(row)
        self.write(rows)
        s = LocalUsageCollector({"codex": [self.root]}).collect(now=now)["providers"]["codex"]
        self.assertEqual(1, s["today"]["event_count"])
        self.assertEqual(3, s["seven_days"]["event_count"])

    def test_inconsistent_or_timezone_free_records_are_flagged(self):
        invalid = self.record("bad")
        invalid["payload"]["usage"]["cached_input_tokens"] = 200
        no_zone = self.record("no-zone")
        no_zone["timestamp"] = "2026-09-14T12:00:00"
        events, errors = read_events(self.write([invalid, no_zone]), "codex")
        self.assertEqual((0, 2), (len(events), errors))

    def test_old_invalid_record_does_not_mark_current_period_partial(self):
        invalid = self.claude()
        invalid["timestamp"] = (self.now - timedelta(days=8)).isoformat()
        invalid["message"]["usage"]["output_tokens"] = -1
        valid = self.claude()
        self.write([invalid, valid])
        result = LocalUsageCollector({"claude": [self.root]}).collect(now=self.now)["providers"]["claude"]
        self.assertEqual("available", result["state"])

    def test_cache_write_price_with_mixed_durations(self):
        event = {"model":"claude-opus-5", "input_tokens":1_000_000,
                 "cache_read_tokens":400_000, "cache_write_tokens":300_000,
                 "cache_write_1h_tokens":100_000, "output_tokens":100_000}
        # 300k regular input + 400k read + 200k 5m write + 100k 1h write + 100k output.
        self.assertAlmostEqual(6.45, estimate(event))
