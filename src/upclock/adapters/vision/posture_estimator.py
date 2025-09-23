"""姿态估计模块，默认使用 MediaPipe，支持扩展 ONNX 实现。"""

from __future__ import annotations

import abc
import logging
from dataclasses import dataclass
from typing import Optional

try:  # pragma: no cover - numpy 为可选依赖
    import numpy as np
except ImportError:  # pragma: no cover - 缺少 numpy 时允许降级
    np = None  # type: ignore[assignment]

logger = logging.getLogger(__name__)

try:  # pragma: no cover - 依赖可选组件
    import mediapipe as mp  # type: ignore
except ImportError:  # pragma: no cover - 未安装 mediapipe 时允许降级
    mp = None  # type: ignore


@dataclass
class PostureEstimate:
    """姿态估计结果。"""

    presence: bool
    confidence: float
    posture_score: float
    posture_state: str


@dataclass
class PostureEstimationConfig:
    """姿态估计阈值配置。"""

    presence_threshold: float = 0.4
    upright_threshold: float = 0.7
    slouch_threshold: float = 0.4
    min_landmark_confidence: float = 0.2
    depth_tolerance: float = 0.15
    shoulder_tilt_tolerance: float = 0.1
    onnx_model_path: Optional[str] = None
    onnx_model_type: Optional[str] = None


class PostureEstimator(abc.ABC):
    """姿态估计器抽象基类。"""

    def __init__(self, config: Optional[PostureEstimationConfig] = None) -> None:
        if np is None:  # pragma: no cover - 缺少 numpy 时不应实例化
            raise RuntimeError("未找到 numpy，姿态估计模块不可用，请安装 `uv sync --extra vision`")
        self._config = config or PostureEstimationConfig()

    @abc.abstractmethod
    def estimate(self, frame_rgb: np.ndarray) -> Optional[PostureEstimate]:
        """对一帧 RGB 图像执行姿态估计。"""

    def close(self) -> None:
        """释放底层资源。默认无需处理。"""


