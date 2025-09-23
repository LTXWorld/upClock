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
        NSAlert,
        NSAlert,
        NSAlertFirstButtonReturn,
        NSAlertSecondButtonReturn,
        NSColor,
        NSFont,
        NSInformationalRequest,
        NSLineBreakByWordWrapping,
        NSMakeRect,
        NSMaxYEdge,
        NSPopover,
        NSPopoverBehaviorTransient,
        NSSlider,
        NSTextField,
        NSView,
        NSViewController,
    )
except Exception:  # pragma: no cover - 测试环境/非 GUI 环境
    objc = None  # type: ignore
    NSApp = None  # type: ignore
    NSAlert = None  # type: ignore
    NSAlertFirstButtonReturn = 1000  # type: ignore
    NSAlertSecondButtonReturn = 1001  # type: ignore
    NSColor = None  # type: ignore
    NSFont = None  # type: ignore
    NSInformationalRequest = 0  # type: ignore
    NSLineBreakByWordWrapping = 0  # type: ignore
    NSMakeRect = None  # type: ignore
    NSMaxYEdge = 0  # type: ignore
    NSPopover = None  # type: ignore
    NSPopoverBehaviorTransient = 0  # type: ignore
    NSSlider = None  # type: ignore
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
    flow_mode_minutes: Optional[float] = None


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


if objc is not None and NSSlider is not None and NSTextField is not None:  # pragma: no cover

    class _FlowSliderDelegate(objc.lookUpClass("NSObject")):
        """帮助更新心流滑块数值显示。"""

        def initWithLabel_(self, label):  # type: ignore[override]
            self = objc.super(_FlowSliderDelegate, self).init()
            if self is None:
                return None
            self._label = label
            return self

        def sliderChanged_(self, sender):  # type: ignore[override]
            value = sender.doubleValue()
            if self._label is not None:
                self._label.setStringValue_(f"{value:.0f} 分钟")

else:  # pragma: no cover - 非 GUI 环境无需滑块

    _FlowSliderDelegate = None  # type: ignore


