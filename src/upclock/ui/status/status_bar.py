"""基于 rumps 的 macOS 状态栏应用原型。"""

from __future__ import annotations

import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Optional

import rumps

try:  # pragma: no cover - 仅在 macOS GUI 环境下可用
    import objc  # type: ignore
    from Cocoa import (  # type: ignore
        NSApp,
        NSColor,
        NSFont,
        NSInformationalRequest,
        NSLineBreakByWordWrapping,
        NSMakeRect,
        NSMaxYEdge,
        NSPopover,
        NSPopoverBehaviorTransient,
        NSTextField,
        NSView,
        NSViewController,
    )
except Exception:  # pragma: no cover - 测试环境/非 GUI 环境
    objc = None  # type: ignore
    NSApp = None  # type: ignore
    NSColor = None  # type: ignore
    NSFont = None  # type: ignore
    NSInformationalRequest = 0  # type: ignore
    NSLineBreakByWordWrapping = 0  # type: ignore
    NSMakeRect = None  # type: ignore
    NSMaxYEdge = 0  # type: ignore
    NSPopover = None  # type: ignore
    NSPopoverBehaviorTransient = 0  # type: ignore
    NSTextField = None  # type: ignore
    NSView = None  # type: ignore
    NSViewController = None  # type: ignore

from upclock.core.activity_engine import ActivitySnapshot, ActivityState


@dataclass
class StatusSnapshot:
    """供状态栏显示的数据。"""

    state: Optional[ActivityState]
    score: float
    seated_minutes: float
    break_minutes: float
    updated_at: float
    next_reminder_minutes: Optional[float] = None


@dataclass
class NotificationMessage:
    """状态栏要显示的提醒消息。"""

    title: str
    subtitle: str
    body: str


if NSViewController is not None and objc is not None:  # pragma: no cover - GUI 逻辑无需测试

    class _TransientPopoverController(NSViewController):
        """用于渲染短暂提醒内容的简单视图控制器。"""

        def initWithMessage_(self, message: str):  # type: ignore[override]
            self = objc.super(_TransientPopoverController, self).init()
            if self is None:
                return None

            width, height = 280.0, 72.0
            view = NSView.alloc().initWithFrame_(NSMakeRect(0.0, 0.0, width, height))

            field = NSTextField.alloc().initWithFrame_(NSMakeRect(12.0, 12.0, width - 24.0, height - 24.0))
            field.setStringValue_(message)
            field.setEditable_(False)
            field.setBordered_(False)
            field.setBezeled_(False)
            field.setDrawsBackground_(False)
            field.setSelectable_(False)
            if NSFont is not None:
                field.setFont_(NSFont.systemFontOfSize_(13.0))
            if NSColor is not None and hasattr(NSColor, "labelColor"):
                field.setTextColor_(NSColor.labelColor())
            field.setLineBreakMode_(NSLineBreakByWordWrapping)

            view.addSubview_(field)
            self.view = view
            return self

else:  # pragma: no cover - 非 GUI 环境无需控制器

    class _TransientPopoverController:  # type: ignore[override]
        def alloc(self):  # type: ignore[misc]
            return self

        def initWithMessage_(self, _message: str):  # type: ignore[override]
            return self


