# -*- coding: utf-8 -*-
"""Structured usage health and in-memory last-known-good snapshots."""

import copy
import json
import socket
import threading
import time
import urllib.error


def usage_error(error_kind, message, http_status=None, retry_after=None):
    state_by_kind = {
        "auth": "auth_error",
        "rate_limit": "rate_limited",
        "network": "network_error",
        "server": "server_error",
        "format": "unsupported_response",
        "unknown": "unknown_error",
    }
    return {
        "state": state_by_kind.get(error_kind, "unknown_error"),
        "last_success_at": None,
        "http_status": http_status,
        "error_kind": error_kind,
        "error": message,
        "retry_after": retry_after,
        "stale": False,
    }


def classify_http_error(error):
    status = getattr(error, "code", None)
    if status in (401, 403):
        kind = "auth"
    elif status == 429:
        kind = "rate_limit"
    elif status is not None and 500 <= status <= 599:
        kind = "server"
    else:
        kind = "unknown"
    retry_after = None
    headers = getattr(error, "headers", None)
    if headers is not None:
        retry_after = headers.get("Retry-After")
    return usage_error(kind, f"HTTP {status}", status, retry_after)


def classify_exception(error):
    if isinstance(error, urllib.error.HTTPError):
        return classify_http_error(error)
    if isinstance(error, json.JSONDecodeError):
        return usage_error("format", "Response was not valid JSON")
    if isinstance(error, (urllib.error.URLError, TimeoutError, socket.timeout)):
        return usage_error("network", f"{type(error).__name__}: {error}")
    return usage_error("unknown", f"{type(error).__name__}: {error}")


class LastGoodUsageStore:
    """Decorate provider results while retaining only non-secret usage data."""

    def __init__(self):
        self._lock = threading.Lock()
        self._snapshots = {}

    def apply(self, provider, now=None):
        now = time.time() if now is None else float(now)
        current = copy.deepcopy(provider)
        provider_id = current.get("id")
        successful = bool(current.get("ok") and current.get("windows"))

        with self._lock:
            if successful:
                usage = {
                    "state": "available",
                    "last_success_at": now,
                    "http_status": 200,
                    "error_kind": None,
                    "error": None,
                    "retry_after": None,
                    "stale": False,
                }
                current["usage"] = usage
                if provider_id:
                    self._snapshots[provider_id] = {
                        "windows": copy.deepcopy(current.get("windows") or []),
                        "meta": copy.deepcopy(current.get("meta") or {}),
                        "last_success_at": now,
                    }
                return current

            usage = copy.deepcopy(current.get("usage") or usage_error(
                "unknown", current.get("error") or "Usage unavailable"
            ))
            cached = self._snapshots.get(provider_id)
            if cached:
                current["windows"] = copy.deepcopy(cached["windows"])
                merged_meta = copy.deepcopy(cached["meta"])
                merged_meta.update(current.get("meta") or {})
                current["meta"] = merged_meta
                usage["last_success_at"] = cached["last_success_at"]
                usage["stale"] = True
            current["usage"] = usage
            return current
