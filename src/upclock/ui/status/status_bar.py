"""基于 rumps 的 macOS 状态栏应用原型。"""

from __future__ import annotations

import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Optional

import rumps

try:  # pragma: no cover - 仅在 macOS GUI 环境下可用
    import objc  # type: ignore
    from Cocoa import (  # type: ignore
        NSApp,
        NSAlert,
        NSAlertFirstButtonReturn,
        NSAlertSecondButtonReturn,
        NSButton,
        NSColor,
        NSFont,
        NSImage,
        NSInformationalRequest,
        NSLineBreakByWordWrapping,
        NSMakeRect,
        NSMakeSize,
        NSMaxYEdge,
        NSPanel,
        NSPopover,
        NSPopoverBehaviorTransient,
        NSSlider,
        NSTextField,
        NSView,
        NSViewController,
        NSWindowStyleMaskTitled,
        NSWindowStyleMaskClosable,
    )
    from Foundation import (  # type: ignore
        NSUserNotification,
        NSUserNotificationCenter,
        NSUserNotificationDefaultSoundName,
    )
except Exception:  # pragma: no cover - 测试环境/非 GUI 环境
    objc = None  # type: ignore
    NSApp = None  # type: ignore
    NSAlert = None  # type: ignore
    NSAlertFirstButtonReturn = 1000  # type: ignore
    NSAlertSecondButtonReturn = 1001  # type: ignore
    NSButton = None  # type: ignore
    NSColor = None  # type: ignore
    NSFont = None  # type: ignore
    NSImage = None  # type: ignore
    NSInformationalRequest = 0  # type: ignore
    NSLineBreakByWordWrapping = 0  # type: ignore
    NSMakeRect = None  # type: ignore
    NSMakeSize = None  # type: ignore
    NSMaxYEdge = 0  # type: ignore
    NSPanel = None  # type: ignore
    NSPopover = None  # type: ignore
    NSPopoverBehaviorTransient = 0  # type: ignore
    NSSlider = None  # type: ignore
    NSTextField = None  # type: ignore
    NSView = None  # type: ignore
    NSViewController = None  # type: ignore
    NSWindowStyleMaskTitled = 0  # type: ignore
    NSWindowStyleMaskClosable = 0  # type: ignore
    NSUserNotification = None  # type: ignore
    NSUserNotificationCenter = None  # type: ignore
    NSUserNotificationDefaultSoundName = None  # type: ignore

from upclock.config_store import UserSettings
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
    snooze_minutes: Optional[float] = None
    quiet_minutes: Optional[float] = None
    context_mode: Optional[str] = None
    context_message: Optional[str] = None
    context_remaining_minutes: Optional[float] = None


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


if objc is not None and NSUserNotificationCenter is not None:  # pragma: no cover

    class _NotificationCenterDelegate(objc.lookUpClass("NSObject")):
        """保证应用前台时仍可展示系统通知。"""

        def userNotificationCenter_shouldPresentNotification_(self, _center, _notification):  # type: ignore[override]
            return True

