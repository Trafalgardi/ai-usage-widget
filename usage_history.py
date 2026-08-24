"""Bounded, local-only usage history with conservative forecasts and alerts."""

import copy
import json
import os
import threading
from datetime import datetime, timezone


HISTORY_SCHEMA_VERSION = 1
DEFAULT_RETENTION_DAYS = 30
DEFAULT_MAX_SNAPSHOTS = 2000
MIN_ANALYSIS_SPAN_SEC = 300
RESET_TOLERANCE_SEC = 300


def utc_iso(timestamp):
    return datetime.fromtimestamp(float(timestamp), timezone.utc).isoformat().replace("+00:00", "Z")


def parse_utc(value):
    if isinstance(value, (int, float)):
        return float(value)
    if not isinstance(value, str):
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(timezone.utc).timestamp()
    except (ValueError, TypeError):
        return None


def _default_document():
    return {"schema_version": HISTORY_SCHEMA_VERSION, "snapshots": [], "alert_state": {}}


def _migrate_document(value):
    if isinstance(value, list):
        value = {"schema_version": 0, "snapshots": value}
    if not isinstance(value, dict):
        return _default_document()
    version = value.get("schema_version", 0)
    if isinstance(version, int) and version > HISTORY_SCHEMA_VERSION:
        raise ValueError("unsupported future history schema")
    snapshots = value.get("snapshots") if isinstance(value.get("snapshots"), list) else []
    if version == 0:
        migrated = []
        for item in snapshots:
            if not isinstance(item, dict):
                continue
            copied = dict(item)
            captured = copied.pop("timestamp", copied.get("captured_at"))
            parsed = parse_utc(captured)
            if parsed is not None:
                copied["captured_at"] = utc_iso(parsed)
                migrated.append(copied)
        snapshots = migrated
    return {
        "schema_version": HISTORY_SCHEMA_VERSION,
        "snapshots": snapshots,
        "alert_state": value.get("alert_state") if isinstance(value.get("alert_state"), dict) else {},
    }


def analyze_window(samples, now):
    """Return a forecast only after two comparable samples spanning five minutes."""
    valid = []
    for item in samples:
        captured = parse_utc(item.get("captured_at"))
        remaining = item.get("remaining_pct")
        if captured is None or remaining is None or captured > now:
            continue
        valid.append((captured, float(remaining), item.get("resets_at")))
    valid.sort(key=lambda row: row[0])
    if len(valid) < 2:
        return {"state": "unavailable", "reason": "insufficient_samples", "confidence": "unavailable"}

    current = valid[-1]
    reset = current[2]
    if reset is not None:
        valid = [row for row in valid if row[2] is not None and abs(float(row[2]) - float(reset)) <= RESET_TOLERANCE_SEC]
    if len(valid) < 2:
        return {"state": "unavailable", "reason": "reset_boundary", "confidence": "unavailable"}
    first, current = valid[0], valid[-1]
    elapsed = current[0] - first[0]
    if elapsed < MIN_ANALYSIS_SPAN_SEC:
        return {"state": "unavailable", "reason": "observation_window_too_short", "confidence": "unavailable"}

    consumed = max(0.0, first[1] - current[1])
    burn = consumed * 3600.0 / elapsed
    hours_observed = elapsed / 3600.0
    if len(valid) >= 6 and hours_observed >= 2:
        confidence = "high"
    elif len(valid) >= 3 and hours_observed >= 0.5:
        confidence = "medium"
    else:
        confidence = "low"

    result = {
        "state": "available",
        "confidence": confidence,
        "sample_count": len(valid),
        "observed_hours": round(hours_observed, 3),
        "burn_pct_per_hour": round(burn, 3),
        "current_remaining_pct": round(current[1], 2),
        "resets_at": reset,
        "projected_exhaustion_at": None,
        "projected_remaining_at_reset": None,
        "pace_ratio": None,
        "pace_state": "unknown",
    }
    if reset is not None and float(reset) > now:
        hours_left = (float(reset) - now) / 3600.0
        sustainable = current[1] / hours_left if hours_left else None
        result["pace_ratio"] = round(burn / sustainable, 3) if sustainable else None
        result["projected_remaining_at_reset"] = round(max(0.0, current[1] - burn * hours_left), 2)
        if burn > 0:
            exhaustion = now + current[1] / burn * 3600.0
            if exhaustion < float(reset):
                result["projected_exhaustion_at"] = exhaustion
                result["pace_state"] = "at_risk"
            else:
                result["pace_state"] = "sustainable"
        else:
            result["pace_state"] = "stable"
    return result


