# -*- coding: utf-8 -*-
"""Legacy quota/tray runtime retained by the v2 Windows AI CLI Control Center.

The release entry point is ``widget_v2.py``. New provider lifecycle behavior
belongs in the extracted health, action, storage, and UI bridge modules.
"""

import base64
import copy
import json
import os
import subprocess
import sys
import threading
import time
import traceback
import urllib.request
import urllib.error
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone

from app_storage import ConfigStore
from auth_health import inspect_claude_auth
from session_repair import attempt_automatic_claude_recovery
from usage_health import LastGoodUsageStore, classify_exception, usage_error
from usage_history import HistoryStore
from version import APP_NAME

try:
    import pystray
    from PIL import Image, ImageDraw, ImageFont
    TRAY_AVAILABLE = True
except ImportError:
    TRAY_AVAILABLE = False

APP_DIR = getattr(sys, "_MEIPASS", os.path.dirname(os.path.abspath(__file__)))
LEGACY_DATA_DIR = os.path.dirname(os.path.abspath(sys.executable)) if getattr(sys, "frozen", False) else APP_DIR
DATA_DIR = (
    os.path.join(os.environ.get("LOCALAPPDATA") or os.environ.get("APPDATA") or LEGACY_DATA_DIR, APP_NAME)
    if getattr(sys, "frozen", False)
    else APP_DIR
)
HOME = os.path.expanduser("~")
CONFIG_PATH = os.path.join(DATA_DIR, "config.json")
HISTORY_PATH = os.path.join(DATA_DIR, "history.json")

DEFAULT_CONFIG = {
    "language": "en",
    "refresh_interval_sec": 60,
    "history": {"enabled": True, "retention_days": 30},
    "alerts": {"enabled": False, "remaining_threshold_pct": 15, "cooldown_sec": 3600},
    "window": {"x": None, "y": None, "width": 380, "height": 600, "on_top": True},
    "opencode": {
        # Если у OpenCode появится/известен официальный usage-эндпоинт — впиши его сюда.
        "usage_endpoint": "",
        # Кандидаты, которые виджет попробует автоматически:
        "endpoint_candidates": [
            "https://opencode.ai/api/usage",
            "https://opencode.ai/zen/v1/usage",
            "https://opencode.ai/zen/go/v1/usage",
            "https://api.opencode.ai/v1/usage",
        ],
        # Ручной режим: если API недоступен, можно вписать лимиты плана (в $)
        # и виджет посчитает расход по локальной статистике opencode (если найдёт).
        "manual_limits": {"session_usd": None, "week_usd": None, "month_usd": None},
    },
}

SETTINGS_STORE = ConfigStore(CONFIG_PATH, DEFAULT_CONFIG)
if getattr(sys, "frozen", False):
    SETTINGS_STORE.migrate_from(os.path.join(LEGACY_DATA_DIR, "config.json"))


# ----------------------------------------------------------------------------
# helpers
# ----------------------------------------------------------------------------

def load_config():
    return SETTINGS_STORE.load()


def save_config(cfg):
    try:
        return SETTINGS_STORE.save(cfg)
    except Exception:
        return False


def http_get_json(url, headers=None, timeout=15):
    req = urllib.request.Request(url, headers=headers or {})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        raw = r.read().decode("utf-8", "replace")
    return json.loads(raw)


def iso_to_epoch(value):
    """Принимает ISO-строку / unix-число / None -> epoch seconds или None."""
    if value is None:
        return None
    if isinstance(value, (int, float)):
        # уже epoch (секунды или миллисекунды)
        return value / 1000.0 if value > 4e10 else float(value)
    if isinstance(value, str):
        s = value.strip()
        try:
            return float(s)
        except ValueError:
            pass
        try:
            if s.endswith("Z"):
                s = s[:-1] + "+00:00"
            dt = datetime.fromisoformat(s)
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            return dt.timestamp()
        except Exception:
            return None
    return None


def pick(d, *keys):
    for k in keys:
        if isinstance(d, dict) and d.get(k) is not None:
            return d[k]
    return None


def make_window(win_id, label, used_pct=None, resets_at=None,
                used_usd=None, limit_usd=None, extra=None):
    """Нормализованное окно лимита."""
    if used_pct is None and used_usd is not None and limit_usd:
        used_pct = 100.0 * float(used_usd) / float(limit_usd)
    if used_pct is not None:
        used_pct = max(0.0, min(100.0, float(used_pct)))
    return {
        "id": win_id,
        "label": label,
        "used_pct": used_pct,
        "remaining_pct": None if used_pct is None else round(100.0 - used_pct, 2),
        "resets_at": resets_at,          # epoch seconds или None
        "used_usd": used_usd,
        "limit_usd": limit_usd,
        "extra": extra or {},
    }


# ----------------------------------------------------------------------------
# Claude Code
# ----------------------------------------------------------------------------

