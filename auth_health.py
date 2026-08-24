# -*- coding: utf-8 -*-
"""Credential metadata inspection for provider-health.

Only non-secret metadata is returned. Access and refresh token values are never
included in health snapshots.
"""

import base64
import json
import os
import time
from datetime import datetime, timezone


def _to_epoch(value):
    if value is None:
        return None
    if isinstance(value, (int, float)):
        value = float(value)
        return value / 1000.0 if value > 4e10 else value
    if isinstance(value, str):
        text = value.strip()
        try:
            number = float(text)
            return number / 1000.0 if number > 4e10 else number
        except ValueError:
            pass
        try:
            if text.endswith("Z"):
                text = text[:-1] + "+00:00"
            dt = datetime.fromisoformat(text)
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            return dt.timestamp()
        except Exception:
            return None
    return None


def _jwt_claims(jwt):
    try:
        payload = jwt.split(".")[1]
        payload += "=" * (-len(payload) % 4)
        return json.loads(base64.urlsafe_b64decode(payload.encode("ascii")))
    except Exception:
        return {}


def _read_json(path):
    try:
        with open(path, "r", encoding="utf-8") as stream:
            return json.load(stream), None
    except Exception as exc:
        return None, f"{type(exc).__name__}: {exc}"


def _claude_credential_paths():
    home = os.path.expanduser("~")
    return [
        os.path.join(home, ".claude", ".credentials.json"),
        os.path.join(home, ".config", "claude", ".credentials.json"),
    ]


def _codex_auth_path():
    home = os.environ.get("CODEX_HOME") or os.path.join(os.path.expanduser("~"), ".codex")
    return os.path.join(home, "auth.json")


def _base_auth_result(provider_id):
    return {
        "provider_id": provider_id,
        "state": "unknown",
        "credential_path": None,
        "access_present": False,
        "refresh_present": False,
        "access_expires_at": None,
        "refresh_expires_at": None,
        "metadata_complete": False,
        "reason": None,
        "error": None,
    }


def inspect_claude_auth(now=None):
    now = time.time() if now is None else float(now)
    result = _base_auth_result("claude")

    path = next((p for p in _claude_credential_paths() if os.path.isfile(p)), None)
    if not path:
        result["state"] = "missing_credentials"
        result["reason"] = "credential_file_missing"
        return result

    result["credential_path"] = path
    data, error = _read_json(path)
    if error:
        result["state"] = "credentials_broken"
        result["reason"] = "credential_file_unreadable"
        result["error"] = error
        return result

    oauth = data.get("claudeAiOauth") or data.get("oauth")
    if not isinstance(oauth, dict):
        result["state"] = "missing_credentials"
        result["reason"] = "oauth_record_missing"
        return result

    access = oauth.get("accessToken") or oauth.get("access_token")
    refresh = oauth.get("refreshToken") or oauth.get("refresh_token")
    access_exp = _to_epoch(oauth.get("expiresAt") or oauth.get("expires_at"))
    refresh_exp = _to_epoch(
        oauth.get("refreshTokenExpiresAt")
        or oauth.get("refresh_token_expires_at")
    )

    result.update({
        "access_present": bool(access),
        "refresh_present": bool(refresh),
        "access_expires_at": access_exp,
        "refresh_expires_at": refresh_exp,
        "metadata_complete": bool(access and access_exp),
    })

    if not access:
        if refresh and (refresh_exp is None or refresh_exp > now):
            result["state"] = "access_missing_refreshable"
            result["reason"] = "access_token_missing_refresh_present"
        else:
            result["state"] = "login_required"
            result["reason"] = "usable_tokens_missing"
        return result

    if access_exp is None:
        result["state"] = "session_present_metadata_incomplete"
        result["reason"] = "access_expiry_missing"
        return result

    remaining = access_exp - now
    if remaining > 3600:
        result["state"] = "valid"
        return result
    if remaining > 0:
        result["state"] = "expiring"
        return result

    if refresh and (refresh_exp is None or refresh_exp > now):
        result["state"] = "access_expired_refreshable"
        result["reason"] = "access_expired_refresh_available"
    else:
        result["state"] = "login_required"
        result["reason"] = (
            "refresh_expired" if refresh_exp is not None and refresh_exp <= now
            else "refresh_token_missing"
        )
    return result


