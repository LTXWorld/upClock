"""后台采集与状态栏通信桥接。"""

from __future__ import annotations

import asyncio
import datetime as dt
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
from upclock.config_store import load_user_settings, save_user_settings, UserSettings
from upclock.core.activity_engine import ActivityEngine, ActivitySnapshot, ActivityState
from upclock.core.signal_buffer import SignalBuffer
from upclock.ui.status import NotificationMessage, StatusSnapshot


REMINDER_SUGGESTIONS = [
    "已经坐了很久啦，站起来放松三分钟吧！",
    "站起来做一次猫式伸展，舒展一下脊柱和肩颈。",
    "离开座位去喝杯水，让身体和大脑都补充点水分。",
    "眺望窗外 20 米外的物体 20 秒，让眼睛休息一下。",
]


def _parse_quiet_slots(quiet_hours: list[list[str]]) -> list[tuple[int, int]]:
    slots: list[tuple[int, int]] = []
    for slot in quiet_hours:
        if len(slot) != 2:
            continue
        start = _time_str_to_minutes(slot[0])
        end = _time_str_to_minutes(slot[1])
        if start is None or end is None:
            continue
        slots.append((start, end))
    return slots


def _time_str_to_minutes(value: str) -> Optional[int]:
    parts = value.strip().split(":")
    if len(parts) != 2:
        return None
    try:
        hour = int(parts[0])
        minute = int(parts[1])
    except ValueError:
        return None
    if not (0 <= hour < 24 and 0 <= minute < 60):
        return None
    return hour * 60 + minute


def _quiet_status(now: dt.datetime, slots: list[tuple[int, int]]) -> tuple[bool, float]:
    current_minutes = now.hour * 60 + now.minute + now.second / 60.0
    for start, end in slots:
        if start == end:
            continue
        if start < end:
            if start <= current_minutes < end:
                return True, end - current_minutes
        else:  # overnight
            if current_minutes >= start or current_minutes < end:
                remaining = (end + 1440 - current_minutes) if current_minutes >= start else (end - current_minutes)
                return True, remaining
    return False, 0.0


@dataclass
class SharedState:
    """共享状态，用于状态栏读取最新快照。"""

    status: Optional[StatusSnapshot] = None
    activity: Optional[ActivitySnapshot] = None
    notification: Optional[NotificationMessage] = None
    system_sleeping: bool = False
    system_state_changed_at: float = 0.0
    flow_mode_until: float = 0.0
    snooze_until: float = 0.0
    _current_settings: Optional[UserSettings] = None
    _settings_update: Optional[UserSettings] = None
    _lock: threading.Lock = field(default_factory=threading.Lock, init=False, repr=False)
    _manual_reset_requested: bool = field(default=False, init=False, repr=False)

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

    def activate_snooze(self, duration_minutes: float) -> None:
        duration_seconds = max(0.0, float(duration_minutes)) * 60.0
        with self._lock:
            if duration_seconds <= 0:
                self.snooze_until = 0.0
            else:
                self.snooze_until = time.time() + duration_seconds

    def cancel_snooze(self) -> None:
        with self._lock:
            self.snooze_until = 0.0

    def get_snooze_state(self) -> tuple[bool, float]:
        now = time.time()
        with self._lock:
            remaining = max(0.0, self.snooze_until - now)
            if remaining <= 0.0:
                self.snooze_until = 0.0
                return False, 0.0
            return True, remaining / 60.0

    def set_current_settings(self, settings: UserSettings) -> None:
        with self._lock:
            self._current_settings = settings

    def get_current_settings(self) -> Optional[UserSettings]:
        with self._lock:
            return self._current_settings

    def queue_settings_update(self, settings: UserSettings) -> None:
        with self._lock:
            self._settings_update = settings

    def pop_settings_update(self) -> Optional[UserSettings]:
        with self._lock:
            settings = self._settings_update
            self._settings_update = None
            return settings

    def request_manual_reset(self) -> None:
        """请求手动重置计时。"""

        with self._lock:
            self._manual_reset_requested = True

    def consume_manual_reset(self) -> bool:
        with self._lock:
            requested = self._manual_reset_requested
            self._manual_reset_requested = False
            return requested


