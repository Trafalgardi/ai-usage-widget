# -*- coding: utf-8 -*-
"""Read-only update discovery. Installation remains an explicit release action."""

import json
import re
import urllib.error
import urllib.request

from error_model import redact_text
from version import __version__


LATEST_RELEASE_API = "https://api.github.com/repos/Trafalgardi/ai-usage-widget/releases/latest"


def _version_tuple(value):
    match = re.fullmatch(r"v?(\d+)\.(\d+)\.(\d+)(?:[-+].*)?", str(value or "").strip())
    return tuple(map(int, match.groups())) if match else None


def check_for_updates(timeout=8, opener=None):
    opener = opener or urllib.request.urlopen
    request = urllib.request.Request(LATEST_RELEASE_API, headers={
        "Accept": "application/vnd.github+json",
        "User-Agent": "ai-cli-control-center",
    })
    try:
        with opener(request, timeout=timeout) as response:
            payload = json.loads(response.read().decode("utf-8", "replace"))
        latest = payload.get("tag_name")
        current_tuple = _version_tuple(__version__)
        latest_tuple = _version_tuple(latest)
        if latest_tuple is None:
            return {"success": False, "status": "malformed_release", "current_version": __version__}
        return {
            "success": True,
            "status": "update_available" if current_tuple and latest_tuple > current_tuple else "up_to_date",
            "current_version": __version__,
            "latest_version": latest,
            "release_url": payload.get("html_url"),
        }
    except (urllib.error.URLError, TimeoutError) as exc:
        return {"success": False, "status": "network_error", "current_version": __version__, "error": redact_text(exc)}
    except (json.JSONDecodeError, UnicodeError, AttributeError) as exc:
        return {"success": False, "status": "malformed_release", "current_version": __version__, "error": redact_text(exc)}
