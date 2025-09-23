import datetime as dt

from upclock.config import AppConfig, WindowCategory
from upclock.core.activity_engine import ActivityEngine, ActivitySnapshot, ActivityState
from upclock.core.signal_buffer import SignalBuffer, SignalRecord


def _fixed_now() -> dt.datetime:
    return dt.datetime(2024, 1, 1, 12, 0, 0)


def _config() -> AppConfig:
    return AppConfig(
        short_break_minutes=1,
        break_reset_minutes=1,
        prolonged_seated_minutes=5,
        window_categories=[WindowCategory(name="work", weight=1.0)],
    )


def test_activity_engine_active_with_recent_events() -> None:
    buffer = SignalBuffer()
    buffer.append(
        SignalRecord(
            timestamp=_fixed_now() - dt.timedelta(seconds=30),
            values={"keyboard_mouse_activity": 25.0, "total_events": 25.0},
        )
    )

    engine = ActivityEngine(buffer, config=_config())
    engine._now = _fixed_now  # type: ignore[method-assign]
    snapshot = engine.compute_snapshot()

    assert snapshot.state is ActivityState.ACTIVE
    assert isinstance(snapshot, ActivitySnapshot)
    assert snapshot.metrics["seated_minutes"] < 1
    assert snapshot.metrics["break_minutes"] < 1
    assert snapshot.score > 0


def test_activity_engine_prolonged_when_seated_long_time() -> None:
    buffer = SignalBuffer()
    buffer.append(
        SignalRecord(
            timestamp=_fixed_now() - dt.timedelta(seconds=10),
            values={"keyboard_mouse_activity": 15.0, "total_events": 15.0},
        )
    )

    engine = ActivityEngine(buffer, config=_config())
    engine._seated_started_at = _fixed_now() - dt.timedelta(minutes=10)
    engine._now = _fixed_now  # type: ignore[method-assign]
    snapshot = engine.compute_snapshot()

    assert snapshot.state is ActivityState.PROLONGED_SEATED
    assert snapshot.metrics["seated_minutes"] >= 10
    assert snapshot.score == 0.0


def test_activity_engine_short_break_after_inactivity() -> None:
    buffer = SignalBuffer()
    buffer.append(
        SignalRecord(
            timestamp=_fixed_now() - dt.timedelta(minutes=5),
            values={"keyboard_mouse_activity": 10.0, "total_events": 10.0},
        )
    )

    engine = ActivityEngine(buffer, config=_config())
    engine._now = _fixed_now  # type: ignore[method-assign]
    snapshot = engine.compute_snapshot()

    assert snapshot.state is ActivityState.SHORT_BREAK
    assert snapshot.metrics["break_minutes"] >= 5


def test_activity_engine_keeps_active_when_vision_uncertain() -> None:
    buffer = SignalBuffer()
    buffer.append(
        SignalRecord(
            timestamp=_fixed_now() - dt.timedelta(seconds=5),
            values={"presence_confidence": 0.2, "posture_state": "unknown"},
        )
    )
    buffer.append(
        SignalRecord(
            timestamp=_fixed_now() - dt.timedelta(seconds=2),
            values={"keyboard_mouse_activity": 10.0, "total_events": 10.0},
        )
    )

    engine = ActivityEngine(buffer, config=_config())
    engine._now = _fixed_now  # type: ignore[method-assign]
    snapshot = engine.compute_snapshot()

    assert snapshot.state is ActivityState.ACTIVE
    assert snapshot.metrics["break_minutes"] < 1
