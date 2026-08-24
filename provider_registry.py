# -*- coding: utf-8 -*-
"""Single source of truth for supported providers and lifecycle actions."""

from dataclasses import dataclass
from enum import Enum
from typing import Mapping, Tuple


class ProviderId(str, Enum):
    CLAUDE = "claude"
    CODEX = "codex"


class ActionId(str, Enum):
    INSTALL = "install"
    REFRESH_SESSION = "refresh_session"
    LOGIN = "login"
    RETRY = "retry"
    DIAGNOSTICS = "diagnostics"


@dataclass(frozen=True)
class ProviderSpec:
    id: ProviderId
    label: str
    command: str
    login_args: Tuple[str, ...]
    installer_script: str
    installer_method: str
    supports_session_refresh: bool = False


PROVIDERS: Mapping[str, ProviderSpec] = {
    ProviderId.CLAUDE.value: ProviderSpec(
        id=ProviderId.CLAUDE,
        label="Claude Code",
        command="claude",
        login_args=("auth", "login"),
        installer_script="irm https://claude.ai/install.ps1 | iex",
        installer_method="official_native",
        supports_session_refresh=True,
    ),
    ProviderId.CODEX.value: ProviderSpec(
        id=ProviderId.CODEX,
        label="Codex CLI",
        command="codex",
        login_args=("login",),
        installer_script="irm https://chatgpt.com/codex/install.ps1 | iex",
        installer_method="official_standalone",
    ),
}


def get_provider(provider_id: str) -> ProviderSpec:
    try:
        return PROVIDERS[provider_id]
    except KeyError as exc:
        raise ValueError(f"Unsupported provider: {provider_id}") from exc
