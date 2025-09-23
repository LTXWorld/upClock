"""ONNX 姿态估计实现，默认支持 MoveNet SinglePose 模型。"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Optional

import numpy as np

try:  # pragma: no cover - 可选依赖
    import onnxruntime as ort  # type: ignore
except Exception as exc:  # pragma: no cover - 未安装 onnxruntime
    ort = None  # type: ignore
    _onnx_error = exc
else:  # pragma: no cover
    _onnx_error = None

try:  # pragma: no cover - vision 依赖
    import cv2  # type: ignore
except Exception as exc:  # pragma: no cover
    cv2 = None  # type: ignore
    _cv_error = exc
else:  # pragma: no cover
    _cv_error = None

from .posture_estimator import (
    MediaPipePoseEstimator,
    PostureEstimate,
    PostureEstimationConfig,
    PostureEstimator,
)

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class OnnxModelSpec:
    """描述 ONNX 姿态模型的输入输出规范。"""

    name: str
    input_size: tuple[int, int]
    input_layout: str  # "nhwc" | "nchw"
    mean: tuple[float, float, float]
    std: tuple[float, float, float]
    output_type: str  # "movenet" | "vector"
    keypoint_names: tuple[str, ...]


def _known_model_specs() -> Dict[str, OnnxModelSpec]:
    """返回预置的模型规格表。"""

    movenet = OnnxModelSpec(
        name="movenet-singlepose",
        input_size=(192, 192),
        input_layout="nhwc",
        mean=(0.0, 0.0, 0.0),
        std=(255.0, 255.0, 255.0),
        output_type="movenet",
        keypoint_names=(
            "nose",
            "left_eye",
            "right_eye",
            "left_ear",
            "right_ear",
            "left_shoulder",
            "right_shoulder",
            "left_elbow",
            "right_elbow",
            "left_wrist",
            "right_wrist",
            "left_hip",
            "right_hip",
            "left_knee",
            "right_knee",
            "left_ankle",
            "right_ankle",
        ),
    )

    return {
        "movenet-singlepose": movenet,
        "movenet-singlepose-lightning": movenet,
        "movenet-lightning": movenet,
        "default": movenet,
    }


@dataclass
class _KeyPoint:
    x: float
    y: float
    z: float
    visibility: float


class ONNXPoseEstimator(PostureEstimator):
    """基于 ONNXRuntime 的姿态估计实现。

    默认支持 MoveNet SinglePose（Lightning/Thunder）导出的 ONNX 模型，
    也支持自定义输出为 `[presence_confidence, posture_score]` 的轻量模型。
    """

    def __init__(
        self,
        config: Optional[PostureEstimationConfig] = None,
        model_path: Optional[str] = None,
        model_type: Optional[str] = None,
        providers: Optional[list[str]] = None,
    ) -> None:
        super().__init__(config=config)
        if ort is None:
            raise RuntimeError(
                "未安装 onnxruntime，请通过 `uv sync --extra vision` 安装依赖"
            ) from _onnx_error
        if cv2 is None:
            raise RuntimeError(
                "未安装 OpenCV，无法对图像进行预处理，请启用 `vision` 额外依赖"
            ) from _cv_error

        self._spec = self._resolve_spec(model_type or (config.onnx_model_type if config else None))
        self._model_path = self._resolve_model_path(model_path or (config.onnx_model_path if config else None))
        self._session = ort.InferenceSession(
            self._model_path,
            providers=providers or ["CPUExecutionProvider"],
        )
        inputs = self._session.get_inputs()
        if not inputs:
            raise RuntimeError("ONNX 模型缺少输入定义")
        self._input_name = inputs[0].name

    def estimate(self, frame_rgb: np.ndarray) -> Optional[PostureEstimate]:  # pragma: no cover - 依赖外部模型
        try:
            input_tensor = self._prepare_input(frame_rgb)
            outputs = self._session.run(None, {self._input_name: input_tensor})
        except Exception as exc:  # pragma: no cover - 推理失败时返回 None
            logger.debug("ONNX 姿态推理失败，将回退到其他信号: %s", exc, exc_info=True)
            return None

        if not outputs:
            logger.debug("ONNX 姿态模型未返回结果")
            return None

        try:
            return self._postprocess(outputs)
        except Exception as exc:  # pragma: no cover - 解析失败
            logger.debug("ONNX 姿态结果解析失败: %s", exc, exc_info=True)
            return None

    # -- 内部工具 ---------------------------------------------------------

    def _resolve_spec(self, model_type: Optional[str]) -> OnnxModelSpec:
        specs = _known_model_specs()
        if not model_type:
            return specs["default"]
        key = model_type.lower()
        if key not in specs:
            raise ValueError(f"未知的 ONNX 姿态模型类型: {model_type}")
        return specs[key]

    def _resolve_model_path(self, model_path: Optional[str]) -> str:
        if not model_path:
            raise RuntimeError("尚未配置 ONNX 姿态模型路径")
        path = Path(model_path).expanduser()
        if not path.exists():
            raise FileNotFoundError(f"找不到指定的 ONNX 模型文件: {path}")
        return str(path)

    def _prepare_input(self, frame_rgb: np.ndarray) -> np.ndarray:
        width, height = self._spec.input_size
        resized = cv2.resize(frame_rgb, (width, height), interpolation=cv2.INTER_AREA)
        tensor = resized.astype(np.float32)

        mean = np.array(self._spec.mean, dtype=np.float32)
        std = np.array(self._spec.std, dtype=np.float32)
        tensor = (tensor - mean) / std

        if self._spec.input_layout == "nhwc":
            tensor = tensor[None, ...]
        elif self._spec.input_layout == "nchw":
            tensor = np.transpose(tensor, (2, 0, 1))[None, ...]
        else:
            raise ValueError(f"不支持的输入布局: {self._spec.input_layout}")

        return tensor.astype(np.float32, copy=False)

    def _postprocess(self, outputs: list[np.ndarray]) -> PostureEstimate:
        if self._spec.output_type == "movenet":
            return self._postprocess_movenet(outputs[0])
        if self._spec.output_type == "vector":
            return self._postprocess_vector(outputs[0])
        raise ValueError(f"不支持的输出类型: {self._spec.output_type}")

    def _postprocess_movenet(self, output: np.ndarray) -> PostureEstimate:
        keypoints = np.array(output)
        keypoints = np.squeeze(keypoints)
        if keypoints.ndim != 2 or keypoints.shape[0] < len(self._spec.keypoint_names):
            raise ValueError(f"MoveNet 输出尺寸不符: {keypoints.shape}")

        mapping = {}
        for idx, name in enumerate(self._spec.keypoint_names):
            y, x, score = keypoints[idx][:3]
            mapping[name] = _KeyPoint(x=float(x), y=float(y), z=0.0, visibility=float(score))

        return MediaPipePoseEstimator.compute_posture_from_keypoints(mapping, config=self._config)

    def _postprocess_vector(self, output: np.ndarray) -> PostureEstimate:
        vector = np.array(output).reshape(-1)
        if vector.size < 2:
            raise ValueError(f"向量输出长度不足: {vector.size}")

        confidence = float(np.clip(vector[0], 0.0, 1.0))
        posture_score = float(np.clip(vector[1], 0.0, 1.0))
        presence = confidence >= self._config.presence_threshold

        if posture_score >= self._config.upright_threshold:
            posture_state = "upright"
        elif posture_score <= self._config.slouch_threshold:
            posture_state = "slouch"
        else:
            posture_state = "uncertain"

        return PostureEstimate(
            presence=presence,
            confidence=confidence,
            posture_score=round(posture_score, 4),
            posture_state=posture_state,
        )
