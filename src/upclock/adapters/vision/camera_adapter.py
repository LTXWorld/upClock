"""基础摄像头适配器，采集摄像头帧并执行姿态估计。"""

from __future__ import annotations

import asyncio
import datetime as dt
import logging
from typing import Optional

import numpy as np

from upclock.adapters.vision.base import PresenceSnapshot, VisionAdapter
from upclock.adapters.vision.capture import CameraCapture, Frame
from upclock.adapters.vision.diff_presence import DiffPresenceDetector
from upclock.adapters.vision.posture_estimator import (
    PostureEstimationConfig,
    PostureEstimator,
    create_posture_estimator,
)

logger = logging.getLogger(__name__)


class CameraVisionAdapter(VisionAdapter):
    """通过摄像头帧差分估算在位情况。"""

    def __init__(
        self,
        buffer,
        capture_interval: float = 10.0,
        frame_size: int = 256,
        diff_threshold: float = 15.0,
        posture_backend: str = "auto",
        posture_config: Optional[PostureEstimationConfig] = None,
    ) -> None:
        super().__init__(buffer, capture_interval=capture_interval)
        self._frame_size = frame_size
        self._diff_threshold = diff_threshold
        self._diff_detector = DiffPresenceDetector(threshold=diff_threshold)
        self._posture_config = posture_config or PostureEstimationConfig()
        self._pose_estimator: Optional[PostureEstimator] = create_posture_estimator(
            backend=posture_backend,
            config=self._posture_config,
        )
        self._probe_lock = asyncio.Lock()

    async def capture(self) -> Optional[PresenceSnapshot]:
        snapshots = await self._collect_snapshots(
            duration=max(1.0, self._capture_interval),
            interval=min(self._capture_interval, 0.5),
            min_samples=2,
            publish=False,
        )
        if snapshots:
            return snapshots[-1]
        return None

    async def probe(
        self,
        duration: float = 3.0,
        interval: float = 0.5,
        min_samples: int = 3,
    ) -> None:
        await self._collect_snapshots(
            duration=max(duration, 0.5),
            interval=max(interval, 0.1),
            min_samples=max(min_samples, 1),
            publish=True,
        )

    async def _collect_snapshots(
        self,
        duration: float,
        interval: float,
        min_samples: int,
        publish: bool,
    ) -> list[PresenceSnapshot]:
        snapshots: list[PresenceSnapshot] = []
        async with self._probe_lock:
            self._diff_detector.reset()
            try:
                async with CameraCapture(frame_size=self._frame_size) as capture:
                    loop = asyncio.get_running_loop()
                    end_at = loop.time() + duration
                    samples = 0
                    while True:
                        frame = await self._next_frame(capture)
                        if frame is None:
                            break
                        snapshot = self._process_frame(frame)
                        snapshots.append(snapshot)
                        if publish:
                            self._publish_snapshot(snapshot)
                        samples += 1
                        if samples >= min_samples and loop.time() >= end_at:
                            break
                        if interval > 0:
                            await asyncio.sleep(interval)
            except Exception as exc:  # pragma: no cover - 依赖硬件
                logger.error("摄像头探测失败: %s", exc)
        return snapshots

    def _publish_snapshot(self, snapshot: PresenceSnapshot) -> None:
        self.publish(
            {
                "presence_confidence": float(snapshot.confidence),
                "posture_score": float(snapshot.posture_score),
                "presence_state": 1.0 if snapshot.presence else 0.0,
                "posture_state": snapshot.posture_state,
            }
        )

    def _process_frame(self, frame) -> PresenceSnapshot:
        diff_score = self._diff_detector.evaluate(frame.gray)
        diff_presence = diff_score > self._diff_threshold
        diff_confidence = min(1.0, diff_score / max(self._diff_threshold * 3.0, 1.0))

        presence = diff_presence
        confidence = diff_confidence
        posture_score = 0.0
        posture_state = "no_pose"

        if self._pose_estimator is not None:
            try:
                estimation = self._pose_estimator.estimate(frame.rgb)
            except Exception as exc:  # pragma: no cover - 姿态估计异常
                logger.debug("姿态估计执行失败，将沿用帧差结果: %s", exc)
                estimation = None

            if estimation is not None:
                presence = estimation.presence or diff_presence
                confidence = max(estimation.confidence, diff_confidence)
                posture_score = estimation.posture_score
                posture_state = estimation.posture_state if estimation.presence else "untracked"

                if not estimation.presence and diff_presence:
                    posture_score = max(posture_score, 0.2)
            else:
                posture_state = "untracked" if diff_presence else "no_pose"
                posture_score = 0.4 if diff_presence else 0.0
        else:
            posture_state = "untracked" if diff_presence else "no_pose"
            posture_score = 0.5 if diff_presence else 0.0

        return PresenceSnapshot(
            timestamp=dt.datetime.utcnow(),
            presence=presence,
            confidence=confidence,
            posture_score=round(float(posture_score), 4),
            posture_state=posture_state,
        )

    async def _next_frame(self, capture: CameraCapture) -> Optional[Frame]:
        async for frame in capture.frames():
            return frame
        return None

    def stop(self) -> None:
        super().stop()
        if self._pose_estimator is not None:
            try:
                self._pose_estimator.close()
            except Exception:  # pragma: no cover - 释放异常仅记录
                logger.debug("姿态估计器释放失败", exc_info=True)
            finally:
                self._pose_estimator = None