class StatusBarApp(rumps.App):
    """状态栏应用，周期性读取后台状态。"""

    def __init__(
        self,
        snapshot_provider: Callable[[], Optional[StatusSnapshot]],
        notification_provider: Callable[[], Optional[NotificationMessage]],
        on_system_sleep: Optional[Callable[[], None]] = None,
        on_system_wake: Optional[Callable[[], None]] = None,
        flow_state_provider: Optional[Callable[[], tuple[bool, float]]] = None,
        activate_flow_mode: Optional[Callable[[float], None]] = None,
        cancel_flow_mode: Optional[Callable[[], None]] = None,
    ) -> None:
        _ensure_info_plist()
        super().__init__(name="upClock", title="⌚", quit_button=None)
        self._snapshot_provider = snapshot_provider
        self._notification_provider = notification_provider
        self._on_system_sleep = on_system_sleep
        self._on_system_wake = on_system_wake
        self._flow_state_provider = flow_state_provider
        self._activate_flow_mode = activate_flow_mode
        self._cancel_flow_mode = cancel_flow_mode
        self._banner_popover = None
        self._banner_timer: Optional[rumps.Timer] = None
        self._flow_menu_item = rumps.MenuItem(title="心流模式：关闭", callback=self._handle_flow_mode)
        self.menu = [
            rumps.MenuItem(title="当前状态", callback=None),
            rumps.MenuItem(title="活跃得分", callback=None),
            rumps.MenuItem(title="在座/休息", callback=None),
            rumps.MenuItem(title="下一次提醒", callback=None),
            self._flow_menu_item,
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
        self._update_flow_menu(snapshot.flow_mode_minutes)

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

    def _update_flow_menu(self, remaining: Optional[float]) -> None:
        if self._flow_state_provider is None:
            self._flow_menu_item.title = "心流模式：未配置"
            self._flow_menu_item.set_callback(None)
            return

        self._flow_menu_item.set_callback(self._handle_flow_mode)
        active, provider_remaining = self._flow_state_provider()
        minutes = remaining if remaining is not None else provider_remaining
        if active:
            minutes = max(minutes, 0.0)
            self._flow_menu_item.title = f"心流模式：剩余 {minutes:.1f} 分"
        else:
            self._flow_menu_item.title = "开启心流模式…"

    def _handle_flow_mode(self, _sender: rumps.MenuItem) -> None:
        if self._flow_state_provider is None:
            rumps.alert("未配置心流模式", "当前版本未提供心流模式控制。")
            return

        active, remaining = self._flow_state_provider()
        if active:
            if self._cancel_flow_mode is None:
                return
            if self._confirm_end_flow_mode(remaining):
                try:
                    self._cancel_flow_mode()
                except Exception:
                    rumps.alert("操作失败", "无法结束心流模式，请查看日志。")
            return

        if self._activate_flow_mode is None:
            return

        minutes = self._prompt_flow_duration(default_minutes=60.0)
        if minutes is None:
            return
        try:
            self._activate_flow_mode(minutes)
        except Exception:
            rumps.alert("操作失败", "无法开启心流模式，请查看日志。")

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

    def _prompt_flow_duration(self, default_minutes: float = 60.0) -> Optional[float]:
        """弹出紧凑窗口询问心流模式时长。"""

        if NSAlert is not None and NSSlider is not None and NSTextField is not None and _FlowSliderDelegate is not None:
            alert = NSAlert.alloc().init()
            alert.setMessageText_("开启心流模式")
            alert.setInformativeText_("通过滚轮选择持续时间：")
            alert.addButtonWithTitle_("开始")
            alert.addButtonWithTitle_("取消")

            width = 220.0
            container = NSView.alloc().initWithFrame_(NSMakeRect(0.0, 0.0, width, 70.0))

            value_label = NSTextField.alloc().initWithFrame_(NSMakeRect(0.0, 40.0, width, 22.0))
            value_label.setStringValue_(f"{default_minutes:.0f} 分钟")
            value_label.setEditable_(False)
            value_label.setBordered_(False)
            value_label.setBezeled_(False)
            value_label.setDrawsBackground_(False)
            value_label.setAlignment_(1)  # center

            slider = NSSlider.alloc().initWithFrame_(NSMakeRect(0.0, 10.0, width, 24.0))
            slider.setMinValue_(15.0)
            slider.setMaxValue_(240.0)
            slider.setDoubleValue_(max(15.0, min(240.0, default_minutes)))
            slider.setNumberOfTickMarks_(16)
            slider.setAllowsTickMarkValuesOnly_(True)
            slider.setContinuous_(True)

            delegate = _FlowSliderDelegate.alloc().initWithLabel_(value_label)
            slider.setTarget_(delegate)
            slider.setAction_(objc.selector(_FlowSliderDelegate.sliderChanged_, signature=b"v@:@"))
            delegate.sliderChanged_(slider)
            try:  # 保持引用，防止被 GC
                objc.setAssociatedObject(
                    slider,
                    b"_upclock_flow_delegate",
                    delegate,
                    getattr(objc, "OBJC_ASSOCIATION_RETAIN", 0),
                )
            except Exception:  # pragma: no cover - setAssociatedObject 不可用时忽略
                pass

            container.setAutoresizesSubviews_(True)
            slider.setAutoresizingMask_(2)  # width resizing

            container.addSubview_(value_label)
            container.addSubview_(slider)
            alert.setAccessoryView_(container)

            response = alert.runModal()
            if response not in (NSAlertFirstButtonReturn, 1, 1000):
                return None
            minutes = slider.doubleValue()
            return max(5.0, minutes)

        window = rumps.Window(
            message="设置心流模式时长（分钟）：",
            title="开启心流模式",
            default_text=f"{default_minutes:.0f}",
            ok="开始",
            cancel="取消",
            dimensions=(200, 60),
        )
        window.icon = None
        response = window.run()
        if response.clicked != 1:
            return None
        text = response.text.strip()

        if not text:
            minutes = default_minutes
        else:
            try:
                minutes = float(text)
            except ValueError:
                rumps.alert("输入无效", "请输入数字分钟数，例如 60。")
                return None

        return max(1.0, minutes)

    def _confirm_end_flow_mode(self, remaining: float) -> bool:
        """确认是否结束心流模式。"""

        confirm = rumps.alert(
            "结束心流模式",
            f"心流模式剩余 {remaining:.1f} 分钟，是否提前结束？",
            ok="结束",
            cancel="继续",
        )
        return confirm == 1

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
    flow_state_provider: Optional[Callable[[], tuple[bool, float]]] = None,
    activate_flow_mode: Optional[Callable[[float], None]] = None,
    cancel_flow_mode: Optional[Callable[[], None]] = None,
) -> None:
    app = StatusBarApp(
        snapshot_provider,
        notification_provider,
        on_system_sleep=on_system_sleep,
        on_system_wake=on_system_wake,
        flow_state_provider=flow_state_provider,
        activate_flow_mode=activate_flow_mode,
        cancel_flow_mode=cancel_flow_mode,
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