CLAUDE_CRED_PATHS = [
    os.path.join(HOME, ".claude", ".credentials.json"),
    os.path.join(HOME, ".config", "claude", ".credentials.json"),
]
CLAUDE_USAGE_URLS = [
    "https://api.anthropic.com/api/oauth/usage",
    "https://claude.ai/api/oauth/usage",
]


def _read_claude_credentials():
    """Read only the access credential needed for the usage request."""
    token = None
    subscription = None
    token_stale = False
    for p in CLAUDE_CRED_PATHS:
        if os.path.exists(p):
            try:
                with open(p, "r", encoding="utf-8") as f:
                    data = json.load(f)
                oauth = data.get("claudeAiOauth") or data.get("oauth") or {}
                token = oauth.get("accessToken") or oauth.get("access_token")
                subscription = oauth.get("subscriptionType")
                exp = oauth.get("expiresAt")
                if exp and iso_to_epoch(exp) and iso_to_epoch(exp) < time.time():
                    token_stale = True
            except Exception:
                pass
            break
    return token, subscription, token_stale


def _fetch_claude_usage(headers):
    """Fetch Claude usage once, stopping immediately on an auth response."""
    last_error = None
    for url in CLAUDE_USAGE_URLS:
        try:
            return http_get_json(url, headers), None, None
        except urllib.error.HTTPError as exc:
            last_error = exc
            if exc.code in (401, 403):
                return None, last_error, exc
        except Exception as exc:
            last_error = exc
    return None, last_error, None


def _claude_headers(token):
    return {
        "Authorization": f"Bearer {token}",
        "anthropic-beta": "oauth-2025-04-20",
        "Content-Type": "application/json",
        "Accept": "application/json",
        "User-Agent": "ai-usage-widget/1.0",
    }


def _parse_claude_usage(data, result):
    label_map = {
        "five_hour": ("session", "Сессия (5 ч)"),
        "seven_day": ("week", "Неделя"),
        "seven_day_sonnet": ("week_sonnet", "Неделя · Sonnet"),
        "seven_day_opus": ("week_opus", "Неделя · Opus"),
        "seven_day_oauth_apps": ("week_apps", "Неделя · приложения"),
    }
    for key, (wid, label) in label_map.items():
        obj = data.get(key)
        if not isinstance(obj, dict):
            continue
        pct = pick(obj, "utilization", "used_percent", "usage_percent")
        resets = iso_to_epoch(pick(obj, "resets_at", "reset_at", "resetsAt"))
        if pct is not None or resets is not None:
            result["windows"].append(make_window(wid, label, used_pct=pct, resets_at=resets))

    extra = data.get("extra_usage") or data.get("extraUsage")
    if isinstance(extra, dict):
        result["meta"]["extra_usage"] = extra


def fetch_claude():
    result = {"id": "claude", "name": "Claude Code", "ok": False,
              "windows": [], "meta": {}, "error": None}
    auth = inspect_claude_auth()
    token, subscription, token_stale = _read_claude_credentials()
    recovery = None
    recovery_decided = False
    if auth.get("state") in ("access_expired_refreshable", "access_missing_refreshable"):
        recovery = attempt_automatic_claude_recovery(auth, trigger="auth_metadata")
        recovery_decided = True
        result["meta"]["session_recovery"] = (
            "session_recovered" if recovery.get("success") else recovery.get("status")
        )
        if recovery.get("success"):
            # Claude Code owns the credential rotation; re-read only after it
            # reports recovery so the retry cannot reuse the stale access token.
            token, subscription, token_stale = _read_claude_credentials()
    if subscription:
        result["meta"]["subscription"] = subscription
    if token_stale:
        result["meta"]["token_stale"] = True
    if not token:
        result["error"] = (
            "Не найден токен Claude Code (~/.claude/.credentials.json). "
            "Открой Claude Code и выполни /login.")
        return result

    data, error, auth_error = _fetch_claude_usage(_claude_headers(token))
    if auth_error and not recovery_decided:
        fresh_auth = inspect_claude_auth()
        if fresh_auth.get("state") in ("access_expired_refreshable", "access_missing_refreshable"):
            recovery = attempt_automatic_claude_recovery(fresh_auth, trigger=f"usage_{auth_error.code}")
            recovery_decided = True
            result["meta"]["session_recovery"] = (
                "session_recovered" if recovery.get("success") else recovery.get("status")
            )
            if recovery.get("success"):
                token, subscription, token_stale = _read_claude_credentials()
                if subscription:
                    result["meta"]["subscription"] = subscription
                if token_stale:
                    result["meta"]["token_stale"] = True
                if token:
                    data, error, auth_error = _fetch_claude_usage(_claude_headers(token))

    if data is None:
        if error:
            result["usage"] = classify_exception(error)
            if isinstance(error, urllib.error.HTTPError):
                result["error"] = f"HTTP {error.code} — сессию не удалось подтвердить" if error.code in (401, 403) else f"HTTP {error.code}"
            else:
                result["error"] = f"{type(error).__name__}: {error}"
        else:
            result["error"] = "Нет ответа от API"
        return result

    _parse_claude_usage(data, result)

    if result["windows"]:
        result["ok"] = True
    else:
        result["error"] = "API ответил, но формат не распознан"
        result["usage"] = usage_error("format", result["error"])
        result["meta"]["raw_keys"] = list(data.keys())[:12]
    return result


