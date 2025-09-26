"""简易配置存储，支持加载/保存用户自定义设置。"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from upclock.config import AppConfig


DEFAULT_CONFIG_PATH = Path.home() / ".upclock" / "config.json"


@dataclass
class UserSettings:
    prolonged_seated_minutes: int
    notification_cooldown_minutes: int
    quiet_hours: list[tuple[str, str]]

    @classmethod
    def from_config(cls, config: AppConfig) -> "UserSettings":
        quiet_hours = [tuple(slot) for slot in config.quiet_hours]
        return cls(
            prolonged_seated_minutes=config.prolonged_seated_minutes,
            notification_cooldown_minutes=config.notification_cooldown_minutes,
            quiet_hours=quiet_hours,
        )

    def to_dict(self) -> dict:
        return {
            "prolonged_seated_minutes": self.prolonged_seated_minutes,
            "notification_cooldown_minutes": self.notification_cooldown_minutes,
            "quiet_hours": [list(slot) for slot in self.quiet_hours],
        }


def load_user_settings(path: Optional[Path] = None) -> Optional[UserSettings]:
    cfg_path = path or DEFAULT_CONFIG_PATH
    try:
        if not cfg_path.exists():
            return None
        data = json.loads(cfg_path.read_text(encoding="utf-8"))
        return UserSettings(
            prolonged_seated_minutes=int(data.get("prolonged_seated_minutes", 45)),
            notification_cooldown_minutes=int(data.get("notification_cooldown_minutes", 30)),
            quiet_hours=[tuple(slot) for slot in data.get("quiet_hours", [])],
        )
    except Exception:
        return None


def save_user_settings(settings: UserSettings, path: Optional[Path] = None) -> None:
    cfg_path = path or DEFAULT_CONFIG_PATH
    cfg_path.parent.mkdir(parents=True, exist_ok=True)
    cfg_path.write_text(json.dumps(settings.to_dict(), ensure_ascii=False, indent=2), encoding="utf-8")