else:  # pragma: no cover - 非 GUI 环境无需通知代理

    _NotificationCenterDelegate = None  # type: ignore


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
        snooze_state_provider: Optional[Callable[[], tuple[bool, float]]] = None,
        activate_snooze: Optional[Callable[[float], None]] = None,
        cancel_snooze: Optional[Callable[[], None]] = None,
        settings_provider: Optional[Callable[[], Optional[UserSettings]]] = None,
        update_settings: Optional[Callable[[UserSettings], None]] = None,
        refresh_callback: Optional[Callable[[], None]] = None,
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
        self._snooze_state_provider = snooze_state_provider
        self._activate_snooze = activate_snooze
        self._cancel_snooze = cancel_snooze
        self._settings_provider = settings_provider
        self._update_settings = update_settings
        self._refresh_callback = refresh_callback
        self._notification_delegate_ref = None
        self._banner_popover = None
        self._banner_timer: Optional[rumps.Timer] = None
        self._flow_menu_item = rumps.MenuItem(title="心流模式：关闭", callback=self._handle_flow_mode)
        self._context_item = rumps.MenuItem("提醒模式：正常", callback=None)
        self._snooze_menu = rumps.MenuItem("延后提醒")
        self._snooze_5 = rumps.MenuItem("延后 5 分钟", lambda _: self._handle_snooze(5))
        self._snooze_15 = rumps.MenuItem("延后 15 分钟", lambda _: self._handle_snooze(15))
        self._snooze_30 = rumps.MenuItem("延后 30 分钟", lambda _: self._handle_snooze(30))
        self._cancel_snooze_item = rumps.MenuItem("取消延后", self._handle_cancel_snooze)
        self._snooze_menu.add(self._snooze_5)
        self._snooze_menu.add(self._snooze_15)
        self._snooze_menu.add(self._snooze_30)
        self._snooze_menu.add(self._cancel_snooze_item)
        self._settings_item = rumps.MenuItem("提醒设置…", self._handle_open_settings)
        self._refresh_item = rumps.MenuItem("刷新久坐计时", self._handle_manual_refresh)
        self.menu = [
            rumps.MenuItem(title="当前状态", callback=None),
            rumps.MenuItem(title="专注指数", callback=None),
            rumps.MenuItem(title="在座/休息", callback=None),
            rumps.MenuItem(title="下一次提醒", callback=None),
            self._context_item,
            self._refresh_item,
            self._flow_menu_item,
            self._snooze_menu,
            self._settings_item,
            None,
            rumps.MenuItem("打开仪表盘", callback=self._open_dashboard),
            rumps.MenuItem("退出", callback=self._quit_app),
        ]
        self._poll_timer = rumps.Timer(self._refresh, 2.0)
        self._last_snapshot: Optional[StatusSnapshot] = None
        if self._on_system_sleep or self._on_system_wake:
            self._register_power_events()
        self._ensure_notification_delegate()

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
        focus_percent = max(0.0, min(100.0, snapshot.score * 100.0))
        self.menu["专注指数"].title = f"专注指数：{focus_percent:.0f}%"
        self.menu["在座/休息"].title = f"在座：{snapshot.seated_minutes:.1f} 分钟 / 休息：{snapshot.break_minutes:.1f}"
        if "下一次提醒" in self.menu:
            if snapshot.quiet_minutes is not None:
                label = f"静默中：{max(0.0, snapshot.quiet_minutes):.1f} 分"
            elif snapshot.snooze_minutes is not None:
                label = f"延后：{max(0.0, snapshot.snooze_minutes):.1f} 分"
            elif snapshot.flow_mode_minutes is not None:
                label = f"心流：{max(0.0, snapshot.flow_mode_minutes):.1f} 分"
            elif snapshot.next_reminder_minutes is not None:
                label = f"下一次提醒：{max(0.0, snapshot.next_reminder_minutes):.1f} 分"
            else:
                label = "下一次提醒：--"
            self.menu["下一次提醒"].title = label
        if snapshot.context_mode:
            remaining = ""
            if snapshot.context_remaining_minutes is not None:
                remaining = f" · 剩余 {max(0.0, snapshot.context_remaining_minutes):.1f} 分"
            message = snapshot.context_message or "提醒已静音"
            if snapshot.context_mode == "meeting":
                prefix = "会议模式"
            elif snapshot.context_mode == "presentation":
                prefix = "演示模式"
            elif snapshot.context_mode == "post_meeting_pending":
                prefix = "善后提醒待发送"
            else:
                prefix = "提醒模式"
            self._context_item.title = f"{prefix}：{message}{remaining}"
        else:
            self._context_item.title = "提醒模式：正常"
        self._update_flow_menu(snapshot.flow_mode_minutes)
        self._update_snooze_menu(snapshot.snooze_minutes)

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
        delivered = self._deliver_user_notification(message)
        if not delivered:
            rumps.notification(message.title, message.subtitle, message.body)
        self._bounce_icon()
        if not delivered:
            self._show_transient_banner(message.body)

    def _deliver_user_notification(self, message: NotificationMessage) -> bool:
        if NSUserNotificationCenter is None or NSUserNotification is None:
            return False
        try:
            center = NSUserNotificationCenter.defaultUserNotificationCenter()
            notification = NSUserNotification.alloc().init()
            title = message.title or "upClock 提醒"
            notification.setTitle_(title)
            if message.subtitle:
                notification.setSubtitle_(message.subtitle)
            body = message.body or ""
            notification.setInformativeText_(body)
            if NSUserNotificationDefaultSoundName is not None:
                notification.setSoundName_(NSUserNotificationDefaultSoundName)
            else:
                notification.setSoundName_("NSUserNotificationDefaultSoundName")
            identifier = f"upclock-{time.time()}"
            if hasattr(notification, "setIdentifier_"):
                notification.setIdentifier_(identifier)
            if hasattr(notification, "setHasActionButton_"):
                notification.setHasActionButton_(False)
            center.deliverNotification_(notification)
            return True
        except Exception:
            rumps.logger.error("系统通知发送失败", exc_info=True)
            return False

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

    def _ensure_notification_delegate(self) -> None:
        if NSUserNotificationCenter is None or _NotificationCenterDelegate is None:
            return
        if self._notification_delegate_ref is not None:
            return
        try:
            center = NSUserNotificationCenter.defaultUserNotificationCenter()
            delegate = _NotificationCenterDelegate.alloc().init()
            center.setDelegate_(delegate)
            self._notification_delegate_ref = delegate
        except Exception:  # pragma: no cover - 设置失败时忽略
            self._notification_delegate_ref = None

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

    def _update_snooze_menu(self, remaining: Optional[float]) -> None:
        if self._snooze_state_provider is None:
            self._snooze_menu.title = "延后提醒：未配置"
            for item in (self._snooze_5, self._snooze_15, self._snooze_30, self._cancel_snooze_item):
                item.set_callback(None)
            return

        self._snooze_5.set_callback(lambda _: self._handle_snooze(5))
        self._snooze_15.set_callback(lambda _: self._handle_snooze(15))
        self._snooze_30.set_callback(lambda _: self._handle_snooze(30))

        active, provider_remaining = self._snooze_state_provider()
        minutes = remaining if remaining is not None else provider_remaining
        if active:
            minutes = max(minutes, 0.0)
            self._snooze_menu.title = f"延后提醒：剩余 {minutes:.1f} 分"
            self._cancel_snooze_item.title = "取消延后"
            self._cancel_snooze_item.set_callback(self._handle_cancel_snooze)
        else:
            self._snooze_menu.title = "延后提醒"
            self._cancel_snooze_item.title = "取消延后 (无)"
            self._cancel_snooze_item.set_callback(lambda _: None)

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

    def _handle_snooze(self, minutes: float) -> None:
        if self._activate_snooze is None:
            rumps.alert("未配置延后提醒", "当前版本未提供延后提醒控制。")
            return
        try:
            self._activate_snooze(minutes)
        except Exception:
            rumps.alert("操作失败", "无法设置延后提醒，请查看日志。")

    def _handle_cancel_snooze(self, _sender: rumps.MenuItem) -> None:
        if self._cancel_snooze is None:
            return
        if self._snooze_state_provider is not None:
            active, _remaining = self._snooze_state_provider()
            if not active:
                rumps.alert("当前无延后提醒", "没有待取消的延后提醒。")
                return
        try:
            self._cancel_snooze()
        except Exception:
            rumps.alert("操作失败", "无法取消延后提醒，请查看日志。")

    def _handle_open_settings(self, _sender: rumps.MenuItem) -> None:
        if self._settings_provider is None or self._update_settings is None:
            rumps.alert("未配置设置面板", "当前版本未提供提醒设置。")
            return

        current = self._settings_provider() or UserSettings(45, 30, [])
        result = self._prompt_settings(current)
        if result is None:
            return
        try:
            self._update_settings(result)
            rumps.notification("提醒设置已更新", "", "新的久坐阈值与静默时段已生效")
        except Exception:
            rumps.alert("操作失败", "无法保存设置，请查看日志。")

    def _handle_manual_refresh(self, _sender: rumps.MenuItem) -> None:
        if self._refresh_callback is None:
            rumps.alert("未配置刷新", "当前版本未提供手动刷新。")
            return
        try:
            self._refresh_callback()
            rumps.notification("久坐计时已刷新", "", "重新开始统计在座时长。")
        except Exception:
            rumps.alert("操作失败", "无法刷新久坐计时，请查看日志。")

    def _prompt_settings(self, current: UserSettings) -> Optional[UserSettings]:
        # 使用 NSAlert + 滑块，暂时移除静默时段输入（因为无法键盘输入）
        return self._prompt_settings_sliders(current)

    def _prompt_settings_sliders(self, current: UserSettings) -> Optional[UserSettings]:
        """使用 NSAlert + 滑块实现设置，去掉静默时段输入框。"""

        if NSAlert is None or NSTextField is None or NSSlider is None:
            # 回退到简单文本输入
            return self._prompt_settings_simple(current)

        alert = NSAlert.alloc().init()
        alert.setMessageText_("⚙️ 提醒设置")
        alert.setInformativeText_("通过滚轮调整久坐阈值和提醒冷却时间")
        alert.addButtonWithTitle_("保存")
        alert.addButtonWithTitle_("取消")

        # 隐藏默认图标
        try:
            if NSImage is not None and NSMakeSize is not None:
                empty_icon = NSImage.alloc().initWithSize_(NSMakeSize(1, 1))
                alert.setIcon_(empty_icon)
        except Exception:
            pass

        width = 280.0
        height = 160.0  # 减少高度，因为去掉了静默时段
        container = NSView.alloc().initWithFrame_(NSMakeRect(0.0, 0.0, width, height))

        def make_label(text: str, y: float) -> NSTextField:
            label = NSTextField.alloc().initWithFrame_(NSMakeRect(0.0, y, width, 18.0))
            label.setStringValue_(text)
            label.setEditable_(False)
            label.setBordered_(False)
            label.setBezeled_(False)
            label.setDrawsBackground_(False)
            if NSFont is not None:
                label.setFont_(NSFont.systemFontOfSize_(12.0))
            return label

        def make_value_label(y: float, value: float) -> NSTextField:
            value_label = NSTextField.alloc().initWithFrame_(NSMakeRect(0.0, y, width, 22.0))
            value_label.setStringValue_(f"{value:.0f} 分钟")
            value_label.setEditable_(False)
            value_label.setBordered_(False)
            value_label.setBezeled_(False)
            value_label.setDrawsBackground_(False)
            value_label.setAlignment_(1)  # center
            if NSFont is not None:
                value_label.setFont_(NSFont.systemFontOfSize_weight_(14.0, 0.3))
            return value_label

        # 久坐阈值
        prolonged_value = max(15.0, min(240.0, float(current.prolonged_seated_minutes)))
        prolonged_label = make_label("久坐阈值：", height - 20.0)
        prolonged_value_label = make_value_label(height - 44.0, prolonged_value)

        prolonged_slider = NSSlider.alloc().initWithFrame_(NSMakeRect(0.0, height - 76.0, width, 24.0))
        prolonged_slider.setMinValue_(15.0)
        prolonged_slider.setMaxValue_(240.0)
        prolonged_slider.setDoubleValue_(prolonged_value)
        prolonged_slider.setNumberOfTickMarks_(46)
        prolonged_slider.setAllowsTickMarkValuesOnly_(True)
        prolonged_slider.setContinuous_(True)

        # 提醒冷却
        cooldown_value = max(5.0, min(120.0, float(current.notification_cooldown_minutes)))
        cooldown_label = make_label("提醒冷却：", height - 100.0)
        cooldown_value_label = make_value_label(height - 124.0, cooldown_value)

        cooldown_slider = NSSlider.alloc().initWithFrame_(NSMakeRect(0.0, height - 156.0, width, 24.0))
        cooldown_slider.setMinValue_(5.0)
        cooldown_slider.setMaxValue_(120.0)
        cooldown_slider.setDoubleValue_(cooldown_value)
        cooldown_slider.setNumberOfTickMarks_(24)
        cooldown_slider.setAllowsTickMarkValuesOnly_(True)
        cooldown_slider.setContinuous_(True)

        container.addSubview_(prolonged_label)
        container.addSubview_(prolonged_value_label)
        container.addSubview_(prolonged_slider)
        container.addSubview_(cooldown_label)
        container.addSubview_(cooldown_value_label)
        container.addSubview_(cooldown_slider)

        # 绑定滑块更新
        if _FlowSliderDelegate is not None:
            prolonged_delegate = _FlowSliderDelegate.alloc().initWithLabel_(prolonged_value_label)
            prolonged_slider.setTarget_(prolonged_delegate)
            prolonged_slider.setAction_(objc.selector(_FlowSliderDelegate.sliderChanged_, signature=b"v@:@"))
            prolonged_delegate.sliderChanged_(prolonged_slider)

            cooldown_delegate = _FlowSliderDelegate.alloc().initWithLabel_(cooldown_value_label)
            cooldown_slider.setTarget_(cooldown_delegate)
            cooldown_slider.setAction_(objc.selector(_FlowSliderDelegate.sliderChanged_, signature=b"v@:@"))
            cooldown_delegate.sliderChanged_(cooldown_slider)

            # 保持引用
            try:
                objc.setAssociatedObject(
                    prolonged_slider,
                    b"_upclock_settings_prolonged_delegate",
                    prolonged_delegate,
                    getattr(objc, "OBJC_ASSOCIATION_RETAIN", 0),
                )
                objc.setAssociatedObject(
                    cooldown_slider,
                    b"_upclock_settings_cooldown_delegate",
                    cooldown_delegate,
                    getattr(objc, "OBJC_ASSOCIATION_RETAIN", 0),
                )
            except Exception:
                pass

        alert.setAccessoryView_(container)
        response = alert.runModal()

        if response not in (NSAlertFirstButtonReturn, 1, 1000):
            return None

        prolonged = int(round(prolonged_slider.doubleValue()))
        cooldown = int(round(cooldown_slider.doubleValue()))

        # 保留原有的静默时段设置
        return UserSettings(
            prolonged_seated_minutes=max(15, prolonged),
            notification_cooldown_minutes=max(5, cooldown),
            quiet_hours=current.quiet_hours,  # 保持不变
        )

    def _prompt_settings_simple(self, current: UserSettings) -> Optional[UserSettings]:
        """使用 rumps.Window 实现简单的文本输入设置。"""

        window = rumps.Window(
            message=(
                "⚙️ 提醒设置\n\n"
                "请输入设置（每行一个字段）：\n"
                "第 1 行：久坐阈值（分钟）\n"
                "第 2 行：提醒冷却（分钟）\n"
                "第 3 行：静默时段（逗号分隔，如 22:00-07:00, 12:30-13:30）"
            ),
            title="提醒设置",
            default_text=(
                f"{current.prolonged_seated_minutes}\n"
                f"{current.notification_cooldown_minutes}\n"
                + ", ".join(f"{start}-{end}" for start, end in current.quiet_hours)
            ),
            ok="保存",
            cancel="取消",
            dimensions=(380, 160),
            secure=True,  # 关键：启用安全文本输入，允许键盘输入
        )
        window.icon = None
        response = window.run()

        if response.clicked != 1:
            return None

        lines = response.text.splitlines()
        if not lines:
            return None

        try:
            prolonged = int(lines[0].strip())
            cooldown = int(lines[1].strip()) if len(lines) > 1 else current.notification_cooldown_minutes
        except ValueError:
            rumps.alert("输入无效", "请填写数字形式的分钟数。")
            return None

        quiet_line = lines[2].strip() if len(lines) > 2 else ""
        quiet_slots = self._parse_quiet_input(quiet_line)

        if quiet_slots is None:
            rumps.alert(
                "静默时段格式错误",
                "请使用 HH:MM-HH:MM 形式，多个时段用逗号分隔。\n"
                "例如：22:00-07:00, 12:30-13:30",
            )
            return None

        return UserSettings(
            prolonged_seated_minutes=max(15, prolonged),
            notification_cooldown_minutes=max(5, cooldown),
            quiet_hours=quiet_slots,
        )

    def _parse_quiet_input(self, text: str) -> Optional[list[tuple[str, str]]]:
        text = text.strip()
        if not text:
            return []
        pairs: list[tuple[str, str]] = []
        for raw in text.split(","):
            part = raw.strip()
            if not part:
                continue
            if "-" not in part:
                return None
            start, end = part.split("-", 1)
            start = start.strip()
            end = end.strip()
            if not start or not end:
                return None
            pairs.append((start, end))
        return pairs

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
            alert.setMessageText_("🧘‍♂️ 开启心流模式")
            alert.setInformativeText_("通过滚轮选择持续时间：")
            alert.addButtonWithTitle_("开始")
            alert.addButtonWithTitle_("取消")

            # 隐藏默认图标：创建一个透明的小图标
            try:
                if NSImage is not None and NSMakeSize is not None:
                    empty_icon = NSImage.alloc().initWithSize_(NSMakeSize(1, 1))
                    alert.setIcon_(empty_icon)
            except Exception:
                pass

            width = 200.0
            container = NSView.alloc().initWithFrame_(NSMakeRect(0.0, 0.0, width, 60.0))

            value_label = NSTextField.alloc().initWithFrame_(NSMakeRect(0.0, 32.0, width, 24.0))
            value_label.setStringValue_(f"{default_minutes:.0f} 分钟")
            value_label.setEditable_(False)
            value_label.setBordered_(False)
            value_label.setBezeled_(False)
            value_label.setDrawsBackground_(False)
            value_label.setAlignment_(1)  # center
            if NSFont is not None:
                value_label.setFont_(NSFont.systemFontOfSize_weight_(16.0, 0.3))  # 稍大字体，medium weight

            slider = NSSlider.alloc().initWithFrame_(NSMakeRect(0.0, 8.0, width, 20.0))
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
            secure=True,  # 启用安全输入，允许键盘输入
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
    snooze_state_provider: Optional[Callable[[], tuple[bool, float]]] = None,
    activate_snooze: Optional[Callable[[float], None]] = None,
    cancel_snooze: Optional[Callable[[], None]] = None,
    settings_provider: Optional[Callable[[], Optional[UserSettings]]] = None,
    update_settings: Optional[Callable[[UserSettings], None]] = None,
    refresh_callback: Optional[Callable[[], None]] = None,
) -> None:
    app = StatusBarApp(
        snapshot_provider,
        notification_provider,
        on_system_sleep=on_system_sleep,
        on_system_wake=on_system_wake,
        flow_state_provider=flow_state_provider,
        activate_flow_mode=activate_flow_mode,
        cancel_flow_mode=cancel_flow_mode,
        snooze_state_provider=snooze_state_provider,
        activate_snooze=activate_snooze,
        cancel_snooze=cancel_snooze,
        settings_provider=settings_provider,
        update_settings=update_settings,
        refresh_callback=refresh_callback,
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
