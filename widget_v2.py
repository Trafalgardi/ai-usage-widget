"""Backward-compatible v2 entry point.

New integrations may import :mod:`application`; existing shortcuts and packaged
builds can continue launching ``widget_v2.py``.
"""

from application import main
from ui_bridge import ControlCenterApi, V2JsApi

__all__ = ["ControlCenterApi", "V2JsApi", "main"]


if __name__ == "__main__":
    main()
