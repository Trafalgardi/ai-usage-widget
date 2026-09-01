# -*- coding: utf-8 -*-
"""Provider authentication recovery helpers.

Claude Code currently has no supported `auth refresh` command. For an expired
access token with a still-present refresh token, a real CLI inference is the
supported path that exercises Claude Code's own refresh logic. This action is
explicit because it consumes a very small amount of quota.
"""

import threading
import time

from auth_health import inspect_claude_auth
from provider_health import discover_cli
from process_runner import run_process


_REPAIR_LOCK = threading.Lock()
_AUTOMATIC_RECOVERY_LOCK = threading.Lock()
_AUTOMATIC_RECOVERY_COOLDOWN_SEC = 15 * 60
_last_failed_automatic_recovery = {"signature": None, "at": 0.0}

RECOVERABLE_CLAUDE_AUTH_STATES = (
    "access_expired_refreshable",
    "access_missing_refreshable",
)


def _credential_signature(auth):
    """Return non-secret metadata identifying one recoverable auth episode."""
    auth = auth or {}
    return (
        auth.get("credential_path"),
        auth.get("state"),
        auth.get("access_expires_at"),
        auth.get("refresh_expires_at"),
    )


def attempt_automatic_claude_recovery(auth, trigger="auth_metadata", now=None):
    """Run at most one CLI repair per unchanged failed credential episode.

    The application never exchanges a refresh token itself.  This guard sits
    above :func:`refresh_claude_session` so a periodic usage refresh cannot
    repeatedly spend quota after a failed CLI recovery.  Explicit UI repair
    remains available through ``refresh_claude_session`` and intentionally is
    not subject to this automatic-retry cooldown.
    """
    auth = auth or {}
    if auth.get("state") not in RECOVERABLE_CLAUDE_AUTH_STATES:
        return {
            "success": False,
            "status": "recovery_not_applicable",
            "provider_id": "claude",
            "attempted": False,
            "auth": auth,
        }
    if not _AUTOMATIC_RECOVERY_LOCK.acquire(blocking=False):
        return {
            "success": False,
            "status": "recovery_already_running",
            "provider_id": "claude",
            "attempted": False,
            "auth": auth,
        }

    try:
        timestamp = time.time() if now is None else float(now)
        signature = _credential_signature(auth)
        if (
            _last_failed_automatic_recovery["signature"] == signature
            and timestamp - _last_failed_automatic_recovery["at"] < _AUTOMATIC_RECOVERY_COOLDOWN_SEC
        ):
            return {
                "success": False,
                "status": "recovery_cooldown",
                "provider_id": "claude",
                "attempted": False,
                "auth": auth,
            }

        result = dict(refresh_claude_session())
        result["attempted"] = True
        result["trigger"] = trigger
        if result.get("success"):
            _last_failed_automatic_recovery["signature"] = None
            _last_failed_automatic_recovery["at"] = 0.0
        else:
            _last_failed_automatic_recovery["signature"] = signature
            _last_failed_automatic_recovery["at"] = timestamp
        return result
    finally:
        _AUTOMATIC_RECOVERY_LOCK.release()


def reset_automatic_recovery_for_tests():
    """Reset process-local automatic recovery state for deterministic tests."""
    _last_failed_automatic_recovery["signature"] = None
    _last_failed_automatic_recovery["at"] = 0.0


def refresh_claude_session(timeout=45):
    """Ask Claude Code itself to refresh an expired OAuth access session.

    This never exchanges refresh tokens directly. It runs one minimal real
    inference through the discovered Claude executable, then re-reads credential
    metadata to verify that Claude Code rotated/recovered the session.
    """
    if not _REPAIR_LOCK.acquire(blocking=False):
        return {
            "success": False,
            "status": "refresh_already_running",
            "provider_id": "claude",
        }

    try:
        before = inspect_claude_auth()
        if before.get("state") not in RECOVERABLE_CLAUDE_AUTH_STATES + (
            "session_present_metadata_incomplete",
        ):
            return {
                "success": before.get("state") in ("valid", "expiring"),
                "status": "refresh_not_needed",
                "provider_id": "claude",
                "auth": before,
            }

        cli = discover_cli("claude")
        executable = cli.get("executable_path")
        if not executable:
            return {
                "success": False,
                "status": "cli_missing" if cli.get("state") == "missing" else "cli_broken",
                "provider_id": "claude",
                "cli": cli,
                "auth": before,
            }

        proc = run_process(executable, ["-p", "Reply exactly OK."], timeout=timeout)
        if proc["timed_out"]:
            return {
                "success": False,
                "status": "refresh_probe_timeout",
                "provider_id": "claude",
                "auth": before,
            }
        if not proc["started"]:
            return {
                "success": False,
                "status": "refresh_probe_failed_to_start",
                "provider_id": "claude",
                "error": proc["error"],
                "auth": before,
            }

        after = inspect_claude_auth()
        recovered = after.get("state") in ("valid", "expiring")
        if not recovered:
            before_exp = before.get("access_expires_at") or 0
            after_exp = after.get("access_expires_at") or 0
            recovered = after_exp > before_exp

        return {
            "success": bool(recovered and proc["exit_code"] == 0),
            "status": "session_refreshed" if recovered else "refresh_failed",
            "provider_id": "claude",
            "exit_code": proc["exit_code"],
            "auth": after,
            "cli": cli,
        }
    finally:
        _REPAIR_LOCK.release()
