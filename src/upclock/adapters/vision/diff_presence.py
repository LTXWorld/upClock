"""基于帧亮度差分的简单在位判定。"""

from __future__ import annotations

import numpy as np


class DiffPresenceDetector:
    """计算相邻帧之间的差异，用于估计是否有人移动。"""

    def __init__(self, threshold: float = 15.0) -> None:
        self.threshold = threshold
        self._last_frame: np.ndarray | None = None

    def evaluate(self, frame: np.ndarray) -> float:
        if self._last_frame is None:
            self._last_frame = frame
            return 0.0

        diff = np.abs(frame.astype(np.float32) - self._last_frame.astype(np.float32))
        self._last_frame = frame
        return float(np.mean(diff))

    def reset(self) -> None:
        """重置历史帧，便于重新开始计算帧差。"""

        self._last_frame = None
