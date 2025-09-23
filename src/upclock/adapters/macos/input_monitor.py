"""macOS 键鼠事件监听实现。"""

from __future__ import annotations

import asyncio
import logging
import threading
from typing import Dict, Optional

import Quartz

from upclock.adapters.base import InputAdapter

logger = logging.getLogger(__name__)

_KEYBOARD_EVENT_TYPES = {
    Quartz.kCGEventKeyDown,
    Quartz.kCGEventKeyUp,
    Quartz.kCGEventFlagsChanged,
}
_MOUSE_EVENT_TYPES = {
    Quartz.kCGEventMouseMoved,
    Quartz.kCGEventLeftMouseDown,
    Quartz.kCGEventLeftMouseUp,
    Quartz.kCGEventRightMouseDown,
    Quartz.kCGEventRightMouseUp,
    Quartz.kCGEventOtherMouseDown,
    Quartz.kCGEventOtherMouseUp,
    Quartz.kCGEventLeftMouseDragged,
    Quartz.kCGEventRightMouseDragged,
    Quartz.kCGEventOtherMouseDragged,
}
_SCROLL_EVENT_TYPES = {Quartz.kCGEventScrollWheel}
_ALL_EVENT_TYPES = _KEYBOARD_EVENT_TYPES | _MOUSE_EVENT_TYPES | _SCROLL_EVENT_TYPES


class MacOSInputMonitor(InputAdapter):
    """监听键盘与鼠标活动并写入缓冲区。"""

    def __init__(self, buffer, poll_interval: float = 1.0) -> None:
        super().__init__(buffer)
        self._poll_interval = poll_interval
        self._task: Optional[asyncio.Task[None]] = None
        self._event_thread: Optional[threading.Thread] = None
        self._stop_event = threading.Event()
        self._lock = threading.Lock()
        self._keyboard_events = 0
        self._mouse_events = 0
        self._scroll_events = 0

    async def start(self) -> None:
        """启动事件捕获与指标汇总。"""

        if self._task is not None:
            return

        self._start_event_tap_thread()

        async def _publish_loop() -> None:
            while not self._stop_event.is_set():
                await asyncio.sleep(self._poll_interval)
                metrics = self._drain_metrics()
                if metrics["total_events"] == 0:
                    continue
                logger.debug(
                    "键鼠事件计数：keyboard=%s mouse=%s scroll=%s",
                    metrics["keyboard_events"],
                    metrics["mouse_events"],
                    metrics["scroll_events"],
                )
                self.publish(metrics)

        self._task = asyncio.create_task(_publish_loop())

    def stop(self) -> None:
        """停止事件捕获并关闭循环。"""

        self._stop_event.set()
        if self._task is not None:
            self._task.cancel()
            self._task = None
        if self._event_thread is not None:
            self._event_thread.join(timeout=1.0)
            self._event_thread = None

    def _start_event_tap_thread(self) -> None:
        if self._event_thread is not None:
            return

        def _event_callback(proxy, type_, event, refcon):  # pragma: no cover - 回调由 macOS 调用
            self._handle_event(int(type_))
            return event

        def _run_loop() -> None:
            event_mask = 0
            for event_type in _ALL_EVENT_TYPES:
                event_mask |= Quartz.CGEventMaskBit(event_type)

            tap = Quartz.CGEventTapCreate(
                Quartz.kCGSessionEventTap,
                Quartz.kCGHeadInsertEventTap,
                Quartz.kCGEventTapOptionListenOnly,
                event_mask,
                _event_callback,
                None,
            )

            if tap is None:
                logger.error("创建事件监听失败，可能缺少辅助功能权限")
                self._stop_event.set()
                return

            run_loop_source = Quartz.CFMachPortCreateRunLoopSource(None, tap, 0)
            run_loop = Quartz.CFRunLoopGetCurrent()
            Quartz.CFRunLoopAddSource(run_loop, run_loop_source, Quartz.kCFRunLoopDefaultMode)
            Quartz.CGEventTapEnable(tap, True)

            logger.info("macOS 键鼠监控已启动")
            while not self._stop_event.is_set():
                Quartz.CFRunLoopRunInMode(Quartz.kCFRunLoopDefaultMode, 0.2, True)

            Quartz.CGEventTapEnable(tap, False)
            Quartz.CFRunLoopRemoveSource(run_loop, run_loop_source, Quartz.kCFRunLoopDefaultMode)
            logger.info("macOS 键鼠监控已停止")

        self._event_thread = threading.Thread(target=_run_loop, name="upclock-input-tap", daemon=True)
        self._event_thread.start()

    def _handle_event(self, event_type: int) -> None:
        with self._lock:
            if event_type in _KEYBOARD_EVENT_TYPES:
                self._keyboard_events += 1
            elif event_type in _MOUSE_EVENT_TYPES:
                self._mouse_events += 1
            elif event_type in _SCROLL_EVENT_TYPES:
                self._scroll_events += 1

    def _drain_metrics(self) -> Dict[str, float]:
        with self._lock:
            keyboard = self._keyboard_events
            mouse = self._mouse_events
            scroll = self._scroll_events
            self._keyboard_events = 0
            self._mouse_events = 0
            self._scroll_events = 0

        total = keyboard + mouse + scroll
        return {
            "keyboard_events": float(keyboard),
            "mouse_events": float(mouse),
            "scroll_events": float(scroll),
            "total_events": float(total),
            "keyboard_mouse_activity": float(total),
        }
