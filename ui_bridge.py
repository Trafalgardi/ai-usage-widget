# -*- coding: utf-8 -*-
"""The versioned bridge exposed to the local WebView UI."""

import copy
import threading
import time

import widget as legacy_widget
from auth_health import recommended_actions
from error_model import ErrorKind, exception_error
from provider_actions import install_provider, login_provider
from provider_registry import ActionId, PROVIDERS
from provider_state import collect_provider_health
from session_repair import refresh_claude_session
from ui_contract import action_result, serialize_snapshot
from update_service import check_for_updates
from version import __version__
from windows_integration import set_startup, startup_status


class ControlCenterApi(legacy_widget.JsApi):
    HEALTH_CACHE_TTL_SEC = 30

    def __init__(self):
        super().__init__()
        self._health_lock = threading.Lock()
        self._health_cache = None
        self._health_cached_at = 0.0

    def _provider_health(self, force=False):
        now = time.time()
        with self._health_lock:
            if not force and self._health_cache is not None and now - self._health_cached_at < self.HEALTH_CACHE_TTL_SEC:
                return self._health_cache
            self._health_cache = collect_provider_health(now=now)
            self._health_cached_at = now
            return self._health_cache

    def _invalidate_health(self):
        self._health_cached_at = 0.0

    def get_data(self):
        snap = super().get_data()
        snap["app_version"] = __version__
        snap["startup"] = startup_status()
        try:
            health = copy.deepcopy(self._provider_health())
            for provider_id, provider in (snap.get("providers") or {}).items():
                item = (health.get("providers") or {}).get(provider_id)
                if not item:
                    continue
                usage = copy.deepcopy(provider.get("usage") or {"state": "unknown", "stale": False, "last_success_at": None})
                item["usage"] = usage
                actions = recommended_actions(item.get("cli"), item.get("auth"), usage)
                item["actions"] = actions
                item["recommended_action"] = actions[0] if actions else None
            snap["provider_health"] = health
        except Exception as exc:
            snap["provider_health"] = {"schema_version": 2, "providers": {}, "error": exception_error("health_collection_failed", ErrorKind.INTERNAL, exc, retryable=True)}
        return serialize_snapshot(snap)

    def get_token_status(self):
        health = self._provider_health()
        result = {provider_id: None for provider_id in PROVIDERS}
        for provider_id in result:
            auth = ((health.get("providers") or {}).get(provider_id) or {}).get("auth") or {}
            state = auth.get("state")
            status = {"valid": "valid", "expiring": "expiring", "access_expired_refreshable": "expired", "access_missing_refreshable": "expired"}.get(state)
            if status:
                expires_at = auth.get("access_expires_at")
                result[provider_id] = {"status": status, "remaining": max(0, expires_at - time.time()) if expires_at else None}
        return result

    def get_provider_health(self):
        try:
            return copy.deepcopy(self._provider_health(force=True))
        except Exception as exc:
            return {"schema_version": 2, "providers": {}, "error": exception_error("health_collection_failed", ErrorKind.INTERNAL, exc, retryable=True)}

    def execute_provider_action(self, provider_id, action_id):
        if provider_id not in PROVIDERS:
            return action_result({"success": False, "status": "unsupported_provider", "provider_id": provider_id})
        if action_id == ActionId.INSTALL.value:
            result = install_provider(provider_id)
        elif action_id == ActionId.REFRESH_SESSION.value and PROVIDERS[provider_id].supports_session_refresh:
            result = refresh_claude_session()
        elif action_id == ActionId.LOGIN.value:
            result = login_provider(provider_id)
        elif action_id == ActionId.RETRY.value:
            started = self.refresh_now()
            result = {"success": bool(started), "status": "refresh_started" if started else "refresh_running", "provider_id": provider_id}
        elif action_id == ActionId.DIAGNOSTICS.value:
            result = {"success": True, "status": "diagnostics_ready", "provider_id": provider_id}
        else:
            return action_result({"success": False, "status": "unsupported_action", "provider_id": provider_id})
        self._invalidate_health()
        try:
            health = copy.deepcopy(self._provider_health(force=True))
        except Exception as exc:
            health = None
            result["error"] = exception_error("health_refresh_failed", ErrorKind.INTERNAL, exc, retryable=True)
        return action_result(result, provider_health=health)

    def install_provider(self, provider_id):
        return self.execute_provider_action(provider_id, ActionId.INSTALL.value)

    def refresh_provider_session(self, provider_id):
        return self.execute_provider_action(provider_id, ActionId.REFRESH_SESSION.value)

    def login_claude(self):
        return self.execute_provider_action("claude", ActionId.LOGIN.value)

    def login_codex(self):
        return self.execute_provider_action("codex", ActionId.LOGIN.value)

    def get_startup_status(self):
        return startup_status()

    def set_start_with_windows(self, enabled):
        return set_startup(bool(enabled))

    def check_for_updates(self):
        return check_for_updates()


V2JsApi = ControlCenterApi
