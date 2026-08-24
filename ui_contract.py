# -*- coding: utf-8 -*-
"""Versioned and typed Python-to-JavaScript contract helpers."""

import copy
from dataclasses import asdict, dataclass, field
from typing import Any, Dict, List, Optional

from error_model import redact_text


UI_CONTRACT_VERSION = 1


@dataclass(frozen=True)
class ActionDescriptor:
    id: str
    reason: str
    kind: str = "primary"
    label_key: str = ""


@dataclass
class ActionResult:
    success: bool
    status: str
    provider_id: Optional[str] = None
    message: Optional[str] = None
    provider_health: Optional[Dict[str, Any]] = None
    error: Optional[Dict[str, Any]] = None
    details: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self):
        value = asdict(self)
        value["contract_version"] = UI_CONTRACT_VERSION
        if value.get("message"):
            value["message"] = redact_text(value["message"])
        return {key: item for key, item in value.items() if item not in (None, {}, [])}


def serialize_snapshot(snapshot):
    """Return a detached JSON-safe snapshot with an explicit contract version."""
    value = copy.deepcopy(snapshot)
    value["contract_version"] = UI_CONTRACT_VERSION
    value.setdefault("providers", {})
    value.setdefault("provider_health", {"schema_version": 2, "providers": {}})
    return value


def action_result(value, provider_health=None):
    """Normalize legacy action dictionaries at the UI boundary."""
    details = copy.deepcopy(value or {})
    success = bool(details.pop("success", False))
    status = str(details.pop("status", "unknown"))
    provider_id = details.pop("provider_id", None)
    error = details.pop("error", None)
    message = details.pop("message", None)
    if isinstance(error, str):
        message = message or redact_text(error)
        error = {"code": status, "kind": "process", "message": redact_text(error)}
    return ActionResult(
        success=success,
        status=status,
        provider_id=provider_id,
        message=message,
        provider_health=copy.deepcopy(provider_health),
        error=error,
        details=details,
    ).to_dict()