class StatusBarApp(rumps.App):
    """状态栏应用，周期性读取后台状态。"""

    def __init__(
        self,
        snapshot_provider: Callable[[], Optional[StatusSnapshot]],
        notification_provider: Callable[[], Optional[NotificationMessage]],
        on_system_sleep: Optional[Callable[[], None]] = None,
        on_system_wake: Optional[Callable[[], None]] = None,
    ) -> None:
        _ensure_info_plist()
        super().__init__(name="upClock", title="⌚", quit_button=None)
        self._snapshot_provider = snapshot_provider
        self._notification_provider = notification_provider
        self._on_system_sleep = on_system_sleep
        self._on_system_wake = on_system_wake
        self._banner_popover = None
        self._banner_timer: Optional[rumps.Timer] = None
        self.menu = [
            rumps.MenuItem(title="当前状态", callback=None),
            rumps.MenuItem(title="活跃得分", callback=None),
            rumps.MenuItem(title="在座/休息", callback=None),
            rumps.MenuItem(title="下一次提醒", callback=None),
            None,
            rumps.MenuItem("打开仪表盘", callback=self._open_dashboard),
            rumps.MenuItem("退出", callback=self._quit_app),
        ]
        self._poll_timer = rumps.Timer(self._refresh, 2.0)
        self._last_snapshot: Optional[StatusSnapshot] = None
        if self._on_system_sleep or self._on_system_wake:
            self._register_power_events()

    def run(self, *args, **kwargs):  # type: ignore[override]
        self._poll_timer.start()
        super().run(*args, **kwargs)

    def _refresh(self, _timer: rumps.Timer) -> None:
        snapshot = self._snapshot_provider()
        if snapshot is None:
            return

        self._last_snapshot = snapshot
        self.title = self._title_for_state(snapshot.state)
        state_name = self._state_label(snapshot.state)
        self.menu["当前状态"].title = f"状态：{state_name}"
        self.menu["活跃得分"].title = f"活跃得分：{snapshot.score:.2f}"
        self.menu["在座/休息"].title = f"在座：{snapshot.seated_minutes:.1f} 分钟 / 休息：{snapshot.break_minutes:.1f}"
        if "下一次提醒" in self.menu:
            if snapshot.next_reminder_minutes is None:
                self.menu["下一次提醒"].title = "下一次提醒：--"
            else:
                self.menu["下一次提醒"].title = (
                    f"下一次提醒：{max(0.0, snapshot.next_reminder_minutes):.1f} 分钟"
                )

        notification = self._notification_provider()
        if notification is not None:
            self._show_notification(notification)

    def _title_for_state(self, state: Optional[ActivityState]) -> str:
        if state is ActivityState.PROLONGED_SEATED:
            return "💥"
        if state is ActivityState.SHORT_BREAK:
            return "☕"
        return "👨🏻‍💻"

    def _show_notification(self, message: NotificationMessage) -> None:
        rumps.notification(message.title, message.subtitle, message.body)
        self._bounce_icon()
        self._show_transient_banner(message.body)

    def _state_label(self, state: Optional[ActivityState]) -> str:
        mapping = {
            ActivityState.ACTIVE: "活跃",
            ActivityState.SHORT_BREAK: "短暂休息",
            ActivityState.PROLONGED_SEATED: "久坐",
        }
        if state is None:
            return "未知"
        return mapping.get(state, state.name)

    def _open_dashboard(self, _sender: rumps.MenuItem) -> None:
        import webbrowser

        webbrowser.open("http://127.0.0.1:8000/")

    def _quit_app(self, _sender: rumps.MenuItem) -> None:
        rumps.quit_application()

    def _bounce_icon(self) -> None:
        if NSApp is None:  # pragma: no cover - 非 GUI 环境无需处理
            return
        try:
            app = NSApp()
            if app is not None:
                app.requestUserAttention_(NSInformationalRequest)
        except Exception:  # pragma: no cover - 请求失败时忽略
            rumps.logger.debug("状态栏弹跳请求失败", exc_info=True)

    def _register_power_events(self) -> None:
        try:
            import rumps.events as events
        except Exception:  # pragma: no cover - rumps 版本不支持事件
            return

        if self._on_system_sleep is not None:
            events.on_sleep(self._handle_system_sleep)
        if self._on_system_wake is not None:
            events.on_wake(self._handle_system_wake)

    def _handle_system_sleep(self, *_args, **_kwargs) -> None:
        if self._on_system_sleep is not None:
            try:
                self._on_system_sleep()
            except Exception:  # pragma: no cover - 回调异常不影响主循环
                rumps.logger.error("处理系统休眠事件失败", exc_info=True)

    def _handle_system_wake(self, *_args, **_kwargs) -> None:
        if self._on_system_wake is not None:
            try:
                self._on_system_wake()
            except Exception:  # pragma: no cover
                rumps.logger.error("处理系统唤醒事件失败", exc_info=True)

    def _show_transient_banner(self, text: str) -> None:
        """在状态栏图标下方短暂展示提醒文本。"""

        if NSPopover is None or NSViewController is None or objc is None:
            return

        status_app = getattr(self, "_nsapp", None)
        if status_app is None:
            return

        status_item = getattr(status_app, "nsstatusitem", None)
        if status_item is None:
            return

        button = None
        try:
            button = status_item.button()
        except Exception:  # pragma: no cover - 旧系统可能没有 button 接口
            button = None

        if button is None:
            return

        self._close_transient_banner()

        try:
            controller = _TransientPopoverController.alloc().initWithMessage_(text)
            popover = NSPopover.alloc().init()
            popover.setContentViewController_(controller)
            popover.setAnimates_(True)
            if NSPopoverBehaviorTransient:
                popover.setBehavior_(NSPopoverBehaviorTransient)
            popover.showRelativeToRect_ofView_preferredEdge_(button.bounds(), button, NSMaxYEdge)
            self._banner_popover = popover
            self._banner_timer = rumps.Timer(self._close_transient_banner, 4.0)
            self._banner_timer.start()
        except Exception:  # pragma: no cover - GUI 相关异常直接忽略
            rumps.logger.debug("短暂通知显示失败", exc_info=True)

    def _close_transient_banner(self, _timer: Optional[rumps.Timer] = None) -> None:
        if self._banner_timer is not None:
            if _timer is None or _timer is not self._banner_timer:
                try:
                    self._banner_timer.stop()
                except Exception:  # pragma: no cover - Timer 停止失败可忽略
                    rumps.logger.debug("短暂通知计时器停止失败", exc_info=True)
            self._banner_timer = None

        if self._banner_popover is not None:
            try:
                self._banner_popover.performClose_(None)
            except Exception:  # pragma: no cover - 关闭失败无需终止程序
                rumps.logger.debug("短暂通知关闭失败", exc_info=True)
            self._banner_popover = None


def run_status_bar_app(
    snapshot_provider: Callable[[], Optional[StatusSnapshot]],
    notification_provider: Callable[[], Optional[NotificationMessage]],
    on_system_sleep: Optional[Callable[[], None]] = None,
    on_system_wake: Optional[Callable[[], None]] = None,
) -> None:
    app = StatusBarApp(
        snapshot_provider,
        notification_provider,
        on_system_sleep=on_system_sleep,
        on_system_wake=on_system_wake,
    )
    app.run()


def _ensure_info_plist() -> None:
    """确保可执行目录存在 Info.plist 以支持通知。"""

    executable = Path(sys.executable)
    plist_path = executable.with_name("Info.plist")
    if plist_path.exists():
        return

    plist_contents = """<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>CFBundleIdentifier</key>
    <string>com.upclock.agent</string>
    <key>CFBundleName</key>
    <string>upClock</string>
</dict>
</plist>
"""

    try:
        plist_path.write_text(plist_contents, encoding="utf-8")
    except Exception as exc:  # pragma: no cover - IO 失败
        rumps.logger.warning(f"无法写入 Info.plist: {exc}")