class MediaPipePoseEstimator(PostureEstimator):
    """基于 MediaPipe Pose 的姿态估计实现。"""

    def __init__(
        self,
        config: Optional[PostureEstimationConfig] = None,
        model_complexity: int = 1,
        enable_segmentation: bool = False,
        min_detection_confidence: float = 0.5,
        min_tracking_confidence: float = 0.5,
    ) -> None:
        super().__init__(config=config)
        if mp is None:  # pragma: no cover - 仅在缺少 mediapipe 时触发
            raise RuntimeError(
                "未找到 MediaPipe，请先安装 `uv sync --extra vision` 并确认 mediapipe 可用"
            )
        self._pose = mp.solutions.pose.Pose(  # type: ignore[attr-defined]
            static_image_mode=False,
            model_complexity=model_complexity,
            smooth_landmarks=True,
            enable_segmentation=enable_segmentation,
            min_detection_confidence=min_detection_confidence,
            min_tracking_confidence=min_tracking_confidence,
        )

    def estimate(self, frame_rgb: np.ndarray) -> Optional[PostureEstimate]:
        frame_rgb = np.ascontiguousarray(frame_rgb)
        results = self._pose.process(frame_rgb)  # type: ignore[call-arg]
        if results is None or results.pose_landmarks is None:
            return None

        return self._parse_landmarks(results.pose_landmarks.landmark)

    def close(self) -> None:
        self._pose.close()

    def _parse_landmarks(self, landmarks) -> Optional[PostureEstimate]:  # type: ignore[no-untyped-def]
        keypoints = {lm.name.lower(): landmarks[lm.value] for lm in mp.solutions.pose.PoseLandmark}  # type: ignore[attr-defined]
        try:
            return self.compute_posture_from_keypoints(
                keypoints,
                config=self._config,
            )
        except ValueError as exc:  # pragma: no cover - 坐标缺失的异常路径
            logger.debug("姿态估计关键点不足: %s", exc)
            return None

    @staticmethod
    def compute_posture_from_keypoints(
        keypoints: dict[str, object],
        config: PostureEstimationConfig,
    ) -> PostureEstimate:
        required = [
            "left_shoulder",
            "right_shoulder",
            "left_hip",
            "right_hip",
        ]
        points = {}
        for name in required:
            landmark = keypoints.get(name)
            if landmark is None:
                raise ValueError(f"缺少关键点 {name}")
            points[name] = landmark

        def _vec(name: str) -> np.ndarray:
            lm = points[name]
            return np.array([lm.x, lm.y, lm.z, lm.visibility])  # type: ignore[attr-defined]

        left_shoulder = _vec("left_shoulder")
        right_shoulder = _vec("right_shoulder")
        left_hip = _vec("left_hip")
        right_hip = _vec("right_hip")

        shoulder_center = (left_shoulder[:3] + right_shoulder[:3]) / 2.0
        hip_center = (left_hip[:3] + right_hip[:3]) / 2.0
        torso_vector = shoulder_center - hip_center

        torso_xy = torso_vector[:2]
        torso_norm = np.linalg.norm(torso_xy)
        if torso_norm < 1e-5:
            posture_score = 0.0
        else:
            vertical = np.array([0.0, -1.0])  # 图像坐标系向上为负
            cos_theta = float(np.dot(torso_xy, vertical) / (torso_norm * np.linalg.norm(vertical)))
            posture_score = max(0.0, min(1.0, cos_theta))

        avg_visibility = float(
            np.mean([left_shoulder[3], right_shoulder[3], left_hip[3], right_hip[3]])
        )

        if avg_visibility < config.min_landmark_confidence:
            return PostureEstimate(
                presence=False,
                confidence=avg_visibility,
                posture_score=0.0,
                posture_state="untracked",
            )

        depth_delta = float(abs((shoulder_center[2] - hip_center[2])))
        depth_penalty = min(0.5, depth_delta / max(config.depth_tolerance, 1e-3)) * 0.3
        posture_score = max(0.0, posture_score - depth_penalty)

        shoulder_tilt = abs(left_shoulder[1] - right_shoulder[1])
        tilt_penalty = min(0.4, shoulder_tilt / max(config.shoulder_tilt_tolerance, 1e-3)) * 0.2
        posture_score = max(0.0, posture_score - tilt_penalty)

        if posture_score >= config.upright_threshold:
            posture_state = "upright"
        elif posture_score <= config.slouch_threshold:
            posture_state = "slouch"
        else:
            posture_state = "uncertain"

        presence = avg_visibility >= config.presence_threshold
        confidence = max(0.0, min(1.0, avg_visibility))

        return PostureEstimate(
            presence=presence,
            confidence=confidence,
            posture_score=round(posture_score, 4),
            posture_state=posture_state,
        )


def create_posture_estimator(
    backend: str = "mediapipe",
    config: Optional[PostureEstimationConfig] = None,
) -> Optional[PostureEstimator]:
    """根据配置创建姿态估计器，未安装依赖时返回 None。"""

    backend = (backend or "mediapipe").lower()

    if np is None:
        logger.warning("未安装 numpy，姿态估计功能将禁用")
        return None

    def _create(single_backend: str) -> PostureEstimator:
        if single_backend == "mediapipe":
            return MediaPipePoseEstimator(config=config)
        if single_backend == "onnx":  # pragma: no cover - 依赖外部模型与权重
            try:
                from .posture_onnx import ONNXPoseEstimator  # type: ignore
            except ImportError as exc:  # pragma: no cover
                raise RuntimeError("未找到 ONNX 姿态估计实现，请检查依赖") from exc

            model_path = config.onnx_model_path if config else None
            model_type = config.onnx_model_type if config else None
            return ONNXPoseEstimator(
                config=config,
                model_path=model_path,
                model_type=model_type,
            )
        raise ValueError(f"不支持的姿态估计后端: {single_backend}")

    candidates = [backend]
    if backend == "auto":
        candidates = ["mediapipe", "onnx"]

    for candidate in candidates:
        try:
            return _create(candidate)
        except Exception as exc:  # pragma: no cover - 自动回退到下一候选
            logger.warning("姿态估计器初始化失败(%s)，尝试其他后端: %s", candidate, exc)
            continue

    logger.warning("所有姿态估计后端初始化失败，将降级为帧差法 (backend=%s)", backend)
    return None
