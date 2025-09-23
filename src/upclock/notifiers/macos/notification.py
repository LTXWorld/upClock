"""rumps 封装的 macOS 通知适配器。"""

from __future__ import annotations

from dataclasses import dataclass

import rumps


@dataclass
class NotificationPayload:
    title: str
    subtitle: str
    informative_text: str


class MacOSNotifier:
    """封装 rumps.notification，便于未来扩展。"""

    def send(self, payload: NotificationPayload) -> None:
        rumps.notification(payload.title, payload.subtitle, payload.informative_text)
