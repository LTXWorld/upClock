# upClock 系统分析与优化建议

## 当前系统概览

### 代码规模
- 总代码行数：~3700 行
- 核心模块：
  - `core/`: 活动评分引擎、信号缓冲
  - `adapters/`: macOS 输入/窗口监控、视觉检测
  - `ui/`: 状态栏应用、FastAPI 仪表盘
  - `service.py`: 后台协调服务 (~650 行)
  - `status_bar.py`: 状态栏界面 (~900 行)

### 已实现功能
✅ 键鼠活动监控
✅ 窗口类别追踪
✅ 可选摄像头姿态检测（MediaPipe/ONNX）
✅ 久坐状态机（ACTIVE/SHORT_BREAK/PROLONGED_SEATED）
✅ 多种提醒模式（心流、延后、静默时段）
✅ 会议/演示自动识别
✅ 系统睡眠感知
✅ FastAPI 实时仪表盘
✅ 每日统计（久坐时长、休息次数）
✅ **新增**: 每15分钟坐姿提醒

---

## 一、核心功能优化

### 1.1 输入体验优化 ⭐⭐⭐
**当前问题**: rumps.Window 和 NSAlert 都无法正常键盘输入

**解决方案**:
```python
# 方案A: 使用 framework Python（推荐）
brew install python@3.11
rm -rf .venv
uv venv --python /opt/homebrew/bin/python3.11
uv sync --extra vision

# 方案B: 替换为 Web 界面配置
# 在仪表盘添加设置页面，通过浏览器配置（体验更好）
```

**优先级**: 高
**工作量**: 1-2 小时
**收益**: 极大提升用户体验

### 1.2 坐姿提醒增强 ⭐⭐
**当前实现**: 固定 15 分钟间隔

**建议扩展**:
```python
# config.py 添加配置
class AppConfig(BaseModel):
    posture_reminder_enabled: bool = True
    posture_reminder_interval_minutes: int = 15
    posture_reminder_messages: list[str] = [
        "请检查当前坐姿体态，注意后背坐实，双臂平放。",
        "保持坐姿端正，避免前倾或后仰。",
        "调整椅子高度，让双脚平放地面。",
    ]
```

**新功能**:
- [ ] 可配置提醒间隔
- [ ] 随机化提醒文案
- [ ] 与摄像头姿态检测联动（检测到slouch时提前提醒）
- [ ] 状态栏显示下次坐姿提醒倒计时

### 1.3 通知优先级管理 ⭐⭐
**当前问题**: 坐姿提醒可能与久坐提醒冲突

**改进方案**:
```python
class NotificationPriority(Enum):
    POSTURE_REMINDER = 1  # 低优先级
    SEATED_WARNING = 2     # 中优先级
    MEETING_SUMMARY = 3    # 高优先级
    SYSTEM_ALERT = 4       # 最高优先级

# 通知队列机制
class NotificationQueue:
    def add(self, notification, priority):
        """按优先级排序，合并相同类型"""

    def should_send(self, notification):
        """根据冷却时间和优先级判断"""
```

---

## 二、数据持久化 ⭐⭐⭐

### 2.1 历史数据存储
**当前**: 仅内存存储，关闭应用后丢失

**建议实现**:
```python
# 使用 SQLite 轻量化存储
# src/upclock/storage/database.py

CREATE TABLE daily_stats (
    date TEXT PRIMARY KEY,
    total_seated_minutes REAL,
    prolonged_seated_minutes REAL,
    break_count INTEGER,
    max_seated_minutes REAL,
    posture_reminders_count INTEGER
);

CREATE TABLE activity_logs (
    timestamp INTEGER,
    state TEXT,
    score REAL,
    posture_score REAL
);
```

**新功能**:
- [ ] 周报/月报生成
- [ ] 历史趋势图表
- [ ] 坐姿质量评分统计
- [ ] 导出为 CSV/JSON

**优先级**: 中高
**工作量**: 4-6 小时

### 2.2 配置备份与同步
```python
# 配置文件版本管理
~/.upclock/
├── config.json          # 当前配置
├── config.backup.json   # 自动备份
└── profiles/            # 多场景配置
    ├── home.json
    ├── office.json
    └── focus.json
```

---

## 三、UI/UX 改进

### 3.1 Web 仪表盘增强 ⭐⭐⭐
**当前**: 基础 HTML + Chart.js

