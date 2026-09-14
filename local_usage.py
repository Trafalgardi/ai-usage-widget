"""Read local CLI usage metadata; never persist or expose conversation content.

The in-memory cache is rebuilt from local logs after restart. Prices are a
standard, short-context API equivalent, NOT a subscription bill or quota.
"""

import hashlib
import json
import os
from datetime import datetime, timedelta
from pathlib import Path

PRICING_DATE = "2026-09-14"
PRICING_SOURCES = {
    "codex": "https://developers.openai.com/api/docs/pricing",
    "claude": "https://platform.claude.com/docs/en/about-claude/pricing",
}
# USD / million: uncached input, cache read, cache write (5m), output.
RATES = {
    "gpt-6-astra": (10, 1, 12.5, 50),
    "gpt-5.6-sol": (4, .4, 5, 20),
    "gpt-5.6-terra": (2, .2, 2.5, 12),
    "gpt-5.6-luna": (.2, .02, .25, 1.2),
    "claude-opus-5": (5, .5, 6.25, 25),
    "claude-opus-4-6": (5, .5, 6.25, 25),
    "claude-opus-4-7": (5, .5, 6.25, 25),
    "claude-opus-4-8": (5, .5, 6.25, 25),
    "claude-sonnet-5": (2, .2, 2.5, 10),
    "claude-sonnet-4-6": (3, .3, 3.75, 15),
    "claude-sonnet-4-5": (3, .3, 3.75, 15),
    "claude-haiku-4-5": (1, .1, 1.25, 5),
}
FIELDS = ("input_tokens", "output_tokens", "cache_read_tokens", "cache_write_tokens", "cache_write_1h_tokens")


def count(value):
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ValueError("invalid token count")
    return value


def fingerprint(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True).encode()).hexdigest()


def timestamp(value):
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        raise ValueError("timestamp needs an explicit timezone")
    return parsed.timestamp()


def codex_counts(usage):
    return {
        "input_tokens": count(usage["input_tokens"]),
        "output_tokens": count(usage["output_tokens"]),
        "cache_read_tokens": count(usage.get("cached_input_tokens", 0)),
        "cache_write_tokens": count(usage.get("cache_write_input_tokens", 0)),
        "cache_write_1h_tokens": 0,
    }


def model_rate(model):
    if model in RATES:
        return RATES[model]
    # Only explicit dated Claude snapshots, never guess a new model's price.
    base, _, suffix = model.rpartition("-")
    return RATES.get(base) if len(suffix) == 8 and suffix.isdigit() else None


def estimate(event):
    rate = model_rate(event["model"])
    if rate is None:
        return None
    uncached = event["input_tokens"] - event["cache_read_tokens"] - event["cache_write_tokens"]
    one_hour = event["cache_write_1h_tokens"]
    return (uncached * rate[0] + event["cache_read_tokens"] * rate[1]
            + (event["cache_write_tokens"] - one_hour) * rate[2]
            + one_hour * rate[0] * 2 + event["output_tokens"] * rate[3]) / 1_000_000


def read_events(path, provider, since=None):
    events = {}
    model, previous = "unknown", None
    skipped = 0
    direct_records = False
    with path.open(encoding="utf-8") as stream:
        for line in stream:
            event_time = None
            try:
                row = json.loads(line)
                if not isinstance(row, dict):
                    continue
                if provider == "claude":
                    if row.get("type") != "assistant":
                        continue
                    message = row.get("message") or {}
                    usage = message.get("usage")
                    if not isinstance(usage, dict):
                        continue
                    event_time = timestamp(row["timestamp"])
                    # Claude repeats zeroed usage on auxiliary streaming blocks,
                    # sometimes retaining the original cache duration breakdown.
                    if all(usage.get(k) == 0 for k in ("input_tokens", "output_tokens",
                                                      "cache_read_input_tokens", "cache_creation_input_tokens")):
                        continue
                    model = message.get("model") or "unknown"
                    read = count(usage.get("cache_read_input_tokens", 0))
                    write = count(usage.get("cache_creation_input_tokens", 0))
                    values = {
                        "input_tokens": count(usage["input_tokens"]) + read + write,
                        "output_tokens": count(usage["output_tokens"]),
                        "cache_read_tokens": read, "cache_write_tokens": write,
                        "cache_write_1h_tokens": count((usage.get("cache_creation") or {}).get("ephemeral_1h_input_tokens", 0)),
                    }
                    # Streaming blocks and copied sessions repeat the message ID.
                    key = fingerprint([row.get("requestId"), message.get("id") or row.get("uuid")])
                    if not message.get("id") and not row.get("uuid"):
                        raise ValueError("missing event identity")
                else:
                    payload = row.get("payload") or {}
                    if row.get("type") == "turn_context":
                        model = payload.get("model") or "unknown"
                        continue
                    if row.get("type") == "token_usage_record":
                        # Modern Codex records every completed response, including
                        # calls without a UI token_count event (e.g. compaction).
                        # These records precede their mirrored token_count event.
                        # Preserve an older legacy-only prefix after CLI upgrades.
                        direct_records = True
                        event_time = timestamp(row["timestamp"])
                        if not payload.get("response_id"):
                            raise ValueError("missing response identity")
                        values = codex_counts(payload["usage"])
                        key = fingerprint(["response", payload["response_id"]])
                    elif direct_records:
                        continue
                    else:
                        if row.get("type") != "event_msg" or payload.get("type") != "token_count":
                            continue
                        event_time = timestamp(row["timestamp"])
                        info = payload.get("info") or {}
                        total = info.get("total_token_usage")
                        if not isinstance(total, dict):
                            continue
                        total = {k: count(total.get(k, 0)) for k in (
                            "input_tokens", "cached_input_tokens", "cache_write_input_tokens", "output_tokens")}
                        if previous == total:
                            continue
                        if previous is not None and all(total[k] >= previous[k] for k in total):
                            usage = {k: total[k] - previous[k] for k in total}
                        else:
                            # First record may contain an inherited session total.
                            usage = info.get("last_token_usage")
                        previous = total
                        if not isinstance(usage, dict):
                            raise ValueError("missing per-response usage")
                        values = codex_counts(usage)
                        key = fingerprint([row.get("timestamp"), total])
                if values["cache_read_tokens"] + values["cache_write_tokens"] > values["input_tokens"]:
                    raise ValueError("inconsistent input counts")
                if values["cache_write_1h_tokens"] > values["cache_write_tokens"]:
                    raise ValueError("inconsistent cache counts")
                event = dict(values, model=str(model), timestamp=event_time)
                existing = events.get(key)
                if existing:
                    # Keep the fullest streaming update, not the sum of blocks.
                    for field in FIELDS:
                        event[field] = max(existing[field], event[field])
                    event["timestamp"] = min(existing["timestamp"], event["timestamp"])
                events[key] = event
            except (ValueError, TypeError, KeyError, AttributeError, OverflowError):
                if since is None or event_time is None or event_time >= since:
                    skipped += 1
    return events, skipped


