#!/usr/bin/env bash
# upClock 启动脚本 - 使用虚拟环境运行，支持键盘输入

set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

# 使用 uv 运行，并在后台启动（这样可以关闭终端）
# 但为了支持 rumps.Window 的键盘输入，需要在前台运行
echo "启动 upClock..."
echo "提示：如需支持键盘输入，请保持此终端窗口打开"
echo ""

# 使用 uv run 确保使用虚拟环境
uv run python main.py