# ----------------------------------------------------------------------------
# Codex CLI (ChatGPT)
# ----------------------------------------------------------------------------

def _codex_home():
    return os.environ.get("CODEX_HOME") or os.path.join(HOME, ".codex")


def _jwt_claims(jwt):
    try:
        payload = jwt.split(".")[1]
        payload += "=" * (-len(payload) % 4)
        return json.loads(base64.urlsafe_b64decode(payload.encode()))
    except Exception:
        return {}


def fetch_codex():
    result = {"id": "codex", "name": "Codex CLI", "ok": False,
              "windows": [], "meta": {}, "error": None}
    auth_path = os.path.join(_codex_home(), "auth.json")
    if not os.path.exists(auth_path):
        result["error"] = ("Не найден ~/.codex/auth.json. "
                           "Выполни `codex login` в терминале.")
        return result
    try:
        with open(auth_path, "r", encoding="utf-8") as f:
            auth = json.load(f)
    except Exception as e:
        result["error"] = f"Не удалось прочитать auth.json: {e}"
        return result

    tokens = auth.get("tokens") or {}
    access = tokens.get("access_token") or auth.get("access_token")
    account_id = tokens.get("account_id") or auth.get("account_id")
    if not account_id:
        for t in (tokens.get("id_token"), access):
            if not t:
                continue
            claims = _jwt_claims(t)
            oai = claims.get("https://api.openai.com/auth") or {}
            account_id = oai.get("chatgpt_account_id") or oai.get("account_id")
            if account_id:
                plan = oai.get("chatgpt_plan_type")
                if plan:
                    result["meta"]["plan"] = plan
                break
    if not access:
        result["error"] = "В auth.json нет access_token. Выполни `codex login`."
        return result

    headers = {
        "Authorization": f"Bearer {access}",
        "Accept": "application/json",
        "Content-Type": "application/json",
        "User-Agent": "ai-usage-widget/1.0",
    }
    if account_id:
        headers["chatgpt-account-id"] = account_id

    try:
        data = http_get_json("https://chatgpt.com/backend-api/wham/usage", headers)
    except urllib.error.HTTPError as e:
        msg = f"HTTP {e.code}"
        if e.code in (401, 403):
            msg += " — сессию не удалось подтвердить"
        result["error"] = msg
        result["usage"] = classify_exception(e)
        return result
    except Exception as e:
        result["error"] = f"{type(e).__name__}: {e}"
        result["usage"] = classify_exception(e)
        return result

    if isinstance(data.get("plan_type"), str):
        result["meta"]["plan"] = data["plan_type"]

    rl = data.get("rate_limit") or data.get("rate_limits") or {}

    def add_window(obj, wid, fallback_label):
        if not isinstance(obj, dict):
            return
        pct = pick(obj, "used_percent", "usage_percent", "utilization")
        resets = iso_to_epoch(pick(obj, "resets_at", "reset_at", "reset_time"))
        if resets is None:
            secs = pick(obj, "resets_in_seconds", "reset_after_seconds")
            if secs is not None:
                resets = time.time() + float(secs)
        # длина окна помогает подписать: минуты
        mins = pick(obj, "window_minutes", "limit_window_minutes")
        label = fallback_label
        if mins:
            mins = float(mins)
            if mins <= 6 * 60:
                label = "Сессия (5 ч)"
            elif mins >= 6.5 * 24 * 60:
                label = "Неделя"
        if pct is not None or resets is not None:
            result["windows"].append(make_window(wid, label, used_pct=pct, resets_at=resets))

    add_window(rl.get("primary_window") or rl.get("primary"), "session", "Сессия (5 ч)")
    add_window(rl.get("secondary_window") or rl.get("secondary"), "week", "Неделя")

    # дополнительные модельные лимиты (например, Spark)
    for i, item in enumerate(data.get("additional_rate_limits") or []):
        if not isinstance(item, dict):
            continue
        title = item.get("title") or item.get("id") or f"Доп. лимит {i+1}"
        obj = item.get("window") or item.get("rate_limit") or item
        pct = pick(obj, "used_percent", "usage_percent")
        resets = iso_to_epoch(pick(obj, "resets_at"))
        if resets is None and obj.get("resets_in_seconds") is not None:
            resets = time.time() + float(obj["resets_in_seconds"])
        if pct is not None:
            result["windows"].append(make_window(f"extra_{i}", str(title),
                                                 used_pct=pct, resets_at=resets))

    credits = data.get("credits")
    if isinstance(credits, dict):
        result["meta"]["credits"] = pick(credits, "balance", "remaining", "amount")

    if result["windows"]:
        result["ok"] = True
    else:
        result["error"] = "API ответил, но лимиты не найдены"
        result["usage"] = usage_error("format", result["error"])
        result["meta"]["raw_keys"] = list(data.keys())[:12]
    return result