class HistoryStore:
    """Atomic JSON store containing only normalized percentages and reset times."""

    def __init__(self, path, retention_days=DEFAULT_RETENTION_DAYS, max_snapshots=DEFAULT_MAX_SNAPSHOTS):
        self.path = path
        self.retention_days = max(1, int(retention_days))
        self.max_snapshots = max(10, int(max_snapshots))
        self._lock = threading.Lock()
        self.last_recovery = None

    def _load(self):
        try:
            with open(self.path, "r", encoding="utf-8") as stream:
                return _migrate_document(json.load(stream))
        except FileNotFoundError:
            return _default_document()
        except (OSError, json.JSONDecodeError, ValueError):
            if os.path.exists(self.path):
                suffix = utc_iso(datetime.now(timezone.utc).timestamp()).replace(":", "-")
                recovery = self.path + ".corrupt-" + suffix
                try:
                    os.replace(self.path, recovery)
                    self.last_recovery = os.path.basename(recovery)
                except OSError:
                    self.last_recovery = "recovery_failed"
            return _default_document()

    def _save(self, document):
        directory = os.path.dirname(os.path.abspath(self.path))
        os.makedirs(directory, exist_ok=True)
        temporary = self.path + ".tmp"
        try:
            with open(temporary, "w", encoding="utf-8") as stream:
                json.dump(document, stream, indent=2, ensure_ascii=False, sort_keys=True)
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(temporary, self.path)
        finally:
            try:
                if os.path.exists(temporary):
                    os.remove(temporary)
            except OSError:
                pass

    def clear(self):
        with self._lock:
            self._save(_default_document())
            self.last_recovery = None
        return True

    def process(self, providers, config, now):
        history_cfg = config.get("history") or {}
        if not history_cfg.get("enabled", True):
            return {"enabled": False, "analytics": {}, "alerts": [], "snapshot_count": 0}
        with self._lock:
            document = self._load()
            snapshots = document["snapshots"]
            for provider_id, provider in (providers or {}).items():
                if not provider.get("ok"):
                    continue
                for window in provider.get("windows") or []:
                    remaining = window.get("remaining_pct")
                    if remaining is None:
                        continue
                    snapshots.append({
                        "provider_id": str(provider_id),
                        "window_id": str(window.get("id") or "unknown"),
                        "captured_at": utc_iso(now),
                        "remaining_pct": round(float(remaining), 4),
                        "resets_at": float(window["resets_at"]) if window.get("resets_at") is not None else None,
                    })
            cutoff = now - min(365, max(1, int(history_cfg.get("retention_days", self.retention_days)))) * 86400
            snapshots[:] = [item for item in snapshots if (parse_utc(item.get("captured_at")) or 0) >= cutoff]
            del snapshots[:-self.max_snapshots]

            analytics = {}
            for provider_id, provider in (providers or {}).items():
                provider_result = {}
                for window in provider.get("windows") or []:
                    window_id = str(window.get("id") or "unknown")
                    matching = [item for item in snapshots if item.get("provider_id") == provider_id and item.get("window_id") == window_id]
                    provider_result[window_id] = analyze_window(matching, now)
                analytics[provider_id] = provider_result

            alerts = self._evaluate_alerts(document, providers, analytics, config.get("alerts") or {}, now)
            document["schema_version"] = HISTORY_SCHEMA_VERSION
            self._save(document)
            return {
                "enabled": True,
                "schema_version": HISTORY_SCHEMA_VERSION,
                "analytics": analytics,
                "alerts": alerts,
                "snapshot_count": len(snapshots),
                "recovered_from_corruption": self.last_recovery,
            }

    def _evaluate_alerts(self, document, providers, analytics, alert_cfg, now):
        if not alert_cfg.get("enabled", False):
            return []
        threshold = min(50.0, max(1.0, float(alert_cfg.get("remaining_threshold_pct", 15))))
        cooldown = max(300, int(alert_cfg.get("cooldown_sec", 3600)))
        state = document["alert_state"]
        emitted = []
        for provider_id, provider in (providers or {}).items():
            by_window = analytics.get(provider_id) or {}
            for window in provider.get("windows") or []:
                remaining = window.get("remaining_pct")
                if remaining is None:
                    continue
                resets_at = window.get("resets_at")
                if resets_at is not None and float(resets_at) <= now + 300:
                    continue
                analysis = by_window.get(str(window.get("id") or "unknown")) or {}
                kind = None
                if analysis.get("projected_exhaustion_at") and analysis.get("confidence") in ("medium", "high"):
                    kind = "projected_exhaustion"
                elif float(remaining) <= threshold:
                    kind = "low_remaining"
                if not kind:
                    continue
                reset_bucket = int(float(window.get("resets_at") or 0) // RESET_TOLERANCE_SEC)
                key = f"{provider_id}:{window.get('id')}:{kind}:{reset_bucket}"
                last = float(state.get(key, 0))
                if last > 0 and now - last < cooldown:
                    continue
                state[key] = now
                emitted.append({
                    "provider_id": provider_id,
                    "window_id": str(window.get("id") or "unknown"),
                    "kind": kind,
                    "remaining_pct": round(float(remaining), 2),
                    "resets_at": window.get("resets_at"),
                    "created_at": utc_iso(now),
                })
        stale_keys = [key for key, value in state.items() if now - float(value or 0) > 90 * 86400]
        for key in stale_keys:
            state.pop(key, None)
        return emitted
