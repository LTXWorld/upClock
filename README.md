# upClock

upClock 是一款面向 macOS 的轻量久坐提醒工具，常驻状态栏运行：

- 以键鼠活跃度、前台窗口类别、摄像头在座信号（可选）实时评估用户状态。
- 当连续坐姿接近阈值时，通过系统通知与状态栏图标提示，提供多样化的休息建议。
- 提供仪表盘可视化、手动刷新、延后提醒、心流模式、静默时段等操控能力，让用户掌控提醒节奏。

> **数据策略**：除个人化设置（久坐阈值/静默时段等）写入 `~/.upclock/config.json` 外，其余活动数据均保存在内存中。关闭应用后会重新开始统计，便于保持私密与轻量。如果后续需要周报/历史趋势，再考虑增持久化方案。

---

## 目录结构

- `src/upclock/`：核心逻辑（信号采集缓冲、活动评分引擎、视觉适配器、状态栏 UI、FastAPI 仪表盘）。
- `scripts/`：开发与打包脚本（`dev_server.py` 启动 API，`build_macos_app*.sh` 打包 macOS App）。
- `tests/`：pytest 测试。
- `config.local.py`：示例本地配置，可覆盖默认参数。
- `AGENT.md`：全局技术方案与迭代规划。

## 功能亮点

- **状态栏常驻**：图标用 `👨🏻‍💻`/`☕`/`💥` 表示活跃、短暂休息、久坐超阈值。点击可查看专注指数、在座/休息时长，并访问仪表盘/退出。新增“刷新久坐计时”按钮，可手动清零当前在座时间。
- **专注指数 (0~100%)**：综合键鼠输入、久坐衰减与坐姿评分。越高代表越专注、越不需要提醒。
- **多种提醒控制**：
  - 延后提醒：快速延后 5/15/30 分钟，菜单实时显示剩余时间，可一键取消。
  - 心流模式：滚轮设定 15~240 分钟，在专注期间静默所有提醒。
  - 静默时段：可配置多个时间段（如午休/夜间）自动免打扰。
  - 智能通知：达到阈值时，系统级通知（带声音）+ 状态栏弹跳 + 随机化休息建议。
- **仪表盘可视化**：
  - 实时显示当前状态、专注指数、连续在座/休息时长、最近 5 分钟趋势。
  - 今日统计：久坐状态累计时长、已起身休息次数、最长连续在座时间（含久坐前活跃阶段）。
  - 提示区域同步展示心流/延后/静默状态，帮助快速判断下一次提醒时间。
- **视觉信号（可选）**：
  - 自适应电源策略，键鼠静默 >60 秒或久坐阈值达 95% 时才短暂启用摄像头 3 秒确认是否有人在座。
  - 支持 MediaPipe + MoveNet ONNX 姿态模型，结合坐姿评分（upright/slouch/uncertain/untracked）。
  - 若摄像头不可用自动降级至差分模拟，保障核心功能可用。
- **状态联动**：
  - 系统休眠时自动重置计时并暂停提醒，唤醒后恢复。
  - 鼠标/键盘重新活跃会取消延后提醒。

---

## 快速开始

1. **安装依赖**
   ```bash
   uv sync --dev
   ```
   - `uv` 会为项目创建 `.venv`（Python 3.11）。
   - 若要启用摄像头/姿态分析，请额外安装视觉依赖：
     ```bash
     uv sync --extra vision
     ```

2. **运行**
   ```bash
   uv run python main.py
   ```
   - 状态栏出现 upClock 图标；首次运行需授予键鼠监听（辅助功能）、摄像头（若开启视觉）、通知权限。
   - FastAPI 默认监听 `http://127.0.0.1:8000`；访问 `/` 即可查看实时仪表盘。

3. **运行测试**
   ```bash
   uv run pytest
   ```

4. **自定义设置**
   - 状态栏“提醒设置…”面板支持滑杆调整久坐阈值、提醒冷却时间，以及逗号分隔的静默时段（如 `22:00-07:00, 12:30-13:30`）。
   - 保存后会写入 `~/.upclock/config.json`，下次启动自动生效。

---

## 摄像头姿态检测（可选）

1. 安装视觉依赖并确认终端拥有摄像头权限：
   ```bash
   uv sync --extra vision
   ```
   首次访问摄像头时，macOS 会弹窗提示，需要在“系统设置 → 隐私与安全”授权。

2. 在 `config.local.py` 或自定义配置中启用：
   ```python
   AppConfig(
       vision_enabled=True,
       vision_capture_interval_seconds=8.0,
       vision_pose_backend="auto",          # 也可指定 "onnx"
       vision_posture_upright_threshold=0.75,
       vision_posture_slouch_threshold=0.35,
   )
   ```

