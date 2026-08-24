# -*- coding: utf-8 -*-
"""Provider lifecycle actions for Windows.

Actions are explicit: this module never installs, logs in or repairs anything
unless the caller invokes the corresponding function.
"""

import os
import shutil
import subprocess

from error_model import redact_text
from provider_health import discover_cli
from provider_registry import PROVIDERS
from process_runner import command_for, run_process


_CREATE_NEW_CONSOLE = getattr(subprocess, "CREATE_NEW_CONSOLE", 0)


def _powershell_path():
    return (
        shutil.which("pwsh")
        or shutil.which("powershell")
        or shutil.which("powershell.exe")
    )


def _tail(text, limit=4000):
    return redact_text((text or "").strip(), limit=limit)


def install_provider(provider_id, timeout=300):
    """Install a missing provider using its official Windows installer."""
    if provider_id not in PROVIDERS:
        return {
            "success": False,
            "status": "unsupported_provider",
            "provider_id": provider_id,
        }
    if os.name != "nt":
        return {
            "success": False,
            "status": "unsupported_platform",
            "provider_id": provider_id,
        }

    before = discover_cli(provider_id)
    if before.get("state") == "installed":
        return {
            "success": True,
            "status": "already_installed",
            "provider_id": provider_id,
            "health": before,
        }

    powershell = _powershell_path()
    if not powershell:
        return {
            "success": False,
            "status": "powershell_missing",
            "provider_id": provider_id,
        }

    spec = PROVIDERS[provider_id]
    args = [
        "-NoLogo",
        "-NoProfile",
        "-ExecutionPolicy",
        "Bypass",
        "-Command",
        spec.installer_script,
    ]

    proc = run_process(powershell, args, timeout=timeout)
    if proc["timed_out"]:
        return {
            "success": False,
            "status": "installer_timeout",
            "provider_id": provider_id,
        }
    if not proc["started"]:
        return {
            "success": False,
            "status": "installer_failed_to_start",
            "provider_id": provider_id,
            "error": proc["error"],
        }

    after = discover_cli(provider_id)
    success = proc["exit_code"] == 0 and after.get("state") == "installed"
    return {
        "success": success,
        "status": "installed" if success else "install_failed",
        "provider_id": provider_id,
        "install_method": spec.installer_method,
        "exit_code": proc["exit_code"],
        "stdout": _tail(proc["stdout"]),
        "stderr": _tail(proc["stderr"]),
        "health": after,
    }


def login_provider(provider_id):
    """Start the provider's official interactive login using an absolute path."""
    spec = PROVIDERS.get(provider_id)
    if spec is None:
        return {
            "success": False,
            "status": "unsupported_provider",
            "provider_id": provider_id,
        }

    health = discover_cli(provider_id)
    executable = health.get("executable_path")
    if not executable:
        return {
            "success": False,
            "status": "cli_missing" if health.get("state") == "missing" else "cli_broken",
            "provider_id": provider_id,
            "health": health,
        }

    try:
        proc = subprocess.Popen(
            command_for(executable, spec.login_args),
            creationflags=_CREATE_NEW_CONSOLE if os.name == "nt" else 0,
        )
    except Exception as exc:
        return {
            "success": False,
            "status": "login_failed_to_start",
            "provider_id": provider_id,
            "error": f"{type(exc).__name__}: {redact_text(exc)}",
            "health": health,
        }

    return {
        "success": True,
        "status": "login_started",
        "provider_id": provider_id,
        "pid": proc.pid,
        "health": health,
    }