def inspect_codex_auth(now=None):
    now = time.time() if now is None else float(now)
    result = _base_auth_result("codex")
    path = _codex_auth_path()

    if not os.path.isfile(path):
        result["state"] = "missing_credentials"
        result["reason"] = "credential_file_missing"
        return result

    result["credential_path"] = path
    auth, error = _read_json(path)
    if error:
        result["state"] = "credentials_broken"
        result["reason"] = "credential_file_unreadable"
        result["error"] = error
        return result

    tokens = auth.get("tokens") or {}
    access = tokens.get("access_token") or auth.get("access_token")
    refresh = tokens.get("refresh_token") or auth.get("refresh_token")
    claims = _jwt_claims(access) if access else {}
    access_exp = _to_epoch(claims.get("exp"))

    result.update({
        "access_present": bool(access),
        "refresh_present": bool(refresh),
        "access_expires_at": access_exp,
        "metadata_complete": bool(access and access_exp),
    })

    if not access:
        if refresh:
            result["state"] = "access_missing_refreshable"
            result["reason"] = "access_token_missing_refresh_present"
        else:
            result["state"] = "login_required"
            result["reason"] = "usable_tokens_missing"
        return result

    if access_exp is None:
        result["state"] = "session_present_metadata_incomplete"
        result["reason"] = "access_expiry_missing"
        return result

    remaining = access_exp - now
    if remaining > 3600:
        result["state"] = "valid"
    elif remaining > 0:
        result["state"] = "expiring"
    elif refresh:
        result["state"] = "access_expired_refreshable"
        result["reason"] = "access_expired_refresh_available"
    else:
        result["state"] = "login_required"
        result["reason"] = "refresh_token_missing"
    return result


def inspect_all_auth(now=None):
    return {
        "claude": inspect_claude_auth(now=now),
        "codex": inspect_codex_auth(now=now),
    }


def recommended_actions(cli_health, auth_health, usage_health=None):
    cli_state = (cli_health or {}).get("state")
    auth_state = (auth_health or {}).get("state")
    usage_state = (usage_health or {}).get("state")

    if cli_state == "missing":
        return [{"id": "install", "reason": "cli_missing", "kind": "primary",
                 "label_key": "install_cli"}]
    if cli_state == "broken":
        return [{"id": "diagnostics", "reason": "cli_probe_failed", "kind": "primary",
                 "label_key": "show_diagnostics"}]

    if auth_state in ("missing_credentials", "login_required"):
        return [{"id": "login", "reason": auth_state, "kind": "primary",
                 "label_key": "sign_in"}]
    if auth_state in (
        "access_missing_refreshable",
        "access_expired_refreshable",
        "session_present_metadata_incomplete",
    ):
        return [
            {"id": "refresh_session", "reason": auth_state, "kind": "primary",
             "label_key": "refresh_session"},
            {"id": "login", "reason": "refresh_fallback", "kind": "secondary",
             "label_key": "sign_in_again"},
        ]
    if auth_state == "credentials_broken":
        return [{"id": "login", "reason": auth_state, "kind": "primary",
                 "label_key": "sign_in_again"}]
    if auth_state not in ("valid", "expiring"):
        return [{"id": "retry", "reason": auth_state or "unknown", "kind": "primary",
                 "label_key": "retry"}]

    if usage_state in ("network_error", "server_error", "unsupported_response", "unknown_error"):
        return [{"id": "retry", "reason": usage_state, "kind": "primary",
                 "label_key": "retry"}]
    return []


def recommended_action(cli_health, auth_health, usage_health=None):
    actions = recommended_actions(cli_health, auth_health, usage_health)
    return actions[0] if actions else None
