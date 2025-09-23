"""开发环境启动 FastAPI 服务。""" 

from __future__ import annotations

import asyncio
import logging
import signal
import threading
from contextlib import suppress

import uvicorn

from upclock.adapters.macos import MacOSInputMonitor, MacOSWindowMonitor
from upclock.config import AppConfig
from upclock.core.activity_engine import ActivityEngine
from upclock.core.signal_buffer import SignalBuffer
from upclock.ui import create_app

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO, format="[%(asctime)s][%(levelname)s] %(name)s: %(message)s")


async def main(shared_state=None) -> None:
    config_model = AppConfig.load()

    if shared_state is None:
        buffer = SignalBuffer()
        engine = ActivityEngine(buffer, config=config_model)
    else:
        buffer = None
        engine = None

    app = create_app(buffer=buffer, engine=engine, shared_state=shared_state)

    input_monitor = None
    window_monitor = None

    if shared_state is None and buffer is not None:
        input_monitor = MacOSInputMonitor(buffer)
        window_monitor = MacOSWindowMonitor(buffer, categories=config_model.window_categories)

        await input_monitor.start()
        await window_monitor.start()

    uvicorn_config = uvicorn.Config(app, host="127.0.0.1", port=8000, reload=False)
    server = uvicorn.Server(uvicorn_config)

    if threading.current_thread() is threading.main_thread():
        stop_event = asyncio.Event()

        def _handle_stop(*_: object) -> None:
            logger.info("收到终止信号，准备关闭服务器…")
            stop_event.set()

        loop = asyncio.get_running_loop()
        for sig in (signal.SIGINT, signal.SIGTERM):
            loop.add_signal_handler(sig, _handle_stop)

        async def _serve() -> None:
            await server.serve()
            stop_event.set()

        serve_task = asyncio.create_task(_serve())

        await stop_event.wait()
        serve_task.cancel()
        with suppress(asyncio.CancelledError):
            await serve_task
    else:
        await server.serve()

    if input_monitor is not None:
        input_monitor.stop()
    if window_monitor is not None:
        window_monitor.stop()


if __name__ == "__main__":
    asyncio.run(main())
