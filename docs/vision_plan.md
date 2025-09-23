# 摄像头在位检测设计草案

## 目标
- 在保证隐私和资源可控的前提下，通过摄像头识别用户是否仍在座位上，以及大致姿态（坐直/弯腰/离席）。
- 输出可与键鼠信号整合的指标，例如 `presence_confidence`、`posture_score`，用于调整久坐判定及提醒策略。
- 支持完全关闭、限定采样频率、遮罩敏感信息等隐私控制。

## 架构概览
```
CameraCapture → FrameQueue → VisionProcessor → PresenceSnapshot → SignalBuffer
```
- **CameraCapture**：独立线程/异步任务，使用 AVFoundation（macOS）或 OpenCV 打开摄像头；按 `capture_interval` 采样（默认 10s）。
- **FrameQueue**：有限缓冲，避免阻塞摄像头；对帧做降采样/压缩。
- **VisionProcessor**：运行轻量模型（首阶段可用 MediaPipe BlazePose Lite / YOLO-NAS-S Pose）。提供插件式推理接口，便于替换或关闭。
- **PresenceSnapshot**：包含 `timestamp`、`presence`（0/1）、`confidence`、`posture_state`、`posture_score` 等字段。
- **SignalBuffer 集成**：将 `presence_confidence` 写入缓冲区，并将 `seated_minutes` 逻辑扩展为：若存在“人离开”信号，则立即重置在座计时。

## 插件接口
```python
class VisionAdapter(InputAdapter):
    async def start(self) -> None: ...
    async def stop(self) -> None: ...

@dataclass
class PresenceSnapshot:
    timestamp: datetime
    presence: bool
    confidence: float
    posture: Literal["upright", "slouch", "unknown"]
    posture_score: float  # 0~1
```
- `VisionAdapter` 继承现有 `InputAdapter`，负责从摄像头采集并调用处理器。
- `PresenceSnapshot` 通过共享队列传给 ActivityEngine，或先写入 `SignalBuffer`。

## 配置项（建议加入 `AppConfig`）
- `vision_enabled`: bool（默认 False）。
- `vision_capture_interval`: float（秒）。
- `vision_presence_threshold`: float（默认 0.6）。
- `vision_posture_thresholds`: dict，用于定义提醒级别。
- `vision_privacy_mode`: enum（`off` / `blur` / `edge`），决定是否保存帧或仅处理关键点。

## ActivityEngine 融合策略
1. **Presence gating**：若 `presence_confidence` < 阈值，则认为用户离开，重置在座计时。
2. **Posture modifier**：久坐提醒可以根据 `posture_score` 加权（例如长期弯腰则提前提醒）。
3. **状态输出**：在 metrics 中新增 `presence_confidence`、`posture_score`、`posture_state`。

## 隐私与开关
- 默认关闭；用户需在设置中打开，并明确说明不会存储或上传影像。
- 仅处理关键点/坐标；可提供调试模式保存帧（默认禁用）。
- 在权限检测失败时（未授权摄像头），VisionAdapter 不启动并给出日志提示。

## 初步实现阶段
1. **占位实现**：不接入真实摄像头，随机输出 presence/posture 模拟数据，验证数据流。
2. **基础摄像头采集**：使用 AVFoundation 或 OpenCV 打开摄像头，按 `capture_interval` 提取帧，执行简单亮度/差分检测判断 presence。
3. **模型融合**：引入 MediaPipe/ONNX 模型，计算人体关键点与姿态分数。
4. **性能优化**：异步队列、推理帧率限制、可配置分辨率。

## 风险与待办
- **权限**：需请求摄像头访问，提示用户操作；未授权时应降级为键鼠模式。
- **性能**：持续推理可能耗电/占 CPU，需限定采样频率并可手动暂停。
- **隐私合规**：提供开关、明确提示、避免存储敏感数据。
- **兼容性**：未来 Windows/Linux 需更换采集方案（DirectShow、V4L2）。

### 当前进展
- 已实现模拟适配器 `SimulatedVisionAdapter`，周期性写入 `presence_confidence`、`posture_score` 等指标。
- `ActivityEngine` 将视觉信号作为“在座/休息”判定的额外证据；当置信度低于阈值时立即视为离席。
- 配置项 `vision_enabled` 默认关闭，可在本地开启体验占位数据流。

下一步将基于该骨架接入真实摄像头采集与姿态模型，实现隐私友好的本地推理。
