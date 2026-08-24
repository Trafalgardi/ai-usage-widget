# -*- coding: utf-8 -*-
"""Provider authentication recovery helpers.

Claude Code currently has no supported `auth refresh` command. For an expired
access token with a still-present refresh token, a real CLI inference is the
supported path that exercises Claude Code's own refresh logic. This action is
explicit because it consumes a very small amount of quota.
"""

import os
import subprocess
import threading

from auth_health import inspect_claude_auth
from provider_health import discover_cli


_CREATE_NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)
_REPAIR_LOCK = threading.Lock()


def _command(executable_path, args):
    command = [executable_path] + list(args)
    suffix = os.path.splitext(executable_path)[1].lower()
    if os.name == "nt" and suffix in (".cmd", ".bat"):
        return ["cmd.exe", "/d", "/s", "/c", subprocess.list2cmdline(command)]
    return command


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
        if before.get("state") not in (
            "access_expired_refreshable",
            "access_missing_refreshable",
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

        try:
            proc = subprocess.run(
                _command(executable, ["-p", "Reply exactly OK."]),
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=timeout,
                creationflags=_CREATE_NO_WINDOW if os.name == "nt" else 0,
            )
        except subprocess.TimeoutExpired:
            return {
                "success": False,
                "status": "refresh_probe_timeout",
                "provider_id": "claude",
                "auth": before,
            }
        except Exception as exc:
            return {
                "success": False,
                "status": "refresh_probe_failed_to_start",
                "provider_id": "claude",
                "error": f"{type(exc).__name__}: {exc}",
                "auth": before,
            }

        after = inspect_claude_auth()
        recovered = after.get("state") in ("valid", "expiring")
        if not recovered:
            before_exp = before.get("access_expires_at") or 0
            after_exp = after.get("access_expires_at") or 0
            recovered = after_exp > before_exp

        return {
            "success": bool(recovered and proc.returncode == 0),
            "status": "session_refreshed" if recovered else "refresh_failed",
            "provider_id": "claude",
            "exit_code": proc.returncode,
            "auth": after,
            "cli": cli,
        }
    finally:
        _REPAIR_LOCK.release()
