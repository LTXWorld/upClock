"""MediaPipe 姿态几何计算单元测试。"""

from __future__ import annotations

from dataclasses import dataclass

from upclock.adapters.vision.posture_estimator import (
    MediaPipePoseEstimator,
    PostureEstimationConfig,
)


@dataclass
class _Landmark:
    x: float
    y: float
    z: float
    visibility: float


def _make_keypoints(**kwargs) -> dict[str, _Landmark]:
    return {name: _Landmark(*values) for name, values in kwargs.items()}


def test_compute_posture_upright() -> None:
    config = PostureEstimationConfig(
        presence_threshold=0.4,
        upright_threshold=0.7,
        slouch_threshold=0.3,
        min_landmark_confidence=0.2,
    )
    keypoints = _make_keypoints(
        left_shoulder=(0.4, 0.4, 0.0, 0.9),
        right_shoulder=(0.6, 0.4, 0.0, 0.9),
        left_hip=(0.4, 0.7, 0.0, 0.9),
        right_hip=(0.6, 0.7, 0.0, 0.9),
    )

    estimation = MediaPipePoseEstimator.compute_posture_from_keypoints(keypoints, config=config)
    assert estimation.presence is True
    assert estimation.posture_state == "upright"
    assert estimation.posture_score >= 0.8


def test_compute_posture_slouch() -> None:
    config = PostureEstimationConfig(
        presence_threshold=0.4,
        upright_threshold=0.7,
        slouch_threshold=0.3,
        min_landmark_confidence=0.2,
    )
    keypoints = _make_keypoints(
        left_shoulder=(0.4, 0.85, -0.3, 0.8),
        right_shoulder=(0.6, 0.82, -0.25, 0.8),
        left_hip=(0.4, 0.7, 0.0, 0.8),
        right_hip=(0.6, 0.7, 0.0, 0.8),
    )

    estimation = MediaPipePoseEstimator.compute_posture_from_keypoints(keypoints, config=config)
    assert estimation.presence is True
    assert estimation.posture_state in {"slouch", "uncertain"}
    assert estimation.posture_score <= 0.5


def test_compute_posture_low_confidence_returns_untracked() -> None:
    config = PostureEstimationConfig(
        presence_threshold=0.4,
        upright_threshold=0.7,
        slouch_threshold=0.3,
        min_landmark_confidence=0.6,
    )
    keypoints = _make_keypoints(
        left_shoulder=(0.4, 0.4, 0.0, 0.2),
        right_shoulder=(0.6, 0.4, 0.0, 0.2),
        left_hip=(0.4, 0.7, 0.0, 0.2),
        right_hip=(0.6, 0.7, 0.0, 0.2),
    )

    estimation = MediaPipePoseEstimator.compute_posture_from_keypoints(keypoints, config=config)
    assert estimation.presence is False
    assert estimation.posture_state == "untracked"
    assert estimation.posture_score == 0.0
