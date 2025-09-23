"""FastAPI 应用及静态 UI。"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Optional

from fastapi import FastAPI
from fastapi.responses import RedirectResponse
from fastapi.staticfiles import StaticFiles

from upclock.core.activity_engine import ActivityEngine
from upclock.core.signal_buffer import SignalBuffer


def create_app(
    buffer: Optional[SignalBuffer] = None,
    engine: Optional[ActivityEngine] = None,
    shared_state: Optional[Any] = None,
) -> FastAPI:
    """构建 FastAPI 应用并注册基础路由。"""

    app = FastAPI(title="upClock")
    _engine = engine
    _buffer = buffer

    if shared_state is None:
        if _buffer is None:
            _buffer = SignalBuffer()
        if _engine is None:
            _engine = ActivityEngine(_buffer)

    static_dir = _resolve_static_directory()
    if static_dir is not None:
        app.mount("/static", StaticFiles(directory=str(static_dir), html=True), name="static")

        @app.get("/", tags=["ui"], include_in_schema=False)
        async def index() -> RedirectResponse:
            return RedirectResponse(url="/static/index.html", status_code=307)

    @app.get("/health", tags=["system"])
    async def health() -> dict[str, str]:
        return {"status": "ok"}

    @app.get("/favicon.ico", include_in_schema=False)
    async def favicon() -> dict[str, str]:
        return {}

    @app.get("/metrics", tags=["metrics"])
    async def metrics() -> dict:
        if shared_state is not None:
            activity = shared_state.get_activity()
            if activity is None:
                return {
                    "score": 0.0,
                    "state": "UNKNOWN",
                    "metrics": {},
                }
            return {
                "score": activity.score,
                "state": activity.state.name,
                "metrics": activity.metrics,
            }

        assert _engine is not None
        snapshot = _engine.compute_snapshot()
        return {
            "score": snapshot.score,
            "state": snapshot.state.name,
            "metrics": snapshot.metrics,
        }

    return app


def _resolve_static_directory() -> Optional[Path]:
    """在开发与打包环境下查找静态资源目录。"""

    candidates: list[Path] = []
    module_static = Path(__file__).resolve().parent / "static"
    candidates.append(module_static)

    resource_path = os.environ.get("RESOURCEPATH")
    if resource_path:
        bundle_static = Path(resource_path) / "static"
        candidates.append(bundle_static)
        bundle_nested = Path(resource_path) / "upclock" / "ui" / "static"
        candidates.append(bundle_nested)

    for path in candidates:
        if path.exists():
            return path

    return None
