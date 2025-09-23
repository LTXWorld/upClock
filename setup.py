"""py2app 打包配置。"""

from __future__ import annotations

import sys
from pathlib import Path

from setuptools import find_packages, setup


sys.setrecursionlimit(10000)

# 确保 zlib 以内置模块形式存在时也能被 py2app 记录
if not hasattr(__import__("zlib"), "__file__"):
    import types
    import zlib

    stub_path = Path(__file__).resolve().parent / "_py2app_zlib_stub.py"
    if not stub_path.exists():
        stub_path.write_text("""# 自动生成的占位文件，供 py2app 记录 zlib 模块\n""", encoding="utf-8")

    zlib.__file__ = str(stub_path)


ROOT = Path(__file__).resolve().parent
SRC_DIR = ROOT / "src"
VERSION = "0.1.0"

APP = [str(ROOT / "main.py")]
DATA_FILES: list[str] = []

PLIST = {
    "CFBundleName": "upClock",
    "CFBundleDisplayName": "upClock",
    "CFBundleIdentifier": "com.upclock.agent",
    "CFBundleShortVersionString": VERSION,
    "CFBundleVersion": VERSION,
    "LSUIElement": True,
    "NSCameraUsageDescription": "upClock 需要访问摄像头以判断是否在座以及久坐风险。",
    "NSMicrophoneUsageDescription": "upClock 将在未来版本中使用麦克风评估环境活跃度。",
    "NSHumanReadableCopyright": "© 2025 upClock contributors",
}

OPTIONS = {
    "argv_emulation": False,
    "packages": ["upclock", "anyio"],
    "includes": [
        "rumps",
        "Quartz",
        "Cocoa",
        "pkg_resources",
        "fastapi",
        "uvicorn",
        "starlette",
        "anyio",
        "h11",
        "sniffio",
        "uvicorn.lifespan.on",
        "uvicorn.protocols",
        "uvicorn.protocols.http",
        "uvicorn.protocols.http.auto",
        "uvicorn.protocols.http.h11_impl",
        "uvicorn.protocols.websockets",
        "uvicorn.protocols.websockets.auto",
        "uvicorn.protocols.websockets.impl",
        "anyio._backends",
        "anyio._backends._asyncio",
    ],
    "resources": [str(SRC_DIR / "upclock" / "ui" / "static")],
    "plist": PLIST,
    "optimize": 0,
}


setup(
    name="upclock-app",
    version=VERSION,
    app=APP,
    data_files=DATA_FILES,
    options={"py2app": OPTIONS},
    setup_requires=["py2app"],
    packages=find_packages(where="src"),
    package_dir={"": "src"},
    include_package_data=True,
    package_data={
        "upclock.ui": [
            "static/*",
            "static/css/*",
            "static/js/*",
        ],
    },
)