async def run_backend(shared: SharedState) -> None:
    """运行异步后台服务，周期性刷新共享状态。"""

    config = AppConfig.load()
    user_settings = load_user_settings()
    if user_settings is not None:
        config = config.model_copy(
            update={
                "prolonged_seated_minutes": user_settings.prolonged_seated_minutes,
                "notification_cooldown_minutes": user_settings.notification_cooldown_minutes,
                "quiet_hours": [list(slot) for slot in user_settings.quiet_hours],
            }
        )
    else:
        user_settings = UserSettings.from_config(config)

    shared.set_current_settings(user_settings)
    quiet_slots = _parse_quiet_slots(config.quiet_hours)
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
    prev_state: Optional[ActivityState] = None
    last_tick = time.time()
    daily_date = dt.date.today()
    daily_prolonged_seconds = 0.0
    daily_break_count = 0
    daily_longest_seated_seconds = 0.0

    try:
        while True:
            loop_now = time.time()
            delta = max(0.0, loop_now - last_tick)
            last_tick = loop_now

            today = dt.date.today()
            if today != daily_date:
                daily_date = today
                daily_prolonged_seconds = 0.0
                daily_break_count = 0
                daily_longest_seated_seconds = 0.0

            pending_settings = shared.pop_settings_update()
            if pending_settings is not None:
                try:
                    save_user_settings(pending_settings)
                except Exception:
                    logging.getLogger(__name__).warning("无法写入用户设置", exc_info=True)
                config = config.model_copy(
                    update={
                        "prolonged_seated_minutes": pending_settings.prolonged_seated_minutes,
                        "notification_cooldown_minutes": pending_settings.notification_cooldown_minutes,
                        "quiet_hours": [list(slot) for slot in pending_settings.quiet_hours],
                    }
                )
                engine.update_config(config)
                cooldown_seconds = config.notification_cooldown_minutes * 60
                quiet_slots = _parse_quiet_slots(config.quiet_hours)
                user_settings = pending_settings
                shared.set_current_settings(user_settings)

            if shared.consume_manual_reset():
                logging.getLogger(__name__).info("手动刷新久坐计时")
                engine.reset_state()
                if buffer is not None:
                    buffer.clear()
                last_notification_at = None
                prev_state = ActivityState.SHORT_BREAK

            quiet_active, quiet_remaining = _quiet_status(dt.datetime.now(), quiet_slots)

            sleeping = shared.is_system_sleeping()
            flow_active, flow_remaining = shared.get_flow_mode_state()
            snooze_active, snooze_remaining = shared.get_snooze_state()

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
                        "snooze_active": 1.0 if snooze_active else 0.0,
                        "snooze_remaining": float(snooze_remaining if snooze_active else 0.0),
                        "quiet_active": 1.0 if quiet_active else 0.0,
                        "quiet_remaining": float(quiet_remaining if quiet_active else 0.0),
                        "daily_date": daily_date.isoformat(),
                        "daily_prolonged_minutes": round(daily_prolonged_seconds / 60, 2),
                        "daily_break_count": int(daily_break_count),
                        "daily_longest_seated_minutes": round(daily_longest_seated_seconds / 60, 2),
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
                        snooze_minutes=snooze_remaining if snooze_active else None,
                        quiet_minutes=quiet_remaining if quiet_active else None,
                    ),
                    notification=None,
                )

                last_notification_at = None
                was_sleeping = True
                prev_state = ActivityState.SHORT_BREAK
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
            snapshot.metrics["snooze_active"] = 1.0 if snooze_active else 0.0
            snapshot.metrics["snooze_remaining"] = float(snooze_remaining if snooze_active else 0.0)

            probe_pending = float(snapshot.metrics.get("visual_probe_pending", 0.0) or 0.0) >= 0.5
            if probe_pending and vision_adapter is not None:
                await vision_adapter.probe(duration=3.0, interval=0.5)
                engine.mark_visual_probe_fired()
                snapshot = engine.compute_snapshot()

            now = time.time()
            seated_minutes = snapshot.metrics.get("seated_minutes", 0.0)
            break_minutes = snapshot.metrics.get("break_minutes", 0.0)

            if snapshot.state is ActivityState.PROLONGED_SEATED:
                daily_prolonged_seconds += delta

            current_seated_seconds = float(seated_minutes or 0.0) * 60.0
            if current_seated_seconds > daily_longest_seated_seconds:
                daily_longest_seated_seconds = current_seated_seconds

            if (
                snapshot.state is ActivityState.SHORT_BREAK
                and prev_state not in (ActivityState.SHORT_BREAK, None)
            ):
                daily_break_count += 1

            snapshot.metrics["daily_date"] = daily_date.isoformat()
            snapshot.metrics["daily_prolonged_minutes"] = round(daily_prolonged_seconds / 60, 2)
            snapshot.metrics["daily_break_count"] = int(daily_break_count)
            snapshot.metrics["daily_longest_seated_minutes"] = round(
                daily_longest_seated_seconds / 60, 2
            )
            snapshot.metrics["quiet_active"] = 1.0 if quiet_active else 0.0
            snapshot.metrics["quiet_remaining"] = float(quiet_remaining if quiet_active else 0.0)

            if snooze_active and snapshot.state is not ActivityState.PROLONGED_SEATED:
                shared.cancel_snooze()
                snooze_active, snooze_remaining = False, 0.0
                snapshot.metrics["snooze_active"] = 0.0
                snapshot.metrics["snooze_remaining"] = 0.0

            next_reminder_minutes: Optional[float] = None
            notification: Optional[NotificationMessage] = None

            if config.notifications_enabled and not flow_active and not snooze_active and not quiet_active:
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
            elif snooze_active and snapshot.state is ActivityState.PROLONGED_SEATED:
                next_reminder_minutes = snooze_remaining
            elif quiet_active and snapshot.state is ActivityState.PROLONGED_SEATED:
                next_reminder_minutes = quiet_remaining

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
                    snooze_minutes=snooze_remaining if snooze_active else None,
                    quiet_minutes=quiet_remaining if quiet_active else None,
                ),
                notification=notification,
            )

            prev_state = snapshot.state

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
