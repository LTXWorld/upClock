"""状态栏应用启动入口。"""

from __future__ import annotations

import asyncio
import logging
import sys
import threading
from pathlib import Path
from typing import Optional

# 确保 src 加入路径
PROJECT_ROOT = Path(__file__).resolve().parent
SRC_DIR = PROJECT_ROOT / "src"
if SRC_DIR.exists() and str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from scripts.dev_server import main as run_dev_server
from upclock.adapters.vision.permissions import configure_opencv_authorization, ensure_camera_permission
from upclock.service import SharedState, start_backend_in_thread
from upclock.ui.status import NotificationMessage, StatusSnapshot, run_status_bar_app


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="[%(asctime)s][%(levelname)s] %(name)s: %(message)s")

    configure_opencv_authorization()
    if not ensure_camera_permission():
        logging.getLogger(__name__).warning("未获摄像头授权，视觉检测将自动降级")

    shared_state = SharedState()

    start_backend_in_thread(shared_state)

    def _serve_api() -> None:
        asyncio.run(run_dev_server(shared_state=shared_state))

    server_thread = threading.Thread(target=_serve_api, name="upclock-api", daemon=True)
    server_thread.start()

    def snapshot_provider() -> Optional[StatusSnapshot]:
        return shared_state.get_status()

    def notification_provider() -> Optional[NotificationMessage]:
        return shared_state.pop_notification()

    def handle_system_sleep() -> None:
        logging.getLogger(__name__).info("检测到系统进入睡眠，暂停久坐计算")
        shared_state.set_system_sleeping(True)

    def handle_system_wake() -> None:
        logging.getLogger(__name__).info("系统唤醒，恢复久坐计算")
        shared_state.set_system_sleeping(False)

    def flow_state_provider() -> tuple[bool, float]:
        return shared_state.get_flow_mode_state()

    def activate_flow_mode(duration_minutes: float) -> None:
        logging.getLogger(__name__).info("心流模式开启 %.1f 分钟", duration_minutes)
        shared_state.activate_flow_mode(duration_minutes)

    def cancel_flow_mode() -> None:
        logging.getLogger(__name__).info("心流模式结束")
        shared_state.cancel_flow_mode()

    run_status_bar_app(
        snapshot_provider,
        notification_provider,
        on_system_sleep=handle_system_sleep,
        on_system_wake=handle_system_wake,
        flow_state_provider=flow_state_provider,
        activate_flow_mode=activate_flow_mode,
        cancel_flow_mode=cancel_flow_mode,
    )


if __name__ == "__main__":
    main()
