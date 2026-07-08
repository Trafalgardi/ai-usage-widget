# -*- coding: utf-8 -*-
"""
AI Usage Widget — виджет остатков лимитов для Claude Code, Codex CLI и OpenCode.

Читает локальные файлы авторизации каждого CLI и опрашивает их usage-эндпоинты:
  * Claude Code : ~/.claude/.credentials.json  -> api.anthropic.com/api/oauth/usage
  * Codex CLI   : ~/.codex/auth.json           -> chatgpt.com/backend-api/wham/usage
  * OpenCode    : ~/.local/share/opencode/auth.json -> opencode.ai (best effort)

Запуск:  python widget.py
Зависимости:  pip install pywebview
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

try:
    import pystray
    from PIL import Image, ImageDraw, ImageFont
    TRAY_AVAILABLE = True
except ImportError:
    TRAY_AVAILABLE = False

APP_DIR = os.path.dirname(os.path.abspath(__file__))
HOME = os.path.expanduser("~")
CONFIG_PATH = os.path.join(APP_DIR, "config.json")

DEFAULT_CONFIG = {
    "refresh_interval_sec": 60,
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


# ----------------------------------------------------------------------------
# helpers
# ----------------------------------------------------------------------------

def load_config():
    cfg = json.loads(json.dumps(DEFAULT_CONFIG))
    try:
        if os.path.exists(CONFIG_PATH):
            with open(CONFIG_PATH, "r", encoding="utf-8") as f:
                user = json.load(f)
            for k, v in user.items():
                if isinstance(v, dict) and isinstance(cfg.get(k), dict):
                    cfg[k].update(v)
                else:
                    cfg[k] = v
    except Exception:
        pass
    return cfg


def save_config(cfg):
    try:
        with open(CONFIG_PATH, "w", encoding="utf-8") as f:
            json.dump(cfg, f, indent=2, ensure_ascii=False)
    except Exception:
        pass


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


def fetch_claude():
    result = {"id": "claude", "name": "Claude Code", "ok": False,
              "windows": [], "meta": {}, "error": None}
    token = None
    cred_file = None
    for p in CLAUDE_CRED_PATHS:
        if os.path.exists(p):
            cred_file = p
            try:
                with open(p, "r", encoding="utf-8") as f:
                    data = json.load(f)
                oauth = data.get("claudeAiOauth") or data.get("oauth") or {}
                token = oauth.get("accessToken") or oauth.get("access_token")
                result["meta"]["subscription"] = oauth.get("subscriptionType")
                exp = oauth.get("expiresAt")
                if exp and iso_to_epoch(exp) and iso_to_epoch(exp) < time.time():
                    result["meta"]["token_stale"] = True
            except Exception as e:
                result["error"] = f"Не удалось прочитать {p}: {e}"
            break
    if not token:
        result["error"] = result["error"] or (
            "Не найден токен Claude Code (~/.claude/.credentials.json). "
            "Открой Claude Code и выполни /login.")
        return result

    headers = {
        "Authorization": f"Bearer {token}",
        "anthropic-beta": "oauth-2025-04-20",
        "Content-Type": "application/json",
        "Accept": "application/json",
        "User-Agent": "ai-usage-widget/1.0",
    }
    data, last_err = None, None
    for url in CLAUDE_USAGE_URLS:
        try:
            data = http_get_json(url, headers)
            break
        except urllib.error.HTTPError as e:
            last_err = f"HTTP {e.code} от {url}"
            if e.code in (401, 403):
                last_err += " — токен истёк, зайди в Claude Code (/login)"
        except Exception as e:
            last_err = f"{type(e).__name__}: {e}"
    if data is None:
        result["error"] = last_err or "Нет ответа от API"
        return result

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

    # extra usage / кредиты, если сервер их отдаёт
    extra = data.get("extra_usage") or data.get("extraUsage")
    if isinstance(extra, dict):
        result["meta"]["extra_usage"] = extra

    if result["windows"]:
        result["ok"] = True
    else:
        result["error"] = "API ответил, но формат не распознан"
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
            msg += " — токен истёк. Запусти Codex (он обновит токен) или `codex login`."
        result["error"] = msg
        return result
    except Exception as e:
        result["error"] = f"{type(e).__name__}: {e}"
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
            if p and p.get("ok"):
                w = next((x for x in p.get("windows", []) if x["id"] == "session"), None)
                if w and w.get("remaining_pct") is not None:
                    result[pid] = round(w["remaining_pct"], 1)
        return result

    def _update_icon_with_data(self):
        pcts = self._get_session_pcts()
        claude_pct = pcts.get("claude")
        codex_pct = pcts.get("codex")
        claude_text = f"{int(claude_pct):02d}" if claude_pct is not None else "--"
        codex_text = f"{int(codex_pct):02d}" if codex_pct is not None else "--"
        try:
            if self.icon_claude:
                img_claude = self._create_icon_image(claude_text, color="#D97757")
                self.icon_claude.icon = img_claude
            if self.icon_codex:
                img_codex = self._create_icon_image(codex_text, color="#2ECC40", outline="#1a7a25")
                self.icon_codex.icon = img_codex
        except Exception as e:
            print(f"Tray: icon update error: {e}")

    def _build_tooltip(self):
        with STATE.lock:
            snap = copy.deepcopy(STATE.snapshot)
        if not snap.get("updated_at"):
            return "AI Usage Widget"
        lines = ["AI Usage Widget"]
        for pid, pname in [("claude", "Claude"), ("codex", "Codex")]:
            p = snap["providers"].get(pid)
            if not p or not p.get("ok"):
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
                reset_str = f"{h}ч {m}м" if h > 0 else f"{m}м"
                lines.append(f"{pname}: {pct}% (сброс {reset_str})")
            else:
                lines.append(f"{pname}: {pct}%")
        return "\n".join(lines)

    def _on_show(self, icon, item):
        if self.window_ref:
            self.window_ref.show()

    def _on_quit(self, icon, item):
        STATE.shutdown_event.set()
        if self.icon_claude:
            self.icon_claude.stop()
        if self.icon_codex:
            self.icon_codex.stop()

    def _on_refresh(self, icon, item):
        threading.Thread(target=refresh_all, daemon=True).start()

    def start(self, window):
        if not TRAY_AVAILABLE:
            return
        self.window_ref = window
        menu = pystray.Menu(
            pystray.MenuItem("Показать", self._on_show, default=True),
            pystray.MenuItem("Обновить", self._on_refresh),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem("Выход", self._on_quit),
        )
        img_claude = self._create_icon_image("--", color="#D97757")
        img_codex = self._create_icon_image("--", color="#2ECC40", outline="#1a7a25")
        self.icon_claude = pystray.Icon("ai-usage-claude", img_claude, "Claude Code", menu)
        self.icon_codex = pystray.Icon("ai-usage-codex", img_codex, "Codex CLI", menu)
        self._thread_claude = threading.Thread(target=self.icon_claude.run, daemon=True)
        self._thread_codex = threading.Thread(target=self.icon_codex.run, daemon=True)
        self._thread_claude.start()
        self._thread_codex.start()

    def update_tooltip(self):
        tooltip = self._build_tooltip()
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


TRAY = TrayManager()


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
                    providers[name] = future.result()
                except Exception:
                    providers[name] = {"id": name, "name": name, "ok": False,
                                       "windows": [], "meta": {},
                                       "error": "Внутренняя ошибка:\n" + traceback.format_exc(limit=2)}
        with STATE.lock:
            STATE.snapshot = {"updated_at": time.time(), "providers": providers}
        TRAY.update_tooltip()
        TRAY._update_icon_with_data()
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
        return snap

    def refresh_now(self):
        if STATE.refresh_lock.locked():
            return False
        threading.Thread(target=refresh_all, daemon=True).start()
        return True

    def login_claude(self):
        try:
            startupinfo = subprocess.STARTUPINFO()
            startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
            startupinfo.wShowWindow = 0  # SW_HIDE
            
            result = subprocess.run(
                ["claude", "login"],
                capture_output=True,
                text=True,
                timeout=120,
                encoding='utf-8',
                errors='replace',
                startupinfo=startupinfo,
                creationflags=subprocess.CREATE_NO_WINDOW
            )
            output = result.stdout + result.stderr
            return {"success": result.returncode == 0, "output": output}
        except FileNotFoundError:
            return {"success": False, "output": "Claude CLI не найден. Установи: npm install -g @anthropic-ai/claude-code"}
        except subprocess.TimeoutExpired:
            return {"success": False, "output": "Превышено время ожидания (120 сек)"}
        except Exception as e:
            return {"success": False, "output": f"Ошибка: {str(e)}"}

    def login_codex(self):
        try:
            startupinfo = subprocess.STARTUPINFO()
            startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
            startupinfo.wShowWindow = 0  # SW_HIDE
            
            result = subprocess.run(
                ["codex", "login"],
                capture_output=True,
                text=True,
                timeout=120,
                encoding='utf-8',
                errors='replace',
                startupinfo=startupinfo,
                creationflags=subprocess.CREATE_NO_WINDOW
            )
            output = result.stdout + result.stderr
            return {"success": result.returncode == 0, "output": output}
        except FileNotFoundError:
            return {"success": False, "output": "Codex CLI не найден. Установи: npm install -g @openai/codex"}
        except subprocess.TimeoutExpired:
            return {"success": False, "output": "Превышено время ожидания (120 сек)"}
        except Exception as e:
            return {"success": False, "output": f"Ошибка: {str(e)}"}

    def toggle_on_top(self):
        try:
            win = webview.windows[0]
            new_val = not CFG["window"].get("on_top", True)
            win.on_top = new_val
            CFG["window"]["on_top"] = new_val
            save_config(CFG)
            return new_val
        except Exception:
            return None

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
        if TRAY_AVAILABLE and (TRAY.icon_claude or TRAY.icon_codex):
            TRAY.hide_window()
            return True
        return False

    def update_tray_icon(self):
        if TRAY_AVAILABLE and (TRAY.icon_claude or TRAY.icon_codex):
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

    threading.Thread(target=refresh_loop, daemon=True).start()

    w = CFG["window"]
    window = webview.create_window(
        "AI Usage",
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
    )
    if TRAY_AVAILABLE:
        TRAY.start(window)
    webview.start(debug=False)
    STATE.shutdown_event.set()
    if TRAY.icon_claude:
        TRAY.icon_claude.stop()
    if TRAY.icon_codex:
        TRAY.icon_codex.stop()
    try:
        CFG["window"]["x"], CFG["window"]["y"] = window.x, window.y
        save_config(CFG)
    except Exception:
        pass


if __name__ == "__main__":
    main()
