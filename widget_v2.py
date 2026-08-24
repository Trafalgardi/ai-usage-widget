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
    const en = (window.LANG || "ru") === "en";
    if(action === "install") return en ? `Install ${id === "claude" ? "Claude Code" : "Codex CLI"}` : `Установить ${id === "claude" ? "Claude Code" : "Codex CLI"}`;
    if(action === "refresh_session") return en ? "Refresh session" : "Обновить сессию";
    if(action === "login") return en ? "Sign in" : "Войти";
    return null;
  }

  function statusLabel(cli){
    const en = (window.LANG || "ru") === "en";
    if(cli.state === "missing") return en ? "CLI not installed" : "CLI не установлен";
    if(cli.state === "broken") return en ? "CLI found but does not start" : "CLI найден, но не запускается";
    if(cli.state === "installed") return en ? "CLI installed" : "CLI установлен";
    return cli.state || "—";
  }

  async function runAction(id, action, button){
    button.disabled = true;
    const original = button.textContent;
    button.textContent = (window.LANG || "ru") === "en" ? "Working…" : "Выполняется…";
    try{
      let result;
      if(action === "install"){
        result = await window.pywebview.api.install_provider(id);
      }else if(action === "refresh_session"){
        result = await window.pywebview.api.refresh_provider_session(id);
      }else{
        return;
      }

      if(result && result.success){
        button.textContent = (window.LANG || "ru") === "en" ? "Done" : "Готово";
        await window.pywebview.api.refresh_now();
        setTimeout(() => {
          if(typeof pull === "function") pull(true);
        }, 700);
      }else{
        button.textContent = (result && (result.status || result.error)) || ((window.LANG || "ru") === "en" ? "Failed" : "Ошибка");
        button.disabled = false;
      }
    }catch(e){
      button.textContent = original;
      button.disabled = false;
    }
  }

  const originalRenderDetail = window.renderDetail;
  if(typeof originalRenderDetail !== "function") return;

  window.renderDetail = function(id){
    originalRenderDetail(id);

    const providerHealth = window.DATA && DATA.provider_health && DATA.provider_health.providers && DATA.provider_health.providers[id];
    if(!providerHealth) return;

    const detail = document.querySelector(`#page-${id} .detail`);
    if(!detail) return;

    const cli = providerHealth.cli || {};
    const recommended = providerHealth.recommended_action;
    const action = recommended && recommended.id;

    // Legacy UI offers Login for any provider error. Structured health owns the action in v2.
    const legacyLogin = detail.querySelector(".login-btn");
    if(legacyLogin && action !== "login") legacyLogin.remove();
    if(legacyLogin && action === "login"){
      legacyLogin.textContent = actionLabel("login", id);
    }

    const health = document.createElement("div");
    health.className = "v2-health";
    const version = cli.version ? ` · ${cli.version}` : "";
    const method = cli.install_method ? ` · ${cli.install_method}` : "";
    const conflict = cli.path_conflict
      ? `<div class="warn">${(window.LANG || "ru") === "en" ? "Multiple CLI installations detected; PATH may select an old copy." : "Найдено несколько установок CLI; PATH может запускать старую копию."}</div>`
      : "";
    health.innerHTML = `<strong>${statusLabel(cli)}</strong>${version}${method}${conflict}`;
    detail.appendChild(health);

    const label = actionLabel(action, id);
    if(label && action !== "login"){
      const button = document.createElement("button");
      button.className = "login-btn v2-action";
      button.textContent = label;
      button.addEventListener("click", () => runAction(id, action, button));
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