# ----------------------------------------------------------------------------
# OpenCode (Zen / Go)
# ----------------------------------------------------------------------------

OPENCODE_AUTH_PATHS = [
    os.path.join(HOME, ".local", "share", "opencode", "auth.json"),
    os.path.join(os.environ.get("LOCALAPPDATA", ""), "opencode", "auth.json"),
    os.path.join(os.environ.get("APPDATA", ""), "opencode", "auth.json"),
    os.path.join(os.environ.get("XDG_DATA_HOME", ""), "opencode", "auth.json"),
]


def _opencode_key():
    for p in OPENCODE_AUTH_PATHS:
        if p and os.path.exists(p):
            try:
                with open(p, "r", encoding="utf-8") as f:
                    data = json.load(f)
            except Exception:
                continue
            # ключи хранятся по id провайдера: "opencode", "opencode-go", "zen"...
            for prov_id in ("opencode", "opencode-go", "opencode-zen", "zen"):
                entry = data.get(prov_id)
                if isinstance(entry, dict):
                    key = entry.get("key") or entry.get("apiKey") or entry.get("api_key")
                    if key:
                        return key, prov_id
            # иначе — первый попавшийся api-ключ
            for prov_id, entry in data.items():
                if isinstance(entry, dict) and entry.get("type") in ("api", "apikey"):
                    key = entry.get("key")
                    if key:
                        return key, prov_id
    return None, None


def _parse_opencode_payload(data, result):
    """Гибкий разбор ответа usage: rolling5h/weekly/monthly и варианты."""
    alias = {
        "session": ("session", "Сессия (5 ч)"),
        "rolling5h": ("session", "Сессия (5 ч)"),
        "five_hour": ("session", "Сессия (5 ч)"),
        "fiveHour": ("session", "Сессия (5 ч)"),
        "week": ("week", "Неделя"),
        "weekly": ("week", "Неделя"),
        "seven_day": ("week", "Неделя"),
        "month": ("month", "Месяц"),
        "monthly": ("month", "Месяц"),
        "thirty_day": ("month", "Месяц"),
    }
    container = data
    for k in ("usage", "limits", "windows", "data"):
        if isinstance(data.get(k), dict):
            container = data[k]
            break
    for key, obj in (container.items() if isinstance(container, dict) else []):
        if key not in alias or not isinstance(obj, dict):
            continue
        wid, label = alias[key]
        pct = pick(obj, "usagePercent", "usedPercent", "used_percent", "utilization", "percent")
        used_usd = pick(obj, "usageDollars", "usedDollars", "usage_usd", "spent", "used")
        limit_usd = pick(obj, "limitDollars", "limit_usd", "limit", "cap")
        resets = iso_to_epoch(pick(obj, "resets_at", "resetAt", "resetsAt"))
        if resets is None:
            secs = pick(obj, "resetInSec", "resets_in_seconds", "resetInSeconds")
            if secs is not None:
                resets = time.time() + float(secs)
        if pct is not None or (used_usd is not None and limit_usd):
            result["windows"].append(make_window(
                wid, label, used_pct=pct, resets_at=resets,
                used_usd=used_usd, limit_usd=limit_usd))
    if isinstance(data.get("balance"), (int, float)):
        result["meta"]["balance_usd"] = data["balance"]
    plan = pick(data, "plan", "subscription", "tier")
    if isinstance(plan, str):
        result["meta"]["plan"] = plan


