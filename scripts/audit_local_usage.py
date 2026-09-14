"""Opt-in, read-only reconciliation against raw local CLI usage metadata.

Creates a temporary metadata-only snapshot so active sessions cannot change
between the two calculations. No prompts, responses, credentials or source
paths are copied or printed. Temporary data is removed at exit.
"""
import argparse
from collections import defaultdict
from datetime import datetime, timedelta
from decimal import Decimal
import hashlib
import json
import os
from pathlib import Path
import sys
import tempfile

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from local_usage import LocalUsageCollector, RATES


def opaque(value):
    return hashlib.sha256(str(value).encode()).hexdigest() if value else None


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--local-logs", action="store_true", required=True)
    parser.parse_args()
    now = datetime.now().astimezone()
    start = now.date() - timedelta(days=6)
    roots = {
        "claude": [Path(os.environ.get("CLAUDE_CONFIG_DIR", Path.home() / ".claude")) / "projects"],
        "codex": [Path(os.environ.get("CODEX_HOME", Path.home() / ".codex")) / part
                  for part in ("sessions", "archived_sessions")],
    }
    reference = {provider: {} for provider in roots}
    statistics = defaultdict(int)
    with tempfile.TemporaryDirectory(prefix="usage-audit-") as directory:
        snapshot_roots = {}
        for provider, folders in roots.items():
            target = Path(directory) / provider
            target.mkdir()
            snapshot_roots[provider] = [target]
            for folder in folders:
                for path in folder.rglob("*.jsonl"):
                    if datetime.fromtimestamp(path.stat().st_mtime).date() < start:
                        continue
                    rows, direct, model = [], [], "unknown"
                    with path.open(encoding="utf-8") as stream:
                        for line in stream:
                            raw = json.loads(line)
                            p = raw.get("payload") or {}
                            record_type = raw.get("type")
                            if provider == "codex":
                                if record_type == "turn_context":
                                    model = p.get("model", "unknown")
                                    rows.append({"type":record_type, "payload":{"model":model}})
                                elif record_type == "token_usage_record":
                                    identity = opaque(p["response_id"])
                                    row = {"timestamp":raw["timestamp"], "type":record_type,
                                           "payload":{"response_id":identity, "usage":p["usage"]}}
                                    rows.append(row)
                                    direct.append((identity, raw["timestamp"], model, p["usage"]))
                                elif record_type == "event_msg" and p.get("type") == "token_count":
                                    rows.append({"timestamp":raw["timestamp"], "type":record_type,
                                                 "payload":{"type":"token_count", "info":p.get("info")}})
                            elif record_type == "assistant" and (raw.get("message") or {}).get("usage"):
                                m = raw["message"]
                                identity = opaque(m.get("id") or raw.get("uuid"))
                                rows.append({"timestamp":raw["timestamp"], "type":record_type,
                                             "requestId":opaque(raw.get("requestId")),
                                             "message":{"id":identity, "model":m.get("model"), "usage":m["usage"]}})
                                direct.append((identity, raw["timestamp"], m.get("model"), m["usage"]))
                    if provider == "codex" and rows and not direct:
                        raise RuntimeError("Live reconciliation needs modern per-response Codex records; legacy parsing is fixture-tested")
                    statistics[provider + "_files"] += 1
                    (target / f"{statistics[provider + '_files']}.jsonl").write_text(
                        "\n".join(json.dumps(row) for row in rows) + "\n", encoding="utf-8")
                    for identity, stamp, model, u in direct:
                        statistics[provider + "_raw_usage_rows"] += 1
                        if provider == "codex":
                            values = [u["input_tokens"], u["output_tokens"], u.get("cached_input_tokens",0),
                                      u.get("cache_write_input_tokens",0), 0]
                        else:
                            base, out = u["input_tokens"], u["output_tokens"]
                            read, write = u.get("cache_read_input_tokens",0), u.get("cache_creation_input_tokens",0)
                            if base + out + read + write == 0:
                                continue
                            values = [base + read + write, out, read, write,
                                      (u.get("cache_creation") or {}).get("ephemeral_1h_input_tokens",0)]
                        date = datetime.fromisoformat(stamp.replace("Z", "+00:00"))
                        old = reference[provider].get(identity)
                        if old:
                            statistics[provider + "_duplicate_rows"] += 1
                            values = [max(a,b) for a,b in zip(values,old[2])]
                            date = min(date,old[0])
                        reference[provider][identity] = (date,model,values)
        actual = LocalUsageCollector(snapshot_roots).collect(now=now)
        fields = ("input_tokens", "output_tokens", "cache_read_tokens", "cache_write_tokens", "cache_write_1h_tokens")
        report = {"captured_at":now.isoformat(), "statistics":dict(statistics), "providers":{}}
        matched = True
        for provider, events in reference.items():
            report["providers"][provider] = {}
            for period in ("today", "seven_days"):
                totals, dollars, priced, unpriced = [0]*5, Decimal(0), 0, 0
                for date,model,values in events.values():
                    day = date.astimezone().date()
                    if not (start <= day <= now.date() and date <= now) or (period == "today" and day != now.date()):
                        continue
                    totals = [a+b for a,b in zip(totals,values)]
                    rate = RATES.get(model) or RATES.get(model.rsplit("-",1)[0])
                    if not rate:
                        unpriced += 1
                        continue
                    priced += 1
                    base,out,read,write,hour = values
                    amounts = (base-read-write,read,write-hour,out)
                    dollars += sum(Decimal(n)*Decimal(str(r)) for n,r in zip(amounts,rate)) / Decimal(1_000_000)
                    dollars += Decimal(hour)*Decimal(str(rate[0]))*2 / Decimal(1_000_000)
                result = actual["providers"][provider][period]
                delta = {key:result[key]-expected for key,expected in zip(fields,totals)}
                price_ok = (abs(Decimal(str(result["estimated_usd"]))-dollars) < Decimal("0.000000001")
                            if priced else result["estimated_usd"] is None)
                ok = not any(delta.values()) and price_ok and result["unpriced_events"] == unpriced
                matched &= ok
                report["providers"][provider][period] = {"matched":ok,"token_deltas":delta,
                    "decimal_cost_matched":price_ok,"input":totals[0],"output":totals[1]}
        report["matched"] = matched
        print(json.dumps(report,indent=2))
        return 0 if matched else 1


if __name__ == "__main__":
    raise SystemExit(main())
