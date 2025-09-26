"""应用配置模型。"""

from __future__ import annotations

import importlib.util
from pathlib import Path

from pydantic import BaseModel, Field


class WindowCategory(BaseModel):
    """单个窗口分类配置。"""

    name: str
    weight: float = Field(1.0, ge=0.0)
    patterns: list[str] = Field(default_factory=list)


class AppConfig(BaseModel):
    """总配置，后续将从 YAML 加载。"""

    short_break_minutes: int = Field(3, ge=1)
    break_reset_minutes: int = Field(3, ge=1)
    prolonged_seated_minutes: int = Field(45, ge=1)
    window_categories: list[WindowCategory] = Field(default_factory=list)
    notifications_enabled: bool = True
    notification_cooldown_minutes: int = Field(30, ge=1)
    quiet_hours: list[list[str]] = Field(default_factory=list)
    vision_enabled: bool = True
    vision_capture_interval_seconds: float = Field(10.0, ge=1.0)
    vision_presence_threshold: float = Field(0.6, ge=0.0, le=1.0)
    vision_pose_backend: str = "auto"
    vision_pose_min_confidence: float = Field(0.2, ge=0.0, le=1.0)
    vision_posture_upright_threshold: float = Field(0.7, ge=0.0, le=1.0)
    vision_posture_slouch_threshold: float = Field(0.4, ge=0.0, le=1.0)
    vision_posture_depth_tolerance: float = Field(0.15, ge=0.01)
    vision_posture_tilt_tolerance: float = Field(0.1, ge=0.01)
    vision_onnx_model_path: str | None = None
    vision_onnx_model_type: str | None = None

    @classmethod
    def load_default(cls) -> "AppConfig":
        """先返回默认配置，后续支持 YAML 文件。"""

        return cls(window_categories=[WindowCategory(name="work", weight=1.0)])

    @classmethod
    def load(cls) -> "AppConfig":
        """优先尝试加载项目根目录的 `config.local.py`，否则返回默认配置。"""

        root_dir = Path(__file__).resolve().parents[2]
        local_path = root_dir / "config.local.py"
        if not local_path.exists():
            return cls.load_default()

        spec = importlib.util.spec_from_file_location("config_local", local_path)
        if spec is None or spec.loader is None:
            return cls.load_default()

        module = importlib.util.module_from_spec(spec)
        try:
            spec.loader.exec_module(module)  # type: ignore[arg-type]
        except Exception:
            return cls.load_default()

        load_fn = getattr(module, "load_config", None)
        if callable(load_fn):
            try:
                return load_fn()
            except Exception:
                return cls.load_default()
        return cls.load_default()

    @classmethod
    def from_file(cls, path: Path) -> "AppConfig":
        """从 YAML 解析配置，当前暂未实现。"""

        raise NotImplementedError("YAML 解析将在后续迭代中实现")
