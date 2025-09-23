"""macOS 平台适配器占位。"""

from .input_monitor import MacOSInputMonitor
from .window_monitor import MacOSWindowMonitor

__all__ = [
    "MacOSInputMonitor",
    "MacOSWindowMonitor",
]
