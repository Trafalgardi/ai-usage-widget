# -*- coding: utf-8 -*-
"""Small, reversible Windows integrations. No elevation is required."""

import os
import subprocess
import sys

from version import APP_ID


RUN_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"


def _startup_command():
    if getattr(sys, "frozen", False):
        return subprocess.list2cmdline([os.path.abspath(sys.executable)])
    pythonw = os.path.join(os.path.dirname(sys.executable), "pythonw.exe")
    executable = pythonw if os.path.isfile(pythonw) else sys.executable
    entry = os.path.join(os.path.dirname(os.path.abspath(__file__)), "widget_v2.py")
    return subprocess.list2cmdline([executable, entry])


def startup_status():
    if os.name != "nt":
        return {"supported": False, "enabled": False}
    import winreg
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY) as key:
            value, _ = winreg.QueryValueEx(key, APP_ID)
        current = _startup_command()
        matches_current = bool(value) and os.path.normcase(str(value).strip()).casefold() == os.path.normcase(current.strip()).casefold()
        return {"supported": True, "enabled": matches_current, "stale_entry": bool(value) and not matches_current}
    except FileNotFoundError:
        return {"supported": True, "enabled": False}
    except OSError as exc:
        return {"supported": True, "enabled": False, "error": f"{type(exc).__name__}: {exc}"}


def set_startup(enabled):
    if os.name != "nt":
        return {"success": False, "status": "unsupported_platform"}
    import winreg
    try:
        with winreg.CreateKey(winreg.HKEY_CURRENT_USER, RUN_KEY) as key:
            if enabled:
                winreg.SetValueEx(key, APP_ID, 0, winreg.REG_SZ, _startup_command())
            else:
                try:
                    winreg.DeleteValue(key, APP_ID)
                except FileNotFoundError:
                    pass
        return {"success": True, "status": "startup_enabled" if enabled else "startup_disabled", "enabled": bool(enabled)}
    except OSError as exc:
        return {"success": False, "status": "startup_update_failed", "error": f"{type(exc).__name__}: {exc}"}