**建议升级**:
```bash
# 使用现代框架重构前端
cd src/upclock/ui/frontend
npm init -y
npm install svelte vite chart.js

# 新功能
- 实时 WebSocket 数据流
- 深色模式切换
- 可拖拽时间轴
- 自定义小部件（番茄钟、待办事项）
- 导出报告（PDF）
```

**路线图**:
1. 保留当前 HTML 作为后备
2. 添加 `/v2` 路由指向新前端
3. 逐步迁移功能
4. 最终替换默认界面

### 3.2 状态栏菜单优化 ⭐⭐
```python
# 当前菜单层级较深，建议重组
upClock ⌚
├── 📊 状态：活跃 | 专注度 68%
├── ⏱️ 在座 23.5 分钟 / 阈值 45 分钟
├── ──────────────
├── 🧘 心流模式...
├── ⏸️ 延后提醒 ▶
│   ├── 5 分钟
│   ├── 15 分钟
│   └── 30 分钟
├── ⚙️ 快速设置 ▶
│   ├── 坐姿提醒: ✓ 开启
│   ├── 久坐阈值: 45 分钟
│   └── 更多设置...
├── 🔄 刷新计时
├── 📈 打开仪表盘
└── ❌ 退出
```

### 3.3 原生通知改进 ⭐
```python
# 使用 macOS 可交互通知
notification.setHasActionButton_(True)
notification.setActionButtonTitle_("我知道了")
notification.setOtherButtonTitle_("延后10分钟")

# 用户点击"延后"时自动调用 activate_snooze(10)
```

---

## 四、健康功能扩展

### 4.1 眼睛休息提醒 ⭐⭐
```python
# 20-20-20 规则：每20分钟，看20英尺外，持续20秒
class EyeCareReminder:
    interval_minutes: int = 20
    distance_feet: int = 20
    duration_seconds: int = 20

    def notify(self):
        """提醒用户进行眼部休息"""
```

### 4.2 站立建议 ⭐⭐
```python
# 根据久坐时间推荐活动
ACTIVITY_SUGGESTIONS = {
    "short": [  # < 30 分钟
        "起身倒杯水",
        "简单拉伸肩颈",
    ],
    "medium": [  # 30-60 分钟
        "站起来走动5分钟",
        "做10个深蹲",
    ],
    "long": [  # > 60 分钟
        "出门散步10分钟",
        "做一套完整拉伸操",
    ]
}
```

### 4.3 饮水提醒 ⭐
```python
class HydrationReminder:
    interval_minutes: int = 60
    daily_goal_ml: int = 2000

    def track_intake(self, ml: int):
        """记录饮水量"""
```

---

## 五、技术债务与代码质量

### 5.1 测试覆盖 ⭐⭐⭐
**当前**: 5 个测试文件，覆盖率约 30%

**待补充**:
```bash
# 缺失的关键测试
tests/
├── test_service.py           # 后台服务集成测试
├── test_notification.py      # 通知逻辑测试
├── test_config_store.py      # 配置持久化测试
├── test_status_bar_ui.py     # UI 交互测试（困难）
└── test_vision_controller.py # 视觉控制器测试
```

**建议**:
```python
# 使用 pytest-cov 检查覆盖率
uv add pytest-cov --dev
uv run pytest --cov=upclock --cov-report=html

# 目标：覆盖率提升至 60%+
```

### 5.2 代码重构 ⭐⭐
**service.py 过大** (650 行)
```python
# 拆分为多个子模块
src/upclock/service/
├── __init__.py
├── coordinator.py      # 主协调逻辑
├── notification.py     # 通知管理
├── context_detection.py # 会议/演示检测
└── state_tracking.py   # 状态追踪
```

**status_bar.py 过大** (900 行)
```python
# 抽取配置对话框
src/upclock/ui/dialogs/
├── settings_dialog.py
├── flow_mode_dialog.py
└── base.py
```

### 5.3 日志系统优化 ⭐
```python
# 结构化日志
import structlog

logger = structlog.get_logger()
logger.info(
    "posture_reminder_sent",
    interval_minutes=15,
    user_state="ACTIVE",
    posture_score=0.73
)

# 日志轮转
# ~/.upclock/logs/
# ├── upclock.log
# ├── upclock.log.1
# └── upclock.log.2
```

---

## 六、性能优化

