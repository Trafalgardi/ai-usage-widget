# -*- coding: utf-8 -*-
"""Normalized v2 provider-health snapshot aggregation."""

from auth_health import inspect_all_auth, recommended_action, recommended_actions
from provider_health import discover_all
from provider_registry import PROVIDERS


HEALTH_SCHEMA_VERSION = 2


def collect_provider_health(now=None):
    cli_by_provider = discover_all()
    auth_by_provider = inspect_all_auth(now=now)

    providers = {}
    for provider_id in PROVIDERS:
        cli = cli_by_provider.get(provider_id) or {"state": "unknown"}
        auth = auth_by_provider.get(provider_id) or {"state": "unknown"}
        actions = recommended_actions(cli, auth)
        providers[provider_id] = {
            "cli": cli,
            "auth": auth,
            "usage": {"state": "unknown", "stale": False, "last_success_at": None},
            "actions": actions,
            "recommended_action": recommended_action(cli, auth),
        }

    return {
        "schema_version": HEALTH_SCHEMA_VERSION,
        "providers": providers,
    }