def fetch_opencode(cfg):
    result = {"id": "opencode", "name": "OpenCode", "ok": False,
              "windows": [], "meta": {}, "error": None}
    key, prov_id = _opencode_key()
    if not key:
        result["error"] = ("Не найден API-ключ OpenCode "
                           "(~/.local/share/opencode/auth.json). "
                           "В opencode выполни /connect → OpenCode Zen/Go.")
        return result
    result["meta"]["provider_id"] = prov_id

    oc_cfg = cfg.get("opencode", {})
    endpoints = []
    if oc_cfg.get("usage_endpoint"):
        endpoints.append(oc_cfg["usage_endpoint"])
    endpoints += oc_cfg.get("endpoint_candidates", [])

    headers = {
        "Authorization": f"Bearer {key}",
        "Accept": "application/json",
        "User-Agent": "ai-usage-widget/1.0",
    }
    last_err = None
    for url in endpoints:
        try:
            data = http_get_json(url, headers, timeout=8)
            if isinstance(data, dict):
                _parse_opencode_payload(data, result)
                if result["windows"]:
                    result["ok"] = True
                    result["meta"]["endpoint"] = url
                    if oc_cfg.get("usage_endpoint") != url:
                        cfg.setdefault("opencode", {})["usage_endpoint"] = url
                        save_config(cfg)
                    return result
        except urllib.error.HTTPError as e:
            last_err = f"HTTP {e.code} от {url}"
        except Exception as e:
            last_err = f"{type(e).__name__}: {e}"

    result["error"] = (
        "У OpenCode пока нет публичного usage-API. "
        "Лимиты видны в консоли opencode.ai. Если появится эндпоинт — "
        "впиши его в config.json → opencode.usage_endpoint."
        + (f" (последняя ошибка: {last_err})" if last_err else ""))
    result["meta"]["console_url"] = "https://opencode.ai"
    return result


# ----------------------------------------------------------------------------
# сбор данных + JS API
# ----------------------------------------------------------------------------

class State:
    def __init__(self):
        self.lock = threading.Lock()
        self.refresh_lock = threading.Lock()
        self.shutdown_event = threading.Event()
        self.snapshot = {"updated_at": None, "providers": {}}


STATE = State()
CFG = load_config()


