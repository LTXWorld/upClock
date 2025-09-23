"""视觉传感器适配器。"""

from .base import PresenceSnapshot, VisionAdapter
camera_import_exc = None
try:
    from .camera_adapter import CameraVisionAdapter  # noqa: F401
except Exception as exc:  # pragma: no cover - 视觉依赖缺失时触发
    camera_import_exc = exc
    CameraVisionAdapter = None  # type: ignore[assignment]
from .posture_estimator import PostureEstimationConfig
from .simulated import SimulatedVisionAdapter

__all__ = [
    "PresenceSnapshot",
    "VisionAdapter",
    "CameraVisionAdapter",
    "PostureEstimationConfig",
    "SimulatedVisionAdapter",
    "camera_import_exc",
]
