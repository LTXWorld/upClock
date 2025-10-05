#!/usr/bin/env python3
"""主动触发摄像头权限请求对话框（macOS）。

在 Ghostty 或其他终端中运行此脚本，会弹出系统权限请求窗口。
授权后，upClock 才能正常使用摄像头功能。
"""

from __future__ import annotations

import logging
import sys
import time
from pathlib import Path

# 确保能导入 upclock 模块
PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_DIR = PROJECT_ROOT / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

logging.basicConfig(
    level=logging.INFO,
    format="[%(levelname)s] %(message)s",
)

logger = logging.getLogger(__name__)


def main() -> None:
    logger.info("=" * 60)
    logger.info("upClock 摄像头权限请求工具")
    logger.info("=" * 60)
    logger.info("")

    # 步骤 1：检查 AVFoundation 是否可用
    try:
        from AVFoundation import AVCaptureDevice, AVMediaTypeVideo
        from Foundation import NSDate, NSDefaultRunLoopMode, NSRunLoop
    except ImportError:
        logger.error("❌ 无法导入 AVFoundation，请确认运行在 macOS 上")
        logger.info("   提示：需要安装 pyobjc-framework-AVFoundation")
        logger.info("   运行: uv sync")
        sys.exit(1)

    logger.info("✓ AVFoundation 模块加载成功")

    # 步骤 2：检查当前权限状态
    status = AVCaptureDevice.authorizationStatusForMediaType_(AVMediaTypeVideo)
    status_map = {
        0: "未请求 (NotDetermined)",
        1: "受限 (Restricted)",
        2: "已拒绝 (Denied)",
        3: "已授权 (Authorized)",
    }

    logger.info(f"📷 当前摄像头权限状态: {status_map.get(status, f'未知({status})')}")
    logger.info("")

    if status == 3:  # Authorized
        logger.info("✅ 摄像头权限已授予，无需再次请求")
        logger.info("")
        logger.info("你可以直接运行 upClock:")
        logger.info("  uv run python main.py")
        return

    if status == 2:  # Denied
        logger.warning("⚠️  摄像头权限已被拒绝")
        logger.info("")
        logger.info("请手动授予权限：")
        logger.info("  1. 打开「系统设置」→「隐私与安全性」→「摄像头」")
        logger.info("  2. 找到 Ghostty（或当前终端应用）")
        logger.info("  3. 勾选以允许访问摄像头")
        logger.info("  4. 重新运行此脚本验证")
        sys.exit(1)

    # 步骤 3：主动请求权限
    logger.info("🔔 即将请求摄像头权限，请注意系统弹窗...")
    logger.info("")

    result: dict[str, bool | None] = {"granted": None}

    def completion_handler(granted: bool) -> None:
        result["granted"] = bool(granted)

    # 发起权限请求
    AVCaptureDevice.requestAccessForMediaType_completionHandler_(
        AVMediaTypeVideo,
        completion_handler,
    )

    # 等待用户响应（最多 30 秒）
    run_loop = NSRunLoop.currentRunLoop()
    deadline = time.time() + 30.0

    logger.info("⏳ 等待用户授权...")
    while result["granted"] is None and time.time() < deadline:
        run_loop.runMode_beforeDate_(
            NSDefaultRunLoopMode,
            NSDate.dateWithTimeIntervalSinceNow_(0.1),
        )

    logger.info("")

    if result["granted"] is None:
        logger.error("❌ 等待授权超时（30秒）")
        logger.info("")
        logger.info("可能原因：")
        logger.info("  - 系统弹窗被其他窗口遮挡")
        logger.info("  - 权限请求已在后台处理")
        logger.info("")
        logger.info("请检查屏幕右上角通知，或重新运行此脚本")
        sys.exit(1)

    if result["granted"]:
        logger.info("✅ 摄像头权限授予成功！")
        logger.info("")
        logger.info("现在可以运行 upClock 完整版：")
        logger.info("  uv run python main.py")
        logger.info("")
        logger.info("你也可以测试摄像头是否工作：")
        logger.info("  uv run python -c 'import cv2; cap = cv2.VideoCapture(0); print(\"✓ 摄像头可用\" if cap.isOpened() else \"✗ 摄像头不可用\"); cap.release()'")
    else:
        logger.error("❌ 用户拒绝了摄像头权限")
        logger.info("")
        logger.info("如需使用摄像头功能，请：")
        logger.info("  1. 重新运行此脚本")
        logger.info("  2. 或在系统设置中手动授权")
        logger.info("")
        logger.info("也可以使用轻量版（无摄像头）：")
        logger.info("  在 config.local.py 中设置 vision_enabled=False")
        sys.exit(1)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        logger.info("")
        logger.info("❌ 用户中断")
        sys.exit(130)
