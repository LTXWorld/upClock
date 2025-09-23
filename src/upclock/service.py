"""后台采集与状态栏通信桥接。"""

from __future__ import annotations

import asyncio
import logging
import random
import threading
import time
from dataclasses import dataclass, field
from typing import Optional

from upclock.adapters.macos import MacOSInputMonitor, MacOSWindowMonitor
from upclock.adapters.vision import (
    CameraVisionAdapter,
    SimulatedVisionAdapter,
    VisionAdapter,
    camera_import_exc,
)
from upclock.adapters.vision.controller import VisionController
from upclock.adapters.vision.posture_estimator import PostureEstimationConfig
from upclock.config import AppConfig
from upclock.core.activity_engine import ActivityEngine, ActivitySnapshot, ActivityState
from upclock.core.signal_buffer import SignalBuffer
from upclock.ui.status import NotificationMessage, StatusSnapshot


REMINDER_SUGGESTIONS = [
    "已经坐了很久啦，站起来放松三分钟吧！",
    "站起来做一次猫式伸展，舒展一下脊柱和肩颈。",
    "离开座位去喝杯水，让身体和大脑都补充点水分。",
    "眺望窗外 20 米外的物体 20 秒，让眼睛休息一下。",
]


@dataclass
class SharedState:
    """共享状态，用于状态栏读取最新快照。"""

    status: Optional[StatusSnapshot] = None
    activity: Optional[ActivitySnapshot] = None
    notification: Optional[NotificationMessage] = None
    system_sleeping: bool = False
    system_state_changed_at: float = 0.0
    flow_mode_until: float = 0.0
    _lock: threading.Lock = field(default_factory=threading.Lock, init=False, repr=False)

    def set(
        self,
        activity: ActivitySnapshot,
        status: StatusSnapshot,
        notification: Optional[NotificationMessage] = None,
    ) -> None:
        with self._lock:
            self.activity = activity
            self.status = status
            if notification is not None:
                self.notification = notification

    def set_system_sleeping(self, sleeping: bool) -> None:
        """更新系统睡眠状态。"""

        with self._lock:
            self.system_sleeping = sleeping
            self.system_state_changed_at = time.time()

    def is_system_sleeping(self) -> bool:
        with self._lock:
            return self.system_sleeping

    def last_system_state_change(self) -> float:
        with self._lock:
            return self.system_state_changed_at

    def get_status(self) -> Optional[StatusSnapshot]:
        with self._lock:
            return self.status

    def get_activity(self) -> Optional[ActivitySnapshot]:
        with self._lock:
            return self.activity

    def pop_notification(self) -> Optional[NotificationMessage]:
        with self._lock:
            message = self.notification
            self.notification = None
            return message

    def activate_flow_mode(self, duration_minutes: float) -> None:
        duration_seconds = max(0.0, float(duration_minutes)) * 60.0
        with self._lock:
            if duration_seconds <= 0:
                self.flow_mode_until = 0.0
            else:
                self.flow_mode_until = time.time() + duration_seconds

    def cancel_flow_mode(self) -> None:
        with self._lock:
            self.flow_mode_until = 0.0

    def get_flow_mode_state(self) -> tuple[bool, float]:
        now = time.time()
        with self._lock:
            remaining = max(0.0, self.flow_mode_until - now)
            if remaining <= 0.0:
                self.flow_mode_until = 0.0
                return False, 0.0
            return True, remaining / 60.0


