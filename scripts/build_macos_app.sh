#!/usr/bin/env bash
# macOS 应用打包脚本

set -euo pipefail

ROOT_DIR="$(cd -- "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

cd "$ROOT_DIR"

echo "[upClock] 清理旧的构建产物..."
rm -rf build dist

echo "[upClock] 同步打包依赖 (py2app + vision 模块)..."
uv sync --extra macos --extra vision

echo "[upClock] 开始 py2app 打包..."
uv run --extra macos --extra vision python setup.py py2app "$@"

echo "[upClock] 打包完成，产物位于 dist/upClock.app"
