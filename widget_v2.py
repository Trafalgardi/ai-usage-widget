# -*- coding: utf-8 -*-
"""Transitional v2 entry point.

Keeps the existing UI/runtime intact while provider-health is extracted from the
legacy widget.py. This file can be removed once widget.py is split into the v2
application modules.
"""

import threading
import time

import widget as legacy_widget
from provider_actions import install_provider as run_install_provider
from provider_actions import login_provider
from provider_state import collect_provider_health


class V2JsApi(legacy_widget.JsApi):
    HEALTH_CACHE_TTL_SEC = 30

    def __init__(self):
        super().__init__()
        self._health_lock = threading.Lock()
        self._health_cache = None
        self._health_cached_at = 0.0

    def _provider_health(self, force=False):
        now = time.time()
        with self._health_lock:
            if (
                not force
                and self._health_cache is not None
                and now - self._health_cached_at < self.HEALTH_CACHE_TTL_SEC
            ):
                return self._health_cache

            self._health_cache = collect_provider_health(now=now)
            self._health_cached_at = now
            return self._health_cache

    def get_data(self):
        snap = super().get_data()
        try:
            snap["provider_health"] = self._provider_health()
        except Exception as exc:
            snap["provider_health"] = {
                "schema_version": 2,
                "providers": {},
                "error": f"{type(exc).__name__}: {exc}",
            }
        return snap

    def get_provider_health(self):
        try:
            return self._provider_health(force=True)
        except Exception as exc:
            return {
                "schema_version": 2,
                "providers": {},
                "error": f"{type(exc).__name__}: {exc}",
            }

    def install_provider(self, provider_id):
        result = run_install_provider(provider_id)
        self._health_cached_at = 0.0
        return result

    def _login_compat(self, provider_id):
        result = login_provider(provider_id)
        self._health_cached_at = 0.0
        if result.get("success"):
            return {
                "success": True,
                "output": "Авторизация запущена",
                "status": result.get("status"),
                "health": result.get("health"),
            }

        status = result.get("status")
        messages = {
            "cli_missing": "CLI не найден",
            "cli_broken": "CLI найден, но не запускается",
            "login_failed_to_start": "Не удалось запустить авторизацию",
        }
        return {
            "success": False,
            "output": messages.get(status, result.get("error") or "Ошибка авторизации"),
            "status": status,
            "health": result.get("health"),
        }

    def login_claude(self):
        return self._login_compat("claude")

    def login_codex(self):
        return self._login_compat("codex")


legacy_widget.JsApi = V2JsApi


if __name__ == "__main__":
    legacy_widget.main()
