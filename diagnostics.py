"""Explicitly allow-listed diagnostics suitable for issue reports."""

import json
import platform
from datetime import datetime, timezone


DIAGNOSTICS_SCHEMA_VERSION = 1


def _timestamp(value):
    if not value:
        return None
    try:
        return datetime.fromtimestamp(float(value), timezone.utc).isoformat().replace("+00:00", "Z")
    except (TypeError, ValueError, OSError):
        return None


def _path_conflict_category(cli):
    copies = cli.get("detected_copies") or []
    working = [item for item in copies if item.get("works")]
    if cli.get("path_conflict"):
        return "multiple_working_copies"
    if len(copies) > 1:
        return "multiple_detected_copies"
    return "none"


def build_diagnostics(app_version, health, providers, now):
    result = {
        "schema_version": DIAGNOSTICS_SCHEMA_VERSION,
        "generated_at": _timestamp(now),
        "app": {"name": "AI CLI Control Center", "version": str(app_version)},
        "os": {
            "system": platform.system(),
            "release": platform.release(),
            "version": platform.version(),
            "architecture": platform.machine(),
        },
        "providers": {},
    }
    health_providers = (health or {}).get("providers") or {}
    for provider_id in ("claude", "codex"):
        item = health_providers.get(provider_id) or {}
        cli = item.get("cli") or {}
        auth = item.get("auth") or {}
        usage = ((providers or {}).get(provider_id) or {}).get("usage") or item.get("usage") or {}
        copies = cli.get("detected_copies") or []
        sources = sorted({str(copy.get("source")) for copy in copies if copy.get("source")})
        error = usage.get("error") if isinstance(usage.get("error"), dict) else {}
        result["providers"][provider_id] = {
            "discovery_status": cli.get("state", "unknown"),
            "cli_version": cli.get("version"),
            "install_method": cli.get("install_method"),
            "discovery_sources": sources,
            "detected_copy_count": len(copies),
            "path_conflict_category": _path_conflict_category(cli),
            "auth_status": auth.get("state", "unknown"),
            "usage_status": usage.get("state", "unknown"),
            "usage_stale": bool(usage.get("stale", False)),
            "last_error_code": error.get("code") or usage.get("error_kind"),
            "last_success_at": _timestamp(usage.get("last_success_at")),
        }
    return result


def format_diagnostics(value):
    return "AI CLI Control Center diagnostics (redacted)\n" + json.dumps(value, indent=2, sort_keys=True)
