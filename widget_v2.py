# -*- coding: utf-8 -*-
"""Transitional v2 entry point.

Keeps the existing UI/runtime intact while provider-health is extracted from the
legacy widget.py. This file can be removed once widget.py is split into the v2
application modules.
"""

import copy
import threading
import time

import widget as legacy_widget
from auth_health import recommended_actions
from provider_actions import install_provider as run_install_provider
from provider_actions import login_provider
from provider_state import collect_provider_health
from session_repair import refresh_claude_session


V2_UI_PATCH = r"""
(() => {
  if (window.__aiUsageV2Patched) return;
  window.__aiUsageV2Patched = true;

  const style = document.createElement("style");
  style.textContent = `
    .v2-health{margin-top:10px;padding:9px 10px;border:1px solid #29292e;border-radius:7px;
      background:#151519;font-size:10px;color:#a8a8b0;line-height:1.45}
    .v2-health strong{color:#d8d8de;font-weight:600}
    .v2-health .warn{color:#f0b35e}
    .v2-action{margin-top:8px}
  `;
  document.head.appendChild(style);

  function actionLabel(action, id){
    const actionId = action && action.id ? action.id : action;
    const en = (typeof LANG !== "undefined" ? LANG : "ru") === "en";
    if(actionId === "install") return en ? `Install ${id === "claude" ? "Claude Code" : "Codex CLI"}` : `Установить ${id === "claude" ? "Claude Code" : "Codex CLI"}`;
    if(actionId === "refresh_session") return en ? "Refresh session" : "Обновить сессию";
    if(actionId === "login") return action && action.label_key === "sign_in_again" ? (en ? "Sign in again" : "Войти заново") : (en ? "Sign in" : "Войти");
    if(actionId === "retry") return en ? "Retry" : "Повторить";
    return null;
  }

  function statusLabel(cli){
    const en = (typeof LANG !== "undefined" ? LANG : "ru") === "en";
    if(cli.state === "missing") return en ? "CLI not installed" : "CLI не установлен";
    if(cli.state === "broken") return en ? "CLI found but does not start" : "CLI найден, но не запускается";
    if(cli.state === "installed") return en ? "CLI installed" : "CLI установлен";
    return cli.state || "—";
  }

  async function runAction(id, action, button){
    button.disabled = true;
    const original = button.textContent;
    button.textContent = (typeof LANG !== "undefined" ? LANG : "ru") === "en" ? "Working…" : "Выполняется…";
    try{
      const result = await window.pywebview.api.execute_provider_action(id, action);

      if(result && result.success){
        button.textContent = (typeof LANG !== "undefined" ? LANG : "ru") === "en" ? "Done" : "Готово";
        await window.pywebview.api.refresh_now();
        setTimeout(() => {
          if(typeof pull === "function") pull(true);
        }, 700);
      }else{
        button.textContent = (result && (result.status || result.error)) || ((typeof LANG !== "undefined" ? LANG : "ru") === "en" ? "Failed" : "Ошибка");
        button.disabled = false;
      }
    }catch(e){
      button.textContent = original;
      button.disabled = false;
    }
  }

  const originalRenderDetail = typeof renderDetail === "function" ? renderDetail : null;
  if(typeof originalRenderDetail !== "function") return;

  renderDetail = function(id){
    originalRenderDetail(id);

    const providerHealth = typeof DATA !== "undefined" && DATA && DATA.provider_health && DATA.provider_health.providers && DATA.provider_health.providers[id];
    if(!providerHealth) return;

    const detail = document.querySelector(`#page-${id} .detail`);
    if(!detail) return;

    const cli = providerHealth.cli || {};
    const usage = providerHealth.usage || {};
    const actions = providerHealth.actions || [];

    // Legacy UI offers Login for any provider error. Structured health owns the action in v2.
    const legacyLogin = detail.querySelector(".login-btn");
    if(legacyLogin) legacyLogin.remove();

    const health = document.createElement("div");
    health.className = "v2-health";
    const version = cli.version ? ` · ${cli.version}` : "";
    const method = cli.install_method ? ` · ${cli.install_method}` : "";
    const conflict = cli.path_conflict
      ? `<div class="warn">${(typeof LANG !== "undefined" ? LANG : "ru") === "en" ? "Multiple CLI installations detected; PATH may select an old copy." : "Найдено несколько установок CLI; PATH может запускать старую копию."}</div>`
      : "";
    const stale = usage.stale
      ? `<div class="warn">${(typeof LANG !== "undefined" ? LANG : "ru") === "en" ? "Usage temporarily unavailable; showing the last successful update." : "Usage временно недоступен; показаны последние успешные данные."}</div>`
      : "";
    health.innerHTML = `<strong>${statusLabel(cli)}</strong>${version}${method}${conflict}${stale}`;
    detail.appendChild(health);

    for(const action of actions){
      const label = actionLabel(action, id);
      if(!label) continue;
      const button = document.createElement("button");
      button.className = "login-btn v2-action";
      button.textContent = label;
      button.addEventListener("click", () => runAction(id, action.id, button));
      detail.appendChild(button);
    }
  };

  if(typeof renderAll === "function") renderAll();
})();
"""


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

    def _invalidate_health(self):
        self._health_cached_at = 0.0

    def get_data(self):
        snap = super().get_data()
        try:
            health = copy.deepcopy(self._provider_health())
            for provider_id, provider in (snap.get("providers") or {}).items():
                provider_health = (health.get("providers") or {}).get(provider_id)
                if not provider_health:
                    continue
                usage = copy.deepcopy(provider.get("usage") or {
                    "state": "unknown", "stale": False, "last_success_at": None
                })
                provider_health["usage"] = usage
                actions = recommended_actions(
                    provider_health.get("cli"), provider_health.get("auth"), usage
                )
                provider_health["actions"] = actions
                provider_health["recommended_action"] = actions[0] if actions else None
            snap["provider_health"] = health
        except Exception as exc:
            snap["provider_health"] = {
                "schema_version": 2,
                "providers": {},
                "error": f"{type(exc).__name__}: {exc}",
            }
        return snap

    def get_token_status(self):
        """Backward-compatible badge state derived from structured auth health."""
        health = self._provider_health()
        result = {"claude": None, "codex": None}
        for provider_id in result:
            auth = ((health.get("providers") or {}).get(provider_id) or {}).get("auth") or {}
            state = auth.get("state")
            if state == "valid":
                status = "valid"
            elif state == "expiring":
                status = "expiring"
            elif state in ("access_expired_refreshable", "access_missing_refreshable"):
                status = "expired"
            else:
                continue
            expires_at = auth.get("access_expires_at")
            result[provider_id] = {
                "status": status,
                "remaining": max(0, expires_at - time.time()) if expires_at else None,
            }
        return result

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
        self._invalidate_health()
        return result

    def refresh_provider_session(self, provider_id):
        if provider_id != "claude":
            return {
                "success": False,
                "status": "refresh_not_supported",
                "provider_id": provider_id,
            }
        result = refresh_claude_session()
        self._invalidate_health()
        return result

    def execute_provider_action(self, provider_id, action_id):
        """Dispatch only backend-declared, explicitly allowlisted actions."""
        if provider_id not in ("claude", "codex"):
            return {"success": False, "status": "unsupported_provider"}
        if action_id == "install":
            result = run_install_provider(provider_id)
        elif action_id == "refresh_session" and provider_id == "claude":
            result = refresh_claude_session()
        elif action_id == "login":
            result = login_provider(provider_id)
        elif action_id == "retry":
            started = self.refresh_now()
            result = {"success": bool(started), "status": "refresh_started" if started else "refresh_running"}
        else:
            return {"success": False, "status": "unsupported_action"}
        self._invalidate_health()
        return result

    def _login_compat(self, provider_id):
        result = login_provider(provider_id)
        self._invalidate_health()
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


def _patch_webview_ui():
    try:
        import webview
    except ImportError:
        return

    original_create_window = webview.create_window

    def create_window_with_v2(*args, **kwargs):
        window = original_create_window(*args, **kwargs)

        def on_loaded():
            try:
                window.evaluate_js(V2_UI_PATCH)
            except Exception:
                pass

        try:
            window.events.loaded += on_loaded
        except Exception:
            pass
        return window

    webview.create_window = create_window_with_v2


if __name__ == "__main__":
    _patch_webview_ui()
    legacy_widget.main()