class TrayManager:
    def __init__(self):
        self.icon_app = None
        self.icon_claude = None
        self.icon_codex = None
        self.window_ref = None
        self._thread = None

    def _create_icon_image(self, text="", color="#FFFFFF", outline=None, bg_color=None):
        size = 64
        img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
        draw = ImageDraw.Draw(img)
        
        try:
            font = ImageFont.truetype("arialbd.ttf", 48)
        except Exception:
            try:
                font = ImageFont.truetype("arial.ttf", 48)
            except Exception:
                font = ImageFont.load_default()
        
        if text:
            if outline:
                draw.text((size//2, size//2), text, fill=color, font=font, anchor="mm", stroke_width=3, stroke_fill=outline)
            else:
                draw.text((size//2, size//2), text, fill=color, font=font, anchor="mm")
        
        return img

    def _get_session_pcts(self):
        with STATE.lock:
            snap = copy.deepcopy(STATE.snapshot)
        result = {}
        for pid in ["claude", "codex"]:
            p = snap["providers"].get(pid)
            has_usage = p and (p.get("ok") or (p.get("usage") or {}).get("stale"))
            if has_usage:
                w = next((x for x in p.get("windows", []) if x["id"] == "session"), None)
                if w and w.get("remaining_pct") is not None:
                    result[pid] = round(w["remaining_pct"], 1)
        return result

    def _update_icon_with_data(self):
        if not TRAY_AVAILABLE:
            return
        # The application icon is deliberately independent of usage data.  A
        # hidden window must never lose its only route back to the user.
        self.ensure_available()
        pcts = self._get_session_pcts()
        providers = {"claude": "Claude Code", "codex": "Codex CLI"}
        icon_attrs = {"claude": "icon_claude", "codex": "icon_codex"}
        thread_attrs = {"claude": "_thread_claude", "codex": "_thread_codex"}
        
        for pid, pname in providers.items():
            pct = pcts.get(pid)
            has_data = pct is not None
            icon = getattr(self, icon_attrs[pid], None)
            
            if has_data:
                text = f"{int(pct):02d}"
                if pid == "claude":
                    img = self._create_icon_image(text, color="#D97757")
                else:
                    img = self._create_icon_image(text, color="#2ECC40", outline="#1a7a25")
                if icon:
                    # Обновляем существующую иконку
                    try:
                        icon.icon = img
                        icon.title = self._build_tooltip()
                    except Exception:
                        pass
                else:
                    # Создаём новую иконку
                    self._create_tray_icon(pid, pname, img)
            else:
                if icon:
                    # Provider indicators are optional; the permanent app icon
                    # remains available when a provider has no usable quota.
                    try:
                        icon.stop()
                    except Exception:
                        pass
                    setattr(self, icon_attrs[pid], None)
                    setattr(self, thread_attrs[pid], None)

    def _menu(self):
        lang = (CFG.get("language") or "ru")[:2]
        labels = {
            "show": "Show" if lang == "en" else "Показать",
            "refresh": "Refresh" if lang == "en" else "Обновить",
            "exit": "Exit" if lang == "en" else "Выход",
        }
        return pystray.Menu(
            pystray.MenuItem(labels["show"], self._on_show, default=True),
            pystray.MenuItem(labels["refresh"], self._on_refresh),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem(labels["exit"], self._on_quit),
        )

    def _run_icon(self, icon, attribute, thread_attribute):
        ready = threading.Event()

        def run():
            try:
                icon.run(setup=lambda _: ready.set())
            except Exception:
                # A failed backend never sets ready, so callers retain the
                # visible application window instead of entering a dead state.
                pass

        try:
            thread = threading.Thread(target=run, daemon=True)
            thread.start()
        except Exception:
            return False
        if not ready.wait(timeout=2):
            try:
                icon.stop()
            except Exception:
                pass
            return False
        setattr(self, attribute, icon)
        setattr(self, thread_attribute, thread)
        return True

    def ensure_available(self):
        """Ensure the permanent application tray icon is running.

        This is called before hiding the WebView.  Failure is intentionally
        observable by callers so they can leave the window visible.
        """
        if not TRAY_AVAILABLE or not self.window_ref:
            return False
        if self.icon_app:
            return True
        try:
            icon = pystray.Icon(
                "ai-cli-control-center",
                self._create_icon_image("AI", color="#FFFFFF", outline="#2ECC40"),
                self._build_tooltip(),
                self._menu(),
            )
        except Exception:
            return False
        return self._run_icon(icon, "icon_app", "_thread_app")

    def _create_tray_icon(self, pid, pname, img):
        """Create an optional provider percentage indicator."""
        try:
            menu = self._menu()
        except Exception:
            return False
        name = f"ai-usage-{pid}"
        try:
            icon = pystray.Icon(name, img, pname, menu)
        except Exception:
            return False
        if pid == "claude":
            return self._run_icon(icon, "icon_claude", "_thread_claude")
        else:
            return self._run_icon(icon, "icon_codex", "_thread_codex")

    def _build_tooltip(self):
        with STATE.lock:
            snap = copy.deepcopy(STATE.snapshot)
        if not snap.get("updated_at"):
            return APP_NAME
        lines = [APP_NAME]
        for pid, pname in [("claude", "Claude"), ("codex", "Codex")]:
            p = snap["providers"].get(pid)
            has_usage = p and (p.get("ok") or (p.get("usage") or {}).get("stale"))
            if not has_usage:
                lines.append(f"{pname}: —")
                continue
            w = next((x for x in p.get("windows", []) if x["id"] == "session"), None)
            if not w or w.get("remaining_pct") is None:
                lines.append(f"{pname}: —")
                continue
            pct = round(w["remaining_pct"], 1)
            resets = w.get("resets_at")
            if resets:
                secs = max(0, int(resets - time.time()))
                h, rem = divmod(secs, 3600)
                m = rem // 60
                lang = (CFG.get("language") or "ru")[:2]
                hu = "h" if lang == "en" else "ч"
                mu = "m" if lang == "en" else "м"
                reset_label = "resets in" if lang == "en" else "сброс"
                reset_str = f"{h}{hu} {m}{mu}" if h > 0 else f"{m}{mu}"
                lines.append(f"{pname}: {pct}% ({reset_label} {reset_str})")
            else:
                lines.append(f"{pname}: {pct}%")
        return "\n".join(lines)

    def _on_show(self, icon, item):
        if self.window_ref:
            self.window_ref.show()

    def _on_quit(self, icon, item):
        STATE.shutdown_event.set()
        if self.icon_app:
            try:
                self.icon_app.stop()
            except Exception:
                pass
        if self.icon_claude:
            try:
                self.icon_claude.stop()
            except Exception:
                pass
        if self.icon_codex:
            try:
                self.icon_codex.stop()
            except Exception:
                pass
        if self.window_ref:
            try:
                self.window_ref.destroy()
            except Exception:
                pass

    def _on_refresh(self, icon, item):
        threading.Thread(target=refresh_all, daemon=True).start()

    def start(self, window):
        if not TRAY_AVAILABLE:
            return False
        self.window_ref = window
        return self.ensure_available()

    def update_tooltip(self):
        tooltip = self._build_tooltip()
        if self.icon_app:
            try:
                self.icon_app.title = tooltip
            except Exception:
                pass
        if self.icon_claude:
            try:
                self.icon_claude.title = tooltip
            except Exception:
                pass
        if self.icon_codex:
            try:
                self.icon_codex.title = tooltip
            except Exception:
                pass

    def hide_window(self):
        if self.window_ref:
            self.window_ref.hide()

    def notify_alerts(self, alerts):
        """Send opt-in local notifications through an existing tray icon."""
        if not TRAY_AVAILABLE or not alerts:
            return
        icon = self.icon_app or self.icon_claude or self.icon_codex
        if not icon or not hasattr(icon, "notify"):
            return
        for alert in alerts:
            provider = "Claude" if alert.get("provider_id") == "claude" else "Codex"
            remaining = alert.get("remaining_pct")
            if alert.get("kind") == "projected_exhaustion":
                message = f"{provider} may exhaust this limit before it resets."
            else:
                message = f"{provider} has {remaining:g}% remaining in this limit window."
            try:
                icon.notify(message, APP_NAME)
            except Exception:
                pass


TRAY = TrayManager()
LAST_GOOD_USAGE = LastGoodUsageStore()
HISTORY_STORE = HistoryStore(HISTORY_PATH)


def refresh_all():
    if not STATE.refresh_lock.acquire(blocking=False):
        return
    try:
        providers = {}
        with ThreadPoolExecutor(max_workers=2) as executor:
            futures = {
                executor.submit(fetch_claude): "claude",
                executor.submit(fetch_codex): "codex",
            }
            for future in as_completed(futures):
                name = futures[future]
                try:
                    provider = future.result()
                except Exception as exc:
                    provider = {"id": name, "name": name, "ok": False,
                                "windows": [], "meta": {},
                                "error": "Внутренняя ошибка:\n" + traceback.format_exc(limit=2),
                                "usage": usage_error(
                                    "unknown", f"{type(exc).__name__}: {exc}"
                                )}
                providers[name] = LAST_GOOD_USAGE.apply(provider)
        captured_at = time.time()
        insights = HISTORY_STORE.process(providers, CFG, captured_at)
        with STATE.lock:
            STATE.snapshot = {"updated_at": captured_at, "providers": providers, "insights": insights}
        TRAY.update_tooltip()
        TRAY._update_icon_with_data()
        TRAY.notify_alerts(insights.get("alerts") or [])
    finally:
        STATE.refresh_lock.release()


def refresh_loop():
    while not STATE.shutdown_event.is_set():
        try:
            refresh_all()
        except Exception:
            pass
        STATE.shutdown_event.wait(timeout=max(15, int(CFG.get("refresh_interval_sec", 60))))


class JsApi:
    def get_data(self):
        with STATE.lock:
            snap = copy.deepcopy(STATE.snapshot)
        snap["now"] = time.time()
        snap["refresh_interval_sec"] = CFG.get("refresh_interval_sec", 60)
        snap["token_status"] = self.get_token_status()
        try:
            snap["on_top"] = CFG["window"].get("on_top", True)
        except Exception:
            snap["on_top"] = True
        snap["_config"] = copy.deepcopy(CFG)
        return snap

    def refresh_now(self):
        if STATE.refresh_lock.locked():
            return False
        threading.Thread(target=refresh_all, daemon=True).start()
        return True

    def login_claude(self):
        """Запускает claude auth login в фоне."""
        try:
            proc = subprocess.Popen(
                ["claude", "auth", "login"],
                creationflags=subprocess.CREATE_NEW_CONSOLE,
                encoding='utf-8',
                errors='replace'
            )
            return {"success": True, "output": "Авторизация запущена"}
        except FileNotFoundError:
            return {"success": False, "output": "Claude CLI не найден"}
        except Exception as e:
            return {"success": False, "output": f"Ошибка: {str(e)}"}

    def login_codex(self):
        """Запускает codex login в фоне."""
        try:
            proc = subprocess.Popen(
                ["codex", "login"],
                creationflags=subprocess.CREATE_NEW_CONSOLE,
                encoding='utf-8',
                errors='replace'
            )
            return {"success": True, "output": "Авторизация запущена"}
        except FileNotFoundError:
            return {"success": False, "output": "Codex CLI не найден"}
        except Exception as e:
            return {"success": False, "output": f"Ошибка: {str(e)}"}
    
    def get_token_status(self):
        """Проверяет статус токенов Claude и Codex."""
        result = {"claude": None, "codex": None}
        
        # Claude
        cred_paths = [
            os.path.join(HOME, ".claude", ".credentials.json"),
            os.path.join(HOME, ".config", "claude", ".credentials.json"),
        ]
        for p in cred_paths:
            if os.path.exists(p):
                try:
                    with open(p, "r", encoding="utf-8") as f:
                        data = json.load(f)
                    oauth = data.get("claudeAiOauth") or data.get("oauth") or {}
                    exp = oauth.get("expiresAt")
                    if exp:
                        exp_epoch = iso_to_epoch(exp)
                        if exp_epoch:
                            now = time.time()
                            remaining = exp_epoch - now
                            if remaining <= 0:
                                result["claude"] = {"status": "expired", "remaining": 0}
                            elif remaining < 3600:
                                result["claude"] = {"status": "expiring", "remaining": remaining}
                            else:
                                result["claude"] = {"status": "valid", "remaining": remaining}
                except Exception:
                    pass
                break
        
        # Codex
        auth_path = os.path.join(_codex_home(), "auth.json")
        if os.path.exists(auth_path):
            try:
                with open(auth_path, "r", encoding="utf-8") as f:
                    auth = json.load(f)
                tokens = auth.get("tokens") or {}
                access = tokens.get("access_token") or auth.get("access_token")
                if access:
                    claims = _jwt_claims(access)
                    exp = claims.get("exp")
                    if exp:
                        now = time.time()
                        remaining = exp - now
                        if remaining <= 0:
                            result["codex"] = {"status": "expired", "remaining": 0}
                        elif remaining < 3600:
                            result["codex"] = {"status": "expiring", "remaining": remaining}
                        else:
                            result["codex"] = {"status": "valid", "remaining": remaining}
            except Exception:
                pass
        
        return result

    def toggle_on_top(self):
        new_val = not CFG["window"].get("on_top", True)
        def _do():
            try:
                win = webview.windows[0]
                win.on_top = new_val
                CFG["window"]["on_top"] = new_val
                save_config(CFG)
            except Exception:
                pass
        threading.Thread(target=_do, daemon=True).start()
        return new_val

    def get_config(self):
        return copy.deepcopy(CFG)

    def save_config_api(self, cfg):
        global CFG
        try:
            old_lang = CFG.get("language", "ru")
            for k, v in cfg.items():
                if isinstance(v, dict) and isinstance(CFG.get(k), dict):
                    CFG[k].update(v)
                else:
                    CFG[k] = v
            save_config(CFG)
            # Применить настройки окна
            try:
                win = webview.windows[0]
                w = CFG["window"]
                win.on_top = w.get("on_top", True)
                win.resize(w.get("width", 380), w.get("height", 600))
            except Exception:
                pass
            # Обновить трей при смене языка
            if CFG.get("language", "ru") != old_lang:
                TRAY.update_tooltip()
            return True
        except Exception as e:
            return str(e)

    def clear_history(self):
        try:
            HISTORY_STORE.clear()
            with STATE.lock:
                STATE.snapshot["insights"] = {
                    "enabled": bool((CFG.get("history") or {}).get("enabled", True)),
                    "analytics": {},
                    "alerts": [],
                    "snapshot_count": 0,
                }
            return {"success": True, "status": "history_cleared"}
        except Exception as exc:
            return {"success": False, "status": "history_clear_failed", "error": type(exc).__name__}

    def close(self):
        STATE.shutdown_event.set()
        try:
            win = webview.windows[0]
            try:
                CFG["window"]["x"], CFG["window"]["y"] = win.x, win.y
                save_config(CFG)
            except Exception:
                pass
            win.destroy()
        except Exception:
            os._exit(0)

    def minimize_to_tray(self):
        if TRAY_AVAILABLE and TRAY.window_ref and TRAY.ensure_available():
            TRAY.hide_window()
            return True
        return False

    def update_tray_icon(self):
        if TRAY_AVAILABLE and TRAY.window_ref:
            TRAY._update_icon_with_data()
            return True
        return False


def main():
    global webview
    try:
        import webview  # pywebview
    except ImportError:
        print("Не установлен pywebview. Выполни:  pip install pywebview")
        sys.exit(1)

    ui_smoke = os.environ.get("AI_CLI_CONTROL_CENTER_UI_SMOKE_TEST") == "1"
    if not ui_smoke:
        threading.Thread(target=refresh_loop, daemon=True).start()

    w = CFG["window"]
    window = webview.create_window(
        APP_NAME,
        url=os.path.join(APP_DIR, "ui.html"),
        js_api=JsApi(),
        width=w.get("width", 380),
        height=w.get("height", 600),
        x=w.get("x"),
        y=w.get("y"),
        frameless=True,
        easy_drag=False,
        on_top=w.get("on_top", True),
        resizable=True,
        background_color="#101012",
        hidden=ui_smoke,
    )
    # Устанавливаем иконку окна через ctypes
    icon_path = os.path.join(APP_DIR, "icon", "app.ico")
    if os.path.exists(icon_path):
        try:
            import ctypes
            from ctypes import wintypes
            ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("ai.usage.widget")
            hwnd = window.native
            if hwnd:
                icon = ctypes.windll.user32.LoadImageW(None, icon_path, 1, 0, 0, 0x00000010 | 0x00000020)
                if icon:
                    ctypes.windll.user32.SendMessageW(hwnd, 0x0080, 0, icon)  # WM_SETICON
        except Exception:
            pass
    if TRAY_AVAILABLE and not ui_smoke:
        TRAY.start(window)
    if ui_smoke:
        threading.Timer(3, window.destroy).start()
    webview.start(debug=False)
    STATE.shutdown_event.set()
    if TRAY.icon_app:
        TRAY.icon_app.stop()
    if TRAY.icon_claude:
        TRAY.icon_claude.stop()
    if TRAY.icon_codex:
        TRAY.icon_codex.stop()
    if not ui_smoke:
        try:
            CFG["window"]["x"], CFG["window"]["y"] = window.x, window.y
            save_config(CFG)
        except Exception:
            pass


if __name__ == "__main__":
    main()
