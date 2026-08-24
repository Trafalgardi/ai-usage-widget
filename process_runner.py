# -*- coding: utf-8 -*-
"""Safe subprocess execution for provider diagnostics.

Non-interactive probes run without a console window and never use shell
interpolation. Windows command shims are routed through cmd.exe with a command
line produced by subprocess.list2cmdline.
"""

import os
import subprocess


_CREATE_NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)


def command_for(executable_path, args):
    command = [executable_path] + list(args)
    suffix = os.path.splitext(executable_path)[1].lower()
    if os.name == "nt" and suffix in (".cmd", ".bat"):
        return ["cmd.exe", "/d", "/s", "/c", subprocess.list2cmdline(command)]
    return command


def run_process(executable_path, args=(), timeout=5):
    """Run a trusted non-interactive command and return a normalized result."""
    try:
        proc = subprocess.run(
            command_for(executable_path, args),
            stdin=subprocess.DEVNULL,
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
            "started": True,
            "timed_out": True,
            "exit_code": None,
            "stdout": "",
            "stderr": "",
            "error": "timeout",
        }
    except Exception as exc:
        return {
            "started": False,
            "timed_out": False,
            "exit_code": None,
            "stdout": "",
            "stderr": "",
            "error": f"{type(exc).__name__}: {exc}",
        }

    return {
        "started": True,
        "timed_out": False,
        "exit_code": proc.returncode,
        "stdout": proc.stdout or "",
        "stderr": proc.stderr or "",
        "error": None,
    }
