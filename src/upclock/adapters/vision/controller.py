"""视觉探测控制器，根据键鼠状态按需触发摄像头采样。"""

from __future__ import annotations

import asyncio
import logging
from typing import Optional

import contextlib

from upclock.adapters.vision.base import VisionAdapter

logger = logging.getLogger(__name__)


class VisionController:
    """根据活动状态动态触发视觉探测，避免长时间占用摄像头。"""

    def __init__(
        self,
        adapter: Optional[VisionAdapter],
        ambiguous_seconds: float = 60.0,
        break_reset_seconds: float = 180.0,
        probe_duration: float = 3.0,
        probe_interval: float = 0.5,
        cooldown_seconds: float = 90.0,
        confidence_hold: float = 0.6,
    ) -> None:
        self._adapter = adapter
        self._ambiguous_seconds = ambiguous_seconds
        self._break_reset_seconds = break_reset_seconds
        self._probe_duration = probe_duration
        self._probe_interval = probe_interval
        self._cooldown_seconds = cooldown_seconds
        self._last_probe_at = 0.0
        self._task: Optional[asyncio.Task[None]] = None
        self._confidence_hold = confidence_hold

    def update(
        self,
        break_minutes: float,
        presence_confidence: float,
        posture_state: str,
        now: float,
    ) -> None:
        if self._adapter is None:
            return

        break_seconds = break_minutes * 60.0
        if break_seconds < self._ambiguous_seconds:
            return
        if break_seconds >= self._break_reset_seconds:
            return

        if presence_confidence >= self._confidence_hold and posture_state != "untracked":
            return

        if (now - self._last_probe_at) < self._cooldown_seconds:
            return

        if self._task is not None and not self._task.done():
            return

        self._last_probe_at = now
        self._task = asyncio.create_task(self._run_probe())

    async def _run_probe(self) -> None:
        assert self._adapter is not None
        try:
            await self._adapter.probe(
                duration=self._probe_duration,
                interval=self._probe_interval,
            )
        except Exception as exc:  # pragma: no cover - 硬件相关异常
            logger.warning("视觉探测失败: %s", exc, exc_info=True)

    async def aclose(self) -> None:
        if self._task is not None and not self._task.done():
            self._task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._task
            self._task = None
