"""macOS 活跃窗口监测实现。"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from typing import Iterable, List, Optional

try:  # pragma: no cover - 平台判定
    import AppKit
except ImportError:  # pragma: no cover - 非 macOS 环境
    AppKit = None  # type: ignore

try:  # pragma: no cover - 平台判定
    import Quartz
except ImportError:  # pragma: no cover - 非 macOS 环境
    Quartz = None  # type: ignore

from upclock.adapters.base import InputAdapter
from upclock.config import WindowCategory

logger = logging.getLogger(__name__)


@dataclass
class CategoryRule:
    """窗口分类匹配规则。"""

    name: str
    weight: float
    patterns: List[str]

    @classmethod
    def from_category(cls, category: WindowCategory) -> "CategoryRule":
        return cls(name=category.name, weight=category.weight, patterns=list(category.patterns))


_DEFAULT_RULES: List[CategoryRule] = [
    CategoryRule(name="work", weight=1.0, patterns=["code", "terminal", "xcode", "notion", "google docs"]),
    CategoryRule(name="meeting", weight=0.9, patterns=["zoom", "meet", "teams"]),
    CategoryRule(name="leisure", weight=0.3, patterns=["music", "netflix", "youtube", "game"]),
]
_NEUTRAL_RULE = CategoryRule(name="neutral", weight=0.6, patterns=[])

_MEETING_KEYWORDS = [
    "zoom",
    "meeting",
    "tencent",
    "kmeeting",
    "feishu",
    "飞书",
    "dingtalk",
    "钉钉",
    "teams",
    "webex",
    "gotomeeting",
    "gongzuo",
]

_MEETING_BUNDLE_HINTS = [
    "us.zoom.xos",
    "com.tencent.meeting",
    "com.tencent.kmeeting",
    "com.bytedance.feishu",
    "com.microsoft.teams",
    "com.microsoft.teams2",
    "com.alibaba.dingtalk",
    "com.cisco.webexmeetings",
]


class MacOSWindowMonitor(InputAdapter):
    """轮询活跃程序并转换为窗口类别指标。"""

    def __init__(
        self,
        buffer,
        poll_interval: float = 5.0,
        categories: Optional[Iterable[WindowCategory]] = None,
    ) -> None:
        super().__init__(buffer)
        self._poll_interval = poll_interval
        self._task: Optional[asyncio.Task[None]] = None
        self._rules: List[CategoryRule] = (
            [CategoryRule.from_category(cat) for cat in categories]
            if categories
            else list(_DEFAULT_RULES)
        )
        self._last_info: dict[str, str | float] = {}

    async def start(self) -> None:
        if self._task is not None:
            return
        if AppKit is None:
            logger.error("当前环境缺少 AppKit，无法启动窗口监控")
            return

        async def _loop() -> None:
            while True:
                metrics = self._collect_metrics()
                if metrics:
                    self.publish(metrics)
                await asyncio.sleep(self._poll_interval)

        self._task = asyncio.create_task(_loop())

    def stop(self) -> None:
        if self._task is not None:
            self._task.cancel()
            self._task = None

    def latest_info(self) -> dict[str, str | float]:
        """返回最近一次采集的窗口信息。"""

        return dict(self._last_info)

    def _collect_metrics(self) -> Optional[dict[str, float]]:
        if AppKit is None:
            return None

        app = AppKit.NSWorkspace.sharedWorkspace().frontmostApplication()
        if app is None:
            logger.debug("未能获取前台应用")
            return None

        bundle_id = app.bundleIdentifier() or ""
        app_name = app.localizedName() or bundle_id or "unknown"

        is_full_screen = self._detect_full_screen(app_name)
        is_meeting = self._is_meeting_app(bundle_id, app_name)

        rule = self._match_rule(bundle_id, app_name)
        self._last_info = {
            "bundle_id": bundle_id,
            "app_name": app_name,
            "category": rule.name,
            "weight": rule.weight,
            "is_full_screen": is_full_screen,
            "is_meeting_app": is_meeting,
        }

        metrics = {
            "window_weight": float(rule.weight),
            "window_fullscreen": 1.0 if is_full_screen else 0.0,
            "window_meeting": 1.0 if is_meeting else 0.0,
            "window_app_name": app_name,
            "window_app_bundle": bundle_id,
        }
        return metrics

    def _match_rule(self, bundle_id: str, app_name: str) -> CategoryRule:
        target_values = [bundle_id.lower(), app_name.lower()]
        for rule in self._rules:
            for pattern in rule.patterns:
                pattern_lower = pattern.lower()
                if not pattern_lower:
                    continue
                if any(pattern_lower in value for value in target_values):
                    return rule
        return _NEUTRAL_RULE

    def _is_meeting_app(self, bundle_id: str, app_name: str) -> bool:
        bundle_lower = (bundle_id or "").lower()
        name_lower = (app_name or "").lower()
        if any(hint in bundle_lower for hint in _MEETING_BUNDLE_HINTS):
            return True
        return any(keyword in name_lower for keyword in _MEETING_KEYWORDS)

    def _detect_full_screen(self, app_name: str) -> bool:
        if AppKit is None or Quartz is None:
            return False

        try:
            screens = AppKit.NSScreen.screens()
        except Exception:  # pragma: no cover - 访问屏幕信息失败
            return False
        if not screens:
            return False

        try:
            window_list = Quartz.CGWindowListCopyWindowInfo(
                Quartz.kCGWindowListOptionOnScreenOnly | Quartz.kCGWindowListOptionOnScreenAboveWindow,
                Quartz.kCGNullWindowID,
            )
        except Exception:  # pragma: no cover - 访问窗口信息失败
            return False

        if not window_list:
            return False

        primary_frames = []
        try:
            for screen in screens:  # type: ignore[assignment]
                frame = screen.frame()
                primary_frames.append((frame.size.width, frame.size.height))
        except Exception:
            primary_frames = []

        app_name_lower = (app_name or "").lower()
        tolerance = 8.0

        for window in window_list:
            owner_name = (window.get("kCGWindowOwnerName") or "").lower()
            if owner_name != app_name_lower:
                continue
            bounds = window.get("kCGWindowBounds") or {}
            width = float(bounds.get("Width", 0.0))
            height = float(bounds.get("Height", 0.0))
            if width <= 0 or height <= 0:
                continue
            for frame_width, frame_height in primary_frames:
                if (
                    abs(width - frame_width) <= tolerance
                    and abs(height - frame_height) <= tolerance
                ):
                    return True
        return False
