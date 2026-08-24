# -*- coding: utf-8 -*-
"""Consistent, UI-safe errors that avoid leaking credentials and home paths."""

import os
import re
from dataclasses import dataclass, asdict
from enum import Enum
from typing import Optional


class ErrorKind(str, Enum):
    AUTH = "auth"
    NETWORK = "network"
    FORMAT = "format"
    PROCESS = "process"
    TIMEOUT = "timeout"
    UNSUPPORTED = "unsupported"
    INTERNAL = "internal"


_SECRET_PATTERNS = (
    re.compile(r"(?i)(bearer\s+)[^\s\"']+"),
    re.compile(r'(?i)([\"\']?(?:access|refresh)?_?token[\"\']?\s*[:=]\s*[\"\']?)[^\s,}\"\']+'),
)


def redact_text(value, limit=1000):
    text = str(value or "")
    home = os.path.expanduser("~")
    if home and home != "~":
        text = text.replace(home, "~").replace(home.replace("\\", "/"), "~")
    for pattern in _SECRET_PATTERNS:
        text = pattern.sub(r"\1[redacted]", text)
    return text[-limit:]


@dataclass(frozen=True)
class AppError:
    code: str
    kind: ErrorKind
    message: str
    retryable: bool = False
    http_status: Optional[int] = None

    def to_dict(self):
        result = asdict(self)
        result["kind"] = self.kind.value
        result["message"] = redact_text(self.message)
        return result


def exception_error(code, kind, exc, retryable=False):
    return AppError(
        code=code,
        kind=kind,
        message=f"{type(exc).__name__}: {redact_text(exc)}",
        retryable=retryable,
    ).to_dict()
