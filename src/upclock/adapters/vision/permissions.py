"""摄像头权限请求工具（仅在 macOS 上生效）。"""

from __future__ import annotations

import logging
import os
import time
from typing import Optional

logger = logging.getLogger(__name__)


def ensure_camera_permission(timeout: float = 10.0) -> bool:
    """确保当前进程拥有摄像头访问权限。

    macOS 要求摄像头授权流程在主线程运行，这里主动触发一次授权，
    避免 OpenCV 在后台线程中请求权限导致失败。
    """

    try:  # pragma: no cover - 仅在 macOS 可用
        from AVFoundation import AVCaptureDevice, AVMediaTypeVideo  # type: ignore
        from Foundation import NSDate, NSDefaultRunLoopMode, NSRunLoop  # type: ignore
    except Exception:  # pragma: no cover - 非 macOS 或缺少依赖
        return True

    status = AVCaptureDevice.authorizationStatusForMediaType_(AVMediaTypeVideo)

    # 3 = authorized, 2 = denied, 0 = not determined
    if status == 3:
        return True
    if status == 2:
        logger.warning("摄像头权限已被拒绝，请在系统设置中手动启用")
        return False

    result: dict[str, Optional[bool]] = {"granted": None}

    def _handler(granted: bool) -> None:
        result["granted"] = bool(granted)

    try:
        AVCaptureDevice.requestAccessForMediaType_completionHandler_(AVMediaTypeVideo, _handler)
    except Exception as exc:  # pragma: no cover - 调用失败
        logger.warning("请求摄像头权限失败: %s", exc)
        return False

    run_loop = NSRunLoop.currentRunLoop()
    deadline = time.time() + timeout

    while result["granted"] is None and time.time() < deadline:
        run_loop.runMode_beforeDate_(NSDefaultRunLoopMode, NSDate.dateWithTimeIntervalSinceNow_(0.1))

    if result["granted"] is None:
        logger.warning("等待摄像头授权超时，请检查系统提示窗口")
        return False

    return bool(result["granted"])


def configure_opencv_authorization() -> None:
    """设置 OpenCV 的授权策略，避免其在后台线程请求权限。"""

    os.environ.setdefault("OPENCV_AVFOUNDATION_SKIP_AUTH", "1")
