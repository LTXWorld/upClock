"""py2app 打包配置。"""

from __future__ import annotations

from pathlib import Path

from setuptools import find_packages, setup


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
    "packages": ["upclock"],
    "includes": [
        "rumps",
        "Quartz",
        "Cocoa",
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