async def run_backend(shared: SharedState) -> None:
    """运行异步后台服务，周期性刷新共享状态。"""

    config = AppConfig.load()
    buffer = SignalBuffer()
    engine = ActivityEngine(buffer, config=config)

    input_monitor = MacOSInputMonitor(buffer)
    window_monitor = MacOSWindowMonitor(buffer, categories=config.window_categories)
    vision_adapter: Optional[VisionAdapter] = None
    vision_controller: Optional[VisionController] = None

    if config.vision_enabled:
        if CameraVisionAdapter is None:
            logging.getLogger(__name__).warning(
                "摄像头模块初始化失败，将禁用视觉检测: %s",
                camera_import_exc,
            )
            config = config.model_copy(update={"vision_enabled": False})

    if config.vision_enabled:
        try:
            posture_config = PostureEstimationConfig(
                presence_threshold=config.vision_presence_threshold,
                upright_threshold=config.vision_posture_upright_threshold,
                slouch_threshold=config.vision_posture_slouch_threshold,
                min_landmark_confidence=config.vision_pose_min_confidence,
                depth_tolerance=config.vision_posture_depth_tolerance,
                shoulder_tilt_tolerance=config.vision_posture_tilt_tolerance,
                onnx_model_path=config.vision_onnx_model_path,
                onnx_model_type=config.vision_onnx_model_type,
            )
            vision_adapter = CameraVisionAdapter(
                buffer,
                capture_interval=max(1.0, config.vision_capture_interval_seconds),
                posture_backend=config.vision_pose_backend,
                posture_config=posture_config,
            )
        except Exception as exc:  # pragma: no cover - 摄像头初始化失败
            logger = logging.getLogger(__name__)
            logger.warning("摄像头不可用，改用模拟视觉信号: %s", exc)
            vision_adapter = SimulatedVisionAdapter(
                buffer,
                capture_interval=max(1.0, config.vision_capture_interval_seconds),
            )

    if vision_adapter is not None:
        vision_controller = VisionController(
            adapter=vision_adapter,
                ambiguous_seconds=60.0,
                break_reset_seconds=config.break_reset_minutes * 60.0,
                probe_duration=3.0,
                probe_interval=0.5,
                cooldown_seconds=120.0,
                confidence_hold=config.vision_presence_threshold,
            )

    await input_monitor.start()
    await window_monitor.start()

    last_notification_at: Optional[float] = None
    last_suggestion: Optional[str] = None
    cooldown_seconds = config.notification_cooldown_minutes * 60
    was_sleeping = shared.is_system_sleeping()

    try:
        while True:
            sleeping = shared.is_system_sleeping()
            flow_active, flow_remaining = shared.get_flow_mode_state()

            if sleeping:
                if not was_sleeping:
                    engine.reset_state()
                    if buffer is not None:
                        buffer.clear()
                now = time.time()
                snapshot = ActivitySnapshot(
                    score=1.0,
                    state=ActivityState.SHORT_BREAK,
                    metrics={
                        "activity_sum": 0.0,
                        "normalized_activity": 0.0,
                        "seated_minutes": 0.0,
                        "break_minutes": 0.0,
                        "presence_confidence": 0.0,
                        "posture_score": 1.0,
                        "posture_state": "sleeping",
                        "score": 1.0,
                        "system_state": "sleeping",
                        "flow_mode_active": 1.0 if flow_active else 0.0,
                        "flow_mode_remaining": float(flow_remaining if flow_active else 0.0),
                    },
                    flow_mode_remaining=flow_remaining if flow_active else None,
                )

                shared.set(
                    activity=snapshot,
                    status=StatusSnapshot(
                        state=ActivityState.SHORT_BREAK,
                        score=1.0,
                        seated_minutes=0.0,
                        break_minutes=0.0,
                        updated_at=now,
                        next_reminder_minutes=None,
                        flow_mode_minutes=flow_remaining if flow_active else None,
                    ),
                    notification=None,
                )

                last_notification_at = None
                was_sleeping = True
                await asyncio.sleep(2.0)
                continue

            if was_sleeping:
                engine.reset_state()
                if buffer is not None:
                    buffer.clear()
                was_sleeping = False

            snapshot = engine.compute_snapshot()
            snapshot.flow_mode_remaining = flow_remaining if flow_active else None
            snapshot.metrics["flow_mode_active"] = 1.0 if flow_active else 0.0
            snapshot.metrics["flow_mode_remaining"] = float(flow_remaining if flow_active else 0.0)

            probe_pending = float(snapshot.metrics.get("visual_probe_pending", 0.0) or 0.0) >= 0.5
            if probe_pending and vision_adapter is not None:
                await vision_adapter.probe(duration=3.0, interval=0.5)
                engine.mark_visual_probe_fired()
                snapshot = engine.compute_snapshot()

            now = time.time()
            seated_minutes = snapshot.metrics.get("seated_minutes", 0.0)
            break_minutes = snapshot.metrics.get("break_minutes", 0.0)

            next_reminder_minutes: Optional[float] = None
            notification: Optional[NotificationMessage] = None

            if config.notifications_enabled and not flow_active:
                if snapshot.state is ActivityState.PROLONGED_SEATED:
                    should_notify = False
                    if last_notification_at is None:
                        should_notify = True
                    else:
                        elapsed = now - last_notification_at
                        if elapsed >= cooldown_seconds:
                            should_notify = True
                        else:
                            next_reminder_minutes = max(0.0, (cooldown_seconds - elapsed) / 60)

                    if should_notify:
                        suggestion = _pick_reminder_suggestion(last_suggestion)
                        notification = NotificationMessage(
                            title="该活动一下啦",
                            subtitle="久坐提醒",
                            body=suggestion,
                        )
                        last_notification_at = now
                        last_suggestion = suggestion
                        next_reminder_minutes = config.notification_cooldown_minutes
                else:
                    last_notification_at = None

            shared.set(
                activity=snapshot,
                status=StatusSnapshot(
                    state=snapshot.state,
                    score=snapshot.score,
                    seated_minutes=seated_minutes,
                    break_minutes=break_minutes,
                    updated_at=now,
                    next_reminder_minutes=next_reminder_minutes,
                    flow_mode_minutes=flow_remaining if flow_active else None,
                ),
                notification=notification,
            )

            if vision_controller is not None:
                presence_conf = float(snapshot.metrics.get("presence_confidence", 0.0) or 0.0)
                posture_state = str(snapshot.metrics.get("posture_state", "unknown"))
                vision_controller.update(
                    break_minutes=break_minutes,
                    presence_confidence=presence_conf,
                    posture_state=posture_state,
                    now=now,
                )
            await asyncio.sleep(2.0)
    finally:
        input_monitor.stop()
        window_monitor.stop()
        if vision_controller is not None:
            await vision_controller.aclose()
        if vision_adapter is not None:
            vision_adapter.stop()


def start_backend_in_thread(shared: SharedState) -> threading.Thread:
    """在独立线程运行 asyncio 后台服务。"""

    loop = asyncio.new_event_loop()

    def _run() -> None:
        asyncio.set_event_loop(loop)
        loop.run_until_complete(run_backend(shared))

    thread = threading.Thread(target=_run, name="upclock-backend", daemon=True)
    thread.start()
    return thread


def _pick_reminder_suggestion(last: Optional[str]) -> str:
    """从候选列表中挑选提醒语，尽量避免连续重复。"""

    if not REMINDER_SUGGESTIONS:
        return "已经坐了很久啦，站起来放松三分钟吧！"

    if len(REMINDER_SUGGESTIONS) == 1:
        return REMINDER_SUGGESTIONS[0]

    candidates = [s for s in REMINDER_SUGGESTIONS if s != last]
    if not candidates:
        candidates = REMINDER_SUGGESTIONS
    return random.choice(candidates)
