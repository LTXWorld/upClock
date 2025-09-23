"""ONNX 姿态估计解析逻辑单元测试。"""

from __future__ import annotations

import numpy as np

from upclock.adapters.vision.posture_estimator import PostureEstimationConfig
from upclock.adapters.vision.posture_onnx import ONNXPoseEstimator, _known_model_specs


def _build_estimator(config: PostureEstimationConfig) -> ONNXPoseEstimator:
    estimator = ONNXPoseEstimator.__new__(ONNXPoseEstimator)
    estimator._config = config
    estimator._spec = _known_model_specs()["default"]
    return estimator


def test_postprocess_movenet_returns_upright() -> None:
    config = PostureEstimationConfig(
        presence_threshold=0.4,
        upright_threshold=0.7,
        slouch_threshold=0.3,
        min_landmark_confidence=0.2,
    )
    estimator = _build_estimator(config)

    output = np.zeros((1, 1, 17, 3), dtype=np.float32)
    # 左/右肩
    output[0, 0, 5] = (0.4, 0.45, 0.95)  # y, x, score
    output[0, 0, 6] = (0.4, 0.55, 0.95)
    # 左/右髋
    output[0, 0, 11] = (0.7, 0.46, 0.92)
    output[0, 0, 12] = (0.7, 0.54, 0.92)

    estimate = estimator._postprocess_movenet(output)
    assert estimate.presence is True
    assert estimate.posture_state == "upright"
    assert estimate.posture_score > 0.7


def test_postprocess_movenet_handles_slouch() -> None:
    config = PostureEstimationConfig(
        presence_threshold=0.4,
        upright_threshold=0.7,
        slouch_threshold=0.3,
        min_landmark_confidence=0.2,
    )
    estimator = _build_estimator(config)

    output = np.zeros((1, 1, 17, 3), dtype=np.float32)
    output[0, 0, 5] = (0.9, 0.45, 0.95)
    output[0, 0, 6] = (0.85, 0.55, 0.95)
    output[0, 0, 11] = (0.7, 0.46, 0.95)
    output[0, 0, 12] = (0.7, 0.54, 0.95)

    estimate = estimator._postprocess_movenet(output)
    assert estimate.presence is True
    assert estimate.posture_state in {"slouch", "uncertain"}
    assert estimate.posture_score < 0.7


def test_postprocess_movenet_low_visibility_untracked() -> None:
    config = PostureEstimationConfig(
        presence_threshold=0.6,
        upright_threshold=0.7,
        slouch_threshold=0.3,
        min_landmark_confidence=0.6,
    )
    estimator = _build_estimator(config)

    output = np.zeros((1, 1, 17, 3), dtype=np.float32)
    output[0, 0, 5] = (0.4, 0.45, 0.2)
    output[0, 0, 6] = (0.4, 0.55, 0.2)
    output[0, 0, 11] = (0.7, 0.46, 0.2)
    output[0, 0, 12] = (0.7, 0.54, 0.2)

    estimate = estimator._postprocess_movenet(output)
    assert estimate.presence is False
    assert estimate.posture_state == "untracked"
    assert estimate.posture_score == 0.0
