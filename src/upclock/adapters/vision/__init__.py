"""视觉传感器适配器。"""

from .base import PresenceSnapshot, VisionAdapter
from .camera_adapter import CameraVisionAdapter
from .posture_estimator import PostureEstimationConfig
from .simulated import SimulatedVisionAdapter

__all__ = [
    "PresenceSnapshot",
    "VisionAdapter",
    "CameraVisionAdapter",
    "PostureEstimationConfig",
    "SimulatedVisionAdapter",
]