### 6.1 资源占用监控 ⭐⭐
```python
# 添加性能指标收集
class PerformanceMonitor:
    def __init__(self):
        self.cpu_usage: list[float] = []
        self.memory_mb: list[float] = []

    def report(self):
        """在仪表盘显示资源占用"""
```

### 6.2 摄像头优化 ⭐
**当前**: 每次探测打开/关闭摄像头

**优化**:
```python
# 保持摄像头连接，仅在需要时采样
class OptimizedCameraAdapter:
    async def start(self):
        """启动时打开摄像头"""

    async def sample(self):
        """采样一帧，不重新打开"""

    async def stop(self):
        """应用退出时关闭"""
```

---

## 七、跨平台支持

### 7.1 Windows 适配 ⭐⭐⭐
```python
# adapters/windows/
├── input_monitor.py   # 使用 pynput 或 pywin32
├── window_monitor.py  # 使用 pywin32
└── systray.py         # 使用 pystray

# 挑战
- 系统托盘而非菜单栏
- 通知 API 不同（toast notification）
- 权限管理不同
```

### 7.2 Linux 适配 ⭐⭐
```python
# adapters/linux/
├── input_monitor.py   # 使用 python-xlib
├── window_monitor.py  # 使用 wmctrl
└── systray.py         # 使用 PyQt 或 GTK
```

---

## 八、生态与集成

### 8.1 快捷指令集成 ⭐⭐
```python
# 提供 CLI 接口
# upclock-cli status
# upclock-cli snooze 10
# upclock-cli flow 60

# 可与 Apple Shortcuts 集成
# "开始工作" -> 自动开启心流模式 90 分钟
```

### 8.2 日历集成 ⭐⭐
```python
# 读取系统日历，自动静默会议时段
import EventKit

class CalendarIntegration:
    def get_upcoming_events(self):
        """获取未来2小时的日历事件"""

    def auto_flow_mode(self, event):
        """会议前自动开启心流模式"""
```

### 8.3 健康 App 集成 ⭐
```python
# 同步数据到 Apple Health
# - 站立时间
# - 久坐时长
# - 活动提醒响应率
```

---

## 九、商业化考虑

### 9.1 免费版 vs 专业版
**免费版**:
- ✅ 基础久坐提醒
- ✅ 心流模式
- ✅ 延后提醒
- ❌ 历史统计
- ❌ 高级报表
- ❌ 多设备同步

**专业版** ($9.99):
- ✅ 所有免费功能
- ✅ 无限历史数据
- ✅ 周报/月报
- ✅ 云同步
- ✅ 高级分析
- ✅ 优先客服

### 9.2 隐私合规
- [ ] 明确隐私政策
- [ ] 本地优先策略
- [ ] 可选遥测（匿名）
- [ ] GDPR 合规（欧洲用户）

---

## 十、优先级排序

### 🔥 立即执行（1周内）
1. **修复键盘输入问题** - 使用 framework Python
2. **坐姿提醒配置化** - 添加到设置界面
3. **补充核心测试** - 提升至 50% 覆盖率

### ⭐ 近期规划（1个月内）
4. **SQLite 历史存储** - 周报功能
5. **Web 仪表盘升级** - 更好的可视化
6. **代码重构** - 拆分大文件

### 🎯 中期目标（3个月内）
7. **Windows 适配** - 扩大用户群
8. **高级健康功能** - 眼睛休息、饮水提醒
9. **日历集成** - 自动化场景

### 🚀 长期愿景（6个月+）
10. **移动端伴侣 App** - iOS/Android 提醒同步
11. **团队版本** - 企业健康管理
12. **AI 个性化建议** - 基于用户习惯

---

## 附录：快速改进检查清单

### 代码质量 ✓
- [ ] 添加类型注解覆盖率检查（mypy）
- [ ] 添加代码格式化（black）
- [ ] 添加 linter（ruff）
- [ ] 设置 pre-commit hooks

### 文档 ✓
- [ ] API 文档（Swagger UI）
- [ ] 架构图更新
- [ ] 用户手册（中英文）
- [ ] 贡献指南

### DevOps ✓
- [ ] GitHub Actions CI/CD
- [ ] 自动化打包脚本
- [ ] 版本号管理
- [ ] 发布日志自动生成

---

**总结**: upClock 已具备坚实的技术基础和核心功能，下一步应聚焦于**用户体验优化**（输入问题）、**数据价值挖掘**（历史统计）和**跨平台扩展**（Windows 支持）。