3. 运行时，upClock 会：
   - 在键鼠静默 >60 秒或久坐即将超时（95%）时短暂唤醒摄像头 3 秒确认是否仍有人在座。
   - 若检测到离席会立即重置在座时间并取消通知；若确认有人，则继续累积直到触发提醒。
   - 无法访问摄像头时，自动回退到差分模拟数据，不影响整体流程。

### ONNX 姿态模型

如需脱离 MediaPipe，可使用 MoveNet ONNX：

```python
AppConfig(
    vision_enabled=True,
    vision_pose_backend="onnx",
    vision_onnx_model_path="/absolute/path/to/movenet.onnx",
    vision_onnx_model_type="movenet-singlepose",
)
```

默认支持 MoveNet SinglePose Lightning/Thunder (`(1, 1, 17, 3)`)，其他模型可在 `posture_onnx.py` 中扩展解析逻辑。

---

## 仪表盘指标说明

- `专注指数`：`score` 原始值 ×100 后映射为 0~100%。受键鼠活跃度、久坐衰减、坐姿评分影响，越高越专注。
- `连续在座 / 休息`：当前已连续坐了多久 / 最近一次离席持续时间。
- `今日久坐状态累计`：只统计进入久坐状态后的分钟数（避免与普通在座混淆）。
- `今日休息次数`：从久坐状态切换到短暂休息的次数。
- `最长连续在座`：今日单段最长在座时间（含久坐前活跃阶段）。
- 趋势图：左轴为专注指数（%），右轴为连续在座（分钟），默认记录最近 5 分钟。

仪表盘顶部摘要会动态拼接：久坐累计、休息次数、最长在座，以及心流模式/延后提醒/静默时段的剩余时间。

---

## FastAPI `/metrics` 字段

| 字段 | 说明 |
| --- | --- |
| `activity_sum` | 近 5 分钟键鼠事件总量 |
| `normalized_activity` | 归一化键鼠活跃度（0~1） |
| `seated_minutes` | 连续在座分钟数 |
| `break_minutes` | 距离上次输入的分钟数（>= `break_reset_minutes` 视为离席） |
| `presence_confidence` | 摄像头在座置信度（0~1） |
| `posture_score` | 姿态得分（越低代表姿态越差） |
| `posture_state` | 姿态分类：`upright` / `slouch` / `uncertain` / `untracked` |
| `score` | 专注指数原始值（0~1） |
| `state` | 活动状态：`ACTIVE` / `SHORT_BREAK` / `PROLONGED_SEATED` |
| `daily_*` | 今日统计（久坐状态累计、休息次数、最长连续在座） |
| `flow_mode_*`, `snooze_*`, `quiet_*` | 心流、延后、静默的开关与剩余时间 |

---

## 配置字段摘要（`AppConfig`）

- `short_break_minutes` / `break_reset_minutes`
- `prolonged_seated_minutes`
- `notification_cooldown_minutes`
- `notifications_enabled`
- `vision_*`（详见上文）
- `window_categories`：可为不同窗口类型（如娱乐/工作）设权重。

可在 `config.local.py` 中编辑并在 `main.py` 中加载自定义配置，或直接使用状态栏“提醒设置…”修改关键参数。

---

## macOS 打包发布

项目提供两种打包脚本，方便对外分享：

### 完整版（含视觉模块）

```bash
uv sync --extra macos --extra vision
bash scripts/build_macos_app.sh
```

- 输出：`dist/upClock.app`
- 包含 OpenCV、MediaPipe、ONNXRuntime 等视觉依赖
- 首次运行需手动授权摄像头/辅助功能/通知

### 轻量版（无视觉依赖）

```bash
uv sync --extra macos
bash scripts/build_macos_app_light.sh
```

- 输出：默认仍为 `dist/upClock.app`。若希望同时保留完整版，可手动重命名为 `upClock-light.app`。
- 仅保留键鼠监控、状态栏、仪表盘逻辑，体积显著减小。

### 发布建议

1. 双击运行产物确认通知/状态栏/仪表盘工作正常。
2. 对外分发前可 `zip` 或打包为 DMG（`hdiutil create`）。
3. 若要面向广大用户发布，建议使用开发者证书进行 `codesign` 与 Apple notarization。

---

## 常见问题

- **通知瞬间闪烁或不出现**：确保系统设置中允许 upClock 横幅/提醒与声音。新版默认使用 `NSUserNotificationCenter` 推送，可持续显示。
- **摄像头未触发**：需在键鼠静默或久坐临界时才会短暂启动；可在日志中查看 `Vision` 相关提示。若终端无权限会自动回退模拟数据。
- **键鼠活动统计异常**：确认“系统设置 → 隐私与安全 → 辅助功能”中已勾选终端/`python`。
- **轻量版缺少视觉能力**：设计如此；需使用完整版或在本地安装 `--extra vision` 依赖并运行源码。

---

## 版权与贡献

upClock 目前仍在积极迭代中，欢迎通过 Issue / PR 反馈体验、提出改进建议或贡献代码。请参考 `AGENT.md` 了解整体规划与下一步方向。
