"""本地配置覆盖示例（未自动导入，可手动在 main 中启用）。"""

from upclock.config import AppConfig, WindowCategory


def load_config() -> AppConfig:
    return AppConfig(
        short_break_minutes=3,
        break_reset_minutes=3,
        prolonged_seated_minutes=45,
        window_categories=[WindowCategory(name="work", weight=1.0)],
        notifications_enabled=True,
        notification_cooldown_minutes=30,
        vision_enabled=True,
        vision_capture_interval_seconds=10.0,
        vision_presence_threshold=0.6,
        vision_pose_backend="auto",
        vision_pose_min_confidence=0.15,
        vision_posture_upright_threshold=0.75,
        vision_posture_slouch_threshold=0.35,
        vision_posture_depth_tolerance=0.2,
        vision_posture_tilt_tolerance=0.12,
        # vision_onnx_model_path="/path/to/your/posture_model.onnx",
        # vision_onnx_model_type="movenet-singlepose" ,
    )
