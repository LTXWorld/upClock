"""模拟视觉适配器，用于开发阶段。"""

from __future__ import annotations

import asyncio
import datetime as dt
import math
import random
from typing import Optional

from upclock.adapters.vision.base import PresenceSnapshot, VisionAdapter


class SimulatedVisionAdapter(VisionAdapter):
    """生成随机在位/姿态数据，便于测试数据流。"""

    def __init__(self, buffer, capture_interval: float = 10.0) -> None:
        super().__init__(buffer, capture_interval=capture_interval)
        self._phase = 0.0

    async def capture(self) -> Optional[PresenceSnapshot]:
        await asyncio.sleep(0)
        now = dt.datetime.utcnow()

        # 模拟一个缓慢变化的 presence 信号
        presence_chance = 0.85 + 0.1 * math.sin(self._phase)
        self._phase += 0.3
        presence = random.random() < presence_chance

        if presence:
            posture_score = max(0.2, random.gauss(0.8, 0.1))
            posture_state = "upright" if posture_score > 0.7 else "slouch"
            confidence = min(1.0, random.uniform(0.7, 0.95))
        else:
            posture_score = 0.0
            posture_state = "away"
            confidence = random.uniform(0.1, 0.4)

        return PresenceSnapshot(
            timestamp=now,
            presence=presence,
            confidence=confidence,
            posture_score=posture_score,
            posture_state=posture_state,
        )
