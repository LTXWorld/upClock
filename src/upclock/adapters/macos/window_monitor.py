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

        rule = self._match_rule(bundle_id, app_name)
        self._last_info = {
            "bundle_id": bundle_id,
            "app_name": app_name,
            "category": rule.name,
            "weight": rule.weight,
        }

        metrics = {
            "window_weight": float(rule.weight),
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
