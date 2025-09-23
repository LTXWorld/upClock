"""摄像头在位检测适配器接口。"""

from __future__ import annotations

import abc
import asyncio
import datetime as dt
from dataclasses import dataclass
from typing import Optional

from upclock.adapters.base import InputAdapter


@dataclass
class PresenceSnapshot:
    """单帧检测结果。"""

    timestamp: dt.datetime
    presence: bool
    confidence: float
    posture_score: float
    posture_state: str = "unknown"


class VisionAdapter(InputAdapter, abc.ABC):
    """摄像头在位检测适配器抽象类。"""

    def __init__(self, buffer, capture_interval: float = 10.0) -> None:
        super().__init__(buffer)
        self._capture_interval = capture_interval
        self._task: Optional[asyncio.Task[None]] = None

    async def start(self) -> None:
        if self._task is not None:
            return

        async def _loop() -> None:
            while True:
                snapshot = await self.capture()
                if snapshot is not None:
                    self._publish(snapshot)
                await asyncio.sleep(self._capture_interval)

        self._task = asyncio.create_task(_loop())

    def stop(self) -> None:
        if self._task is not None:
            self._task.cancel()
            self._task = None

    @abc.abstractmethod
    async def capture(self) -> Optional[PresenceSnapshot]:
        """执行一次检测，返回快照。"""

        raise NotImplementedError

    async def probe(self, duration: float = 3.0, interval: Optional[float] = None) -> None:
        """有限时间内主动采集若干快照。"""

        interval = self._capture_interval if interval is None else interval
        interval = max(interval, 0.1)
        loop = asyncio.get_running_loop()
        end_at = loop.time() + max(duration, 0.1)

        while True:
            snapshot = await self.capture()
            if snapshot is not None:
                self._publish(snapshot)
            if loop.time() >= end_at:
                break
            await asyncio.sleep(interval)

    def _publish(self, snapshot: PresenceSnapshot) -> None:
        self.publish(
            {
                "presence_confidence": float(snapshot.confidence),
                "posture_score": float(snapshot.posture_score),
                "presence_state": 1.0 if snapshot.presence else 0.0,
                "posture_state": snapshot.posture_state,
            }
        )
