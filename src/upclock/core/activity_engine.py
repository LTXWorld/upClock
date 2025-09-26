"""活动评分引擎与状态管理。"""

from __future__ import annotations

import datetime as dt
from dataclasses import dataclass
from enum import Enum, auto
from typing import Dict, List, Optional, Protocol, Union

from upclock.config import AppConfig
from upclock.core.signal_buffer import SignalBuffer, SignalRecord


class ActivityState(Enum):
    """用户活动状态枚举。"""

    ACTIVE = auto()
    SHORT_BREAK = auto()
    PROLONGED_SEATED = auto()


@dataclass
class ActivitySnapshot:
    """聚合后的活动快照。"""

    score: float
    state: ActivityState
    metrics: Dict[str, Union[float, str]]
    flow_mode_remaining: Optional[float] = None


class SignalBufferReader(Protocol):
    """信号缓存读取接口，用于供引擎消费。"""

    def snapshot(self) -> List[SignalRecord]:
        """返回当前信号快照。"""


class ActivityEngine:
    """根据缓冲信号计算用户在座情况。"""

    def __init__(self, buffer: SignalBufferReader, config: Optional[AppConfig] = None) -> None:
        self._buffer = buffer
        self._config = config or AppConfig.load_default()
        window_minutes = max(1, min(self._config.short_break_minutes, 5))
        self._activity_window = dt.timedelta(minutes=window_minutes)
        self._baseline_activity = max(self._activity_window.total_seconds() / 6, 20.0)
        self._seated_started_at: Optional[dt.datetime] = None
        self._visual_probe_requested_at: Optional[dt.datetime] = None
        self._visual_probe_triggered_at: Optional[dt.datetime] = None
        self._visual_probe_cooldown = dt.timedelta(seconds=120)
        self._visual_probe_window = dt.timedelta(seconds=90)

    def compute_snapshot(self) -> ActivitySnapshot:
        now = self._now()
        records = self._buffer.snapshot()
        if not records:
            return ActivitySnapshot(
                score=0.0,
                state=ActivityState.SHORT_BREAK,
                metrics={
                    "seated_minutes": 0.0,
                    "break_minutes": float(self._config.break_reset_minutes),
                    "normalized_activity": 0.0,
                    "activity_sum": 0.0,
                    "score": 0.0,
                },
            )

        recent_records = [r for r in records if now - r.timestamp <= self._activity_window]
        activity_sum = 0.0
        has_recent_keyboard_mouse = False
        for record in recent_records:
            value = record.values.get("keyboard_mouse_activity")
            if value is None:
                value = record.values.get("total_events", 0.0)
            try:
                numeric = float(value)
            except (TypeError, ValueError):
                numeric = 0.0
            if numeric > 0.0:
                has_recent_keyboard_mouse = True
            activity_sum += max(0.0, numeric)
        normalized_activity = min(activity_sum / self._baseline_activity, 1.0) if activity_sum else 0.0

        last_activity_at = self._last_activity_time(records)
        if last_activity_at is None:
            last_activity_at = records[-1].timestamp

        presence = self._latest_presence(records)
        presence_confidence = presence.confidence if presence else None

        vision_signal = None
        if presence is not None:
            if presence.posture_state != "untracked" and presence.confidence > 0.05:
                vision_signal = presence

        break_minutes = max(0.0, (now - last_activity_at).total_seconds() / 60)

        if (
            vision_signal is not None
            and vision_signal.confidence < self._config.vision_presence_threshold
            and not has_recent_keyboard_mouse
        ):
            break_minutes = max(break_minutes, float(self._config.break_reset_minutes))

        seated_minutes = self._update_seated_timer(now, last_activity_at, break_minutes)

        state = self._resolve_state(seated_minutes, break_minutes)

        self._update_visual_probe_state(
            now=now,
            seated_minutes=seated_minutes,
            break_minutes=break_minutes,
            state=state,
            presence_confidence=presence_confidence or 0.0,
            posture_state=presence.posture_state if presence else "unknown",
        )

        posture_score = vision_signal.posture_score if vision_signal else 1.0
        score = self._compute_score(seated_minutes, normalized_activity, posture_score)

        metrics: Dict[str, Union[float, str]] = {
            "activity_sum": float(activity_sum),
            "normalized_activity": float(normalized_activity),
            "seated_minutes": float(seated_minutes),
            "break_minutes": float(break_minutes),
            "presence_confidence": float(presence_confidence or 0.0),
            "posture_score": float(posture_score),
            "posture_state": presence.posture_state if presence else "unknown",
            "score": float(score),
            "visual_probe_pending": 1.0 if self._should_request_visual_probe(now) else 0.0,
        }

        return ActivitySnapshot(score=score, state=state, metrics=metrics)

    def should_trigger_visual_probe(self, now: Optional[dt.datetime] = None) -> bool:
        now = now or self._now()
        return self._should_request_visual_probe(now)

    def _should_request_visual_probe(self, now: dt.datetime) -> bool:
        if self._visual_probe_requested_at is None:
            return False
        if (
            self._visual_probe_triggered_at is not None
            and self._visual_probe_triggered_at >= self._visual_probe_requested_at
        ):
            return False
        if now - self._visual_probe_requested_at > self._visual_probe_window:
            return False
        return True

    def mark_visual_probe_fired(self, now: Optional[dt.datetime] = None) -> None:
        if self._visual_probe_requested_at is None:
            return
        self._visual_probe_triggered_at = now or self._now()

    def reset_state(self) -> None:
        """重置内部计时器，适用于系统休眠或手动清零场景。"""

        self._seated_started_at = None
        self._visual_probe_requested_at = None
        self._visual_probe_triggered_at = None

    def _update_seated_timer(
        self, now: dt.datetime, last_activity_at: dt.datetime, break_minutes: float
    ) -> float:
        if break_minutes >= self._config.break_reset_minutes:
            self._seated_started_at = None
            return 0.0

        if self._seated_started_at is None:
            self._seated_started_at = last_activity_at

        seated_minutes = max(0.0, (now - self._seated_started_at).total_seconds() / 60)
        return seated_minutes

    def _last_activity_time(self, records: List[SignalRecord]) -> Optional[dt.datetime]:
        """返回最近一次可视为“主动交互”的时间。

        键鼠事件优先；若长时间无键鼠输入，则当视觉置信度满足阈值时，
        也视为用户仍在座位上（例如阅读或观看视频），避免误判为休息。
        """

        for record in reversed(records):
            total = record.values.get("keyboard_mouse_activity") or record.values.get("total_events")
            if total and total > 0:
                return record.timestamp

            presence_conf = record.values.get("presence_confidence")
            if presence_conf is None:
                continue

            try:
                confidence = float(presence_conf)
            except (TypeError, ValueError):
                continue

            if confidence < self._config.vision_presence_threshold:
                continue

            presence_state = record.values.get("presence_state")
            if presence_state is not None:
                try:
                    present = float(presence_state) >= 0.5
                except (TypeError, ValueError):
                    present = False
                if not present:
                    continue

            # 缓冲中未提供 presence_state 时，仅凭置信度也视为仍在座位
            return record.timestamp
        return None

    def _resolve_state(self, seated_minutes: float, break_minutes: float) -> ActivityState:
        if break_minutes >= self._config.break_reset_minutes:
            return ActivityState.SHORT_BREAK
        if seated_minutes >= self._config.prolonged_seated_minutes:
            return ActivityState.PROLONGED_SEATED
        return ActivityState.ACTIVE
    def _update_visual_probe_state(
        self,
        now: dt.datetime,
        seated_minutes: float,
        break_minutes: float,
        state: ActivityState,
        presence_confidence: float,
        posture_state: str,
    ) -> None:
        if state is ActivityState.PROLONGED_SEATED:
            return

        prolonged_seconds = self._config.prolonged_seated_minutes * 60
        seated_seconds = seated_minutes * 60
        break_seconds = break_minutes * 60

        if break_seconds >= self._config.break_reset_minutes * 60:
            self._visual_probe_requested_at = None
            self._visual_probe_triggered_at = None
            return

        threshold_seconds = prolonged_seconds * 0.95
        if seated_seconds < threshold_seconds:
            self._visual_probe_requested_at = None
            self._visual_probe_triggered_at = None
            return

        if presence_confidence >= self._config.vision_presence_threshold and posture_state != "untracked":
            self._visual_probe_requested_at = None
            self._visual_probe_triggered_at = None
            return

        if self._visual_probe_requested_at is not None:
            elapsed = now - self._visual_probe_requested_at
            if elapsed <= self._visual_probe_window:
                return
            if elapsed <= self._visual_probe_cooldown:
                return

        self._visual_probe_requested_at = now
        self._visual_probe_triggered_at = None


    def _compute_score(
        self, seated_minutes: float, normalized_activity: float, posture_score: float
    ) -> float:
        ratio = min(seated_minutes / max(self._config.prolonged_seated_minutes, 1), 1.0)
        modifier = posture_score if posture_score > 0 else 0.5
        return round((1.0 - ratio) * normalized_activity * modifier, 4)

    def _now(self) -> dt.datetime:
        return dt.datetime.utcnow()

    def update_config(self, config: AppConfig) -> None:
        """更新配置参数。"""

        self._config = config

    @dataclass
    class _Presence:
        timestamp: dt.datetime
        confidence: float
        posture_score: float
        posture_state: str

    def _latest_presence(self, records: List[SignalRecord]) -> Optional["ActivityEngine._Presence"]:
        for record in reversed(records):
            if "presence_confidence" in record.values:
                return ActivityEngine._Presence(
                    timestamp=record.timestamp,
                    confidence=float(record.values.get("presence_confidence", 0.0)),
                    posture_score=float(record.values.get("posture_score", 0.0)),
                    posture_state=str(record.values.get("posture_state", "unknown")),
                )
        return None
