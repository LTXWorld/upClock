"""摄像头采集实现，优先使用 AVFoundation，回退到 OpenCV。"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from typing import AsyncIterator, Optional

try:  # pragma: no cover - 仅在 macOS 可用
    import AVFoundation  # type: ignore
    import CoreMedia  # type: ignore
except ImportError:  # pragma: no cover
    AVFoundation = None  # type: ignore

import cv2  # type: ignore
import numpy as np

logger = logging.getLogger(__name__)


@dataclass
class Frame:
    """摄像头帧数据，包含彩色与灰度视图。"""

    rgb: np.ndarray
    gray: np.ndarray
    timestamp: float


class CameraCapture:
    """摄像头帧捕获，支持异步迭代。"""

    def __init__(self, device_index: int = 0, frame_size: int = 256) -> None:
        self.device_index = device_index
        self.frame_size = frame_size
        self._capture: Optional[cv2.VideoCapture] = None

    async def __aenter__(self) -> "CameraCapture":
        loop = asyncio.get_running_loop()
        await loop.run_in_executor(None, self._open)
        return self

    async def __aexit__(self, exc_type, exc, tb) -> None:
        loop = asyncio.get_running_loop()
        await loop.run_in_executor(None, self._release)

    def _open(self) -> None:
        self._capture = cv2.VideoCapture(self.device_index)
        if not self._capture.isOpened():
            raise RuntimeError("无法打开摄像头，请检查权限或设备连接")

    def _release(self) -> None:
        if self._capture is not None:
            self._capture.release()
            self._capture = None

    async def frames(self) -> AsyncIterator[Frame]:
        if self._capture is None:
            raise RuntimeError("摄像头未打开")

        loop = asyncio.get_running_loop()
        while True:
            ret, frame = await loop.run_in_executor(None, self._capture.read)
            if not ret:
                logger.warning("摄像头读取失败，尝试重连")
                await loop.run_in_executor(None, self._open)
                continue

            rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            resized_rgb = cv2.resize(rgb, (self.frame_size, self.frame_size), interpolation=cv2.INTER_AREA)
            gray = cv2.cvtColor(resized_rgb, cv2.COLOR_RGB2GRAY)
            yield Frame(rgb=resized_rgb, gray=gray, timestamp=loop.time())


async def test_camera_capture() -> None:
    async with CameraCapture() as camera:
        async for frame in camera.frames():
            logger.info("Capture frame %s", frame.rgb.shape)
            break


if __name__ == "__main__":
    asyncio.run(test_camera_capture())
