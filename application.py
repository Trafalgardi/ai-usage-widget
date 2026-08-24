"""Composition root for the Windows AI CLI Control Center."""

import os
import time

import widget as legacy_widget
from ui_bridge import ControlCenterApi


def smoke_check():
    required = [
        os.path.join(legacy_widget.APP_DIR, "ui.html"),
        os.path.join(legacy_widget.APP_DIR, "icon", "512.png"),
        os.path.join(legacy_widget.APP_DIR, "icon", "app.ico"),
    ]
    missing = [path for path in required if not os.path.isfile(path)]
    if missing:
        raise RuntimeError("Missing packaged resources: " + ", ".join(os.path.basename(path) for path in missing))
    return required


class UiSmokeApi:
    """Credential-free bridge used only by the packaged UI smoke check."""

    def get_data(self):
        return {
            "contract_version": 1,
            "updated_at": time.time(),
            "now": time.time(),
            "refresh_interval_sec": 60,
            "providers": {
                "claude": {"id": "claude", "name": "Claude Code", "ok": True, "windows": [], "meta": {}},
                "codex": {"id": "codex", "name": "Codex CLI", "ok": True, "windows": [], "meta": {}},
            },
            "provider_health": {"schema_version": 2, "providers": {}},
            "insights": {"enabled": True, "analytics": {}, "alerts": [], "snapshot_count": 0},
            "token_status": {"claude": None, "codex": None},
            "_config": {"language": "en", "refresh_interval_sec": 60, "window": {"width": 380, "height": 600, "on_top": False}},
            "on_top": False,
        }


def main():
    if os.environ.get("AI_CLI_CONTROL_CENTER_SMOKE_TEST") == "1":
        smoke_check()
        return
    if os.environ.get("AI_CLI_CONTROL_CENTER_UI_SMOKE_TEST") == "1":
        smoke_check()
        legacy_widget.JsApi = UiSmokeApi
    else:
        legacy_widget.JsApi = ControlCenterApi
    legacy_widget.main()
