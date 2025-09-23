# upClock

桌面久坐提醒助手，目标是在后台持续运行，根据键鼠活动与活跃窗口判断用户状态，并在达到阈值时提醒。

## 目录结构

- `src/upclock/`：核心代码（信号缓冲、评分引擎、适配器、通知、UI）。
- `scripts/`：开发/运维脚本，当前包含 `dev_server.py` 用于启动 FastAPI。
- `tests/`：pytest 测试用例。
- `AGENT.md`：整体技术方案与迭代规划。

## 开始使用

1. **安装依赖**
   ```bash
   uv sync --dev
   ```
   若首次使用 uv，请确保已安装并允许其管理 Python 3.11。
   若要体验摄像头检测与姿态评估，请额外安装 vision 依赖（包含 OpenCV、MediaPipe、ONNXRuntime）：
   ```bash
   uv sync --extra vision
   ```

2. **运行开发服务器**
   ```bash
   uv run python main.py
   ```
   - 系统状态栏会出现 upClock 图标（✅/☕/⛔），展示当前久坐状态。
   - 服务默认监听 `http://127.0.0.1:8000`，可访问 `/health` 与 `/metrics`。
   - 浏览器访问 `http://127.0.0.1:8000/` 可查看实时仪表盘（默认每 2 秒刷新一次）。
   - 首次运行若提示缺少通知或摄像头权限，请在“系统设置”中为终端或 uv 允许运行通知、摄像头与屏幕录制，并在“辅助功能”中授权键鼠监听。

3. **运行测试**
   ```bash
   uv run pytest
   ```

## 启用摄像头姿态检测

1. 安装 vision 依赖并确认终端拥有摄像头权限：
   ```bash
   uv sync --extra vision
   ```
   若首次运行，macOS 会弹窗提示摄像头访问，需要在“系统设置 → 隐私与安全”中为终端授权。

2. 覆盖默认配置（可参考 `config.local.py`）：
   ```python
   AppConfig(
       vision_enabled=True,
       vision_capture_interval_seconds=8.0,
       vision_pose_backend="auto",  # 可切换为 "onnx"
       vision_posture_upright_threshold=0.75,
       vision_posture_slouch_threshold=0.35,
   )
   ```

3. 在 `main.py` 启动前加载自定义配置或在后续版本提供的配置加载入口中启用。

当摄像头/模型不可用时，系统会自动回退到差分法模拟数据，确保流程不中断。

> **省电策略**：摄像头不会持续开启，仅在键鼠输入超过约 60 秒仍未恢复、处于“模糊状态”时临时探测约 3 秒，确认是否仍有人在座。探测完成后摄像头立即关闭，从而避免长时间占用硬件资源。

> **久坐阈值最终确认**：当连续在座时长达到久坐阈值的约 95% 时（默认 45 分钟 → 约 42 分钟），系统会再触发一次短暂摄像头探测，以判断用户是否仍在座位。若探测结果显示有人，就继续累积并在真正达到阈值时提醒；若判定已离席，则自动重置在座计时，避免误报。

### 使用 ONNX 模型

若你希望脱离 MediaPipe，使用自定义的 ONNX 姿态模型（目前内置支持 MoveNet SinglePose Lightning/Thunder）：

1. 下载对应的 ONNX 模型文件，例如 `movenet_singlepose_lightning_192x192.onnx`，并放置在本地路径。
2. 在配置中指定：
   ```python
   AppConfig(
       vision_enabled=True,
       vision_pose_backend="onnx",
       vision_onnx_model_path="/absolute/path/to/movenet.onnx",
       vision_onnx_model_type="movenet-singlepose",
   )
   ```
3. 再次运行 `uv run python main.py`。若模型加载失败，日志会提示并自动退回模拟数据。

当前实现默认针对 MoveNet 输出格式（`(1, 1, 17, 3)` 的关键点数组）。如需接入其他 ONNX 姿态模型，可在 `posture_onnx.py` 中补充规格描述与解析逻辑。

## 指标说明（当前 FastAPI `/metrics`）