def summarize(events):
    result = {field: 0 for field in FIELDS}
    result.update(event_count=0, estimated_usd=0.0, unpriced_events=0, models=[])
    models = set()
    for event in events:
        result["event_count"] += 1
        models.add(event["model"])
        for field in FIELDS:
            result[field] += event[field]
        cost = estimate(event)
        if cost is None:
            result["unpriced_events"] += 1
        else:
            result["estimated_usd"] += cost
    result["models"] = sorted(models)
    if result["unpriced_events"] == result["event_count"]:
        result["estimated_usd"] = None
    return result


class LocalUsageCollector:
    def __init__(self, roots=None):
        self.roots = roots
        self.cache = {}

    def collect(self, enabled=True, now=None):
        if not enabled:
            self.cache.clear()
            return {"enabled": False}
        # None uses the OS timezone for each timestamp, including DST history.
        local_zone = now.tzinfo if now is not None else None
        now = datetime.now().astimezone() if now is None else now
        today = now.date()
        first_day = today - timedelta(days=6)
        since = datetime.combine(first_day, datetime.min.time(), tzinfo=local_zone).timestamp()
        roots = self.roots or {
            "claude": [Path(os.environ.get("CLAUDE_CONFIG_DIR", Path.home() / ".claude")) / "projects"],
            "codex": [Path(os.environ.get("CODEX_HOME", Path.home() / ".codex")) / name
                      for name in ("sessions", "archived_sessions")],
        }
        result = {"enabled": True, "pricing_date": PRICING_DATE, "providers": {}}
        live_paths = set()
        for provider, folders in roots.items():
            merged, errors, file_count = {}, 0, 0
            for folder in folders:
                try:
                    paths = Path(folder).rglob("*.jsonl")
                    for path in paths:
                        try:
                            stat = path.stat()
                            if datetime.fromtimestamp(stat.st_mtime, local_zone).date() < first_day:
                                continue
                            live_paths.add(path)
                            signature = (stat.st_mtime_ns, stat.st_size, since)
                            cached = self.cache.get(path)
                            if cached is None or cached[0] != signature:
                                events, skipped = read_events(path, provider, since=since)
                                cached = (signature, events, skipped)
                                self.cache[path] = cached
                            file_count += 1
                            errors += cached[2]
                            for key, event in cached[1].items():
                                existing = merged.get(key)
                                if existing is None or sum(event[f] for f in FIELDS) > sum(existing[f] for f in FIELDS):
                                    merged[key] = event
                        except (OSError, UnicodeError):
                            errors += 1
                except OSError:
                    errors += 1
            recent = [e for e in merged.values() if first_day <= datetime.fromtimestamp(e["timestamp"], local_zone).date() <= today
                      and e["timestamp"] <= now.timestamp()]
            current = [e for e in recent if datetime.fromtimestamp(e["timestamp"], local_zone).date() == today]
            result["providers"][provider] = {
                "state": "partial" if errors else ("available" if recent else "no_data"),
                "skipped_records_or_files": errors, "files_read": file_count,
                "today": summarize(current), "seven_days": summarize(recent),
            }
        self.cache = {p: item for p, item in self.cache.items() if p in live_paths}
        return result
