#!/usr/bin/env bash
# macOS 轻量版应用打包脚本（不包含视觉依赖）

set -euo pipefail

ROOT_DIR="$(cd -- "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

cd "$ROOT_DIR"

echo "[upClock-light] 清理旧的构建产物..."
rm -rf build dist

echo "[upClock-light] 同步打包依赖 (仅 py2app)..."
uv sync --extra macos

echo "[upClock-light] 开始 py2app 打包 (轻量版)..."
INCLUDE_VISION=0 uv run --extra macos python setup.py py2app "$@"

echo "[upClock-light] 打包完成，产物位于 dist/upClock.app"
