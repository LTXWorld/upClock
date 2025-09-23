import Quartz

from upclock.core.signal_buffer import SignalBuffer
from upclock.adapters.macos.input_monitor import MacOSInputMonitor


def test_input_monitor_drain_metrics_counts_events() -> None:
    buffer = SignalBuffer()
    monitor = MacOSInputMonitor(buffer, poll_interval=0.1)

    monitor._handle_event(Quartz.kCGEventKeyDown)
    monitor._handle_event(Quartz.kCGEventMouseMoved)
    monitor._handle_event(Quartz.kCGEventScrollWheel)

    metrics = monitor._drain_metrics()

    assert metrics["keyboard_events"] == 1.0
    assert metrics["mouse_events"] == 1.0
    assert metrics["scroll_events"] == 1.0
    assert metrics["total_events"] == 3.0
    assert metrics["keyboard_mouse_activity"] == 3.0
