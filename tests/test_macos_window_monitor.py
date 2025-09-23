from upclock.config import WindowCategory
from upclock.core.signal_buffer import SignalBuffer
from upclock.adapters.macos.window_monitor import CategoryRule, MacOSWindowMonitor


def test_match_rule_prefers_custom_category() -> None:
    buffer = SignalBuffer()
    categories = [WindowCategory(name="focus", weight=1.2, patterns=["pycharm"])]
    monitor = MacOSWindowMonitor(buffer, categories=categories)

    rule = monitor._match_rule("com.jetbrains.pycharm", "PyCharm")

    assert isinstance(rule, CategoryRule)
    assert rule.name == "focus"
    assert rule.weight == 1.2


def test_match_rule_falls_back_to_neutral() -> None:
    buffer = SignalBuffer()
    monitor = MacOSWindowMonitor(buffer)

    rule = monitor._match_rule("unknown.bundle", "SomeApp")

    assert rule.name == "neutral"
    assert rule.weight == 0.6