- `activity_sum`：近 5 分钟内聚合的键鼠事件数（用于观察交互频率）。
- `normalized_activity`：归一化后的键鼠活跃度（0~1）。
- `seated_minutes`：自上次有效离席以来的连续在座时长（分钟）。
- `break_minutes`：距离最近一次检测到活动的分钟数，超过 `break_reset_minutes` 认为已经起身休息。
- `presence_confidence`：视觉模型输出的在座置信度（0~1）。
- `posture_score`：根据 MediaPipe/ONNX 姿态模型计算的坐姿得分，越低越可能久坐不良。
- `posture_state`：对坐姿的离散分类（`upright`、`slouch`、`uncertain`、`untracked`）。
- `score`：综合分数（活跃度 × 久坐程度衰减 × 姿态修正），越低表示越需要提醒。
- `state`：`ACTIVE`（正常在座）、`SHORT_BREAK`（近期离席/休息）、`PROLONGED_SEATED`（久坐超阈值）。

## UI / 状态栏预览

- 状态栏图标：`👨🏻‍💻` 表示活跃、`☕` 表示短暂休息、`💥` 表示久坐超阈值。点击图标可查看得分、在座/休息时长、打开仪表盘或退出程序。
- 默认启用久坐提醒：当进入 `PROLONGED_SEATED` 且满足冷却时间（默认 30 分钟，可在配置中修改）时，会通过系统通知提示活动（首次运行若提示缺少 Info.plist，应用会自动生成所需文件）。状态栏菜单会显示下一次提醒的预计时间。
- 仪表盘：展示当前状态、得分、在座/休息时长，并绘制得分与在座趋势曲线。指标更新频率默认 2 秒，可在 `src/upclock/ui/static/js/app.js` 中调整。

## 配置字段概要

- `short_break_minutes`：判定为“短暂休息”的最小离席时长（默认 3 分钟）。超过该值会重置在座计时。
- `break_reset_minutes`：在座计时的重置阈值（默认 3 分钟，通常与 `short_break_minutes` 相同）。
- `prolonged_seated_minutes`：连续在座超过该值视为“久坐”（默认 45 分钟）。
- `notification_cooldown_minutes`：久坐提醒之间的冷却时间（默认 30 分钟）。
- `vision_enabled`：是否启用摄像头在位检测（默认关闭）。
- `vision_capture_interval_seconds`：摄像头采样间隔（默认 10 秒）。
- `vision_presence_threshold`：判定“在座”所需的最小置信度（默认 0.6，可与姿态模型联动）。
- `vision_pose_backend`：姿态模型后端（`auto`=优先 MediaPipe，失败降级；`onnx`=使用自定义 ONNXRuntime 模型）。
- `vision_pose_min_confidence`：姿态关键点最低可接受置信度，低于该值会视为 `untracked`。
- `vision_posture_upright_threshold` / `vision_posture_slouch_threshold`：坐姿评分分段阈值。
- `vision_posture_depth_tolerance` / `vision_posture_tilt_tolerance`：前倾与歪斜的容忍度，数值越小越敏感。
- `vision_onnx_model_path`：可选的 ONNX 模型路径，用于自定义姿态推理。
- `vision_onnx_model_type`：ONNX 模型规格（默认 MoveNet，可在 `posture_onnx.py` 中查看可选项）。
- `notifications_enabled`：是否启用系统通知。

若需快速验证久坐提醒，可临时将上述分钟数调小（例如 1 分钟）再运行。启用视觉后，请确认终端已获得摄像头权限；若 MediaPipe 模型不可用，系统会自动退回帧差模拟，相关阈值依旧有效。

## 打包发布（macOS）

使用 `py2app` 可以将 upClock 打包为原生的 `.app`，便于分享给其他 macOS 用户：

1. **同步打包依赖**（包含 py2app 与视觉模块）
   ```bash
   uv sync --extra macos --extra vision
   ```

2. **执行打包脚本**
   ```bash
   bash scripts/build_macos_app.sh
   ```
   - 脚本会清理 `build/` 与 `dist/`，随后运行 `python setup.py py2app`。
   - 构建完成后，`.app` 位于 `dist/upClock.app`。

3. **首次发布建议**
   - 双击运行 `dist/upClock.app`，确认状态栏图标/仪表盘/通知都正常工作。
   - 若计划对外分发，可将 `dist/upClock.app` 打包为 ZIP，或使用 `hdiutil create` 生成 DMG。
   - 公共发布时请考虑使用开发者证书进行 `codesign` 与 Apple notarization，以减少 Gatekeeper 提示。

> **提示**：若希望生成不含视觉模块的轻量版，可在脚本中去掉 `--extra vision` 并调整 `setup.py` 的 `includes`/`packages`。不过在运行端若缺失相关依赖，摄像头功能会自动禁用。
