#!/usr/bin/env bash
# 安装 framework Python 以支持 rumps 键盘输入

set -euo pipefail

echo "检测 Python 是否为 framework 版本..."

if python3 -c "import sys, os; exit(0 if os.path.exists(os.path.join(sys.prefix, 'Python.framework')) else 1)" 2>/dev/null; then
    echo "✓ 当前 Python 已经是 framework 版本"
    exit 0
fi

echo "当前 Python 不是 framework 版本，需要安装 framework Python"
echo ""
echo "解决方案："
echo "1. 使用 Homebrew 安装 framework Python:"
echo "   brew install python@3.11"
echo ""
echo "2. 或使用 pyenv 安装 framework Python:"
echo "   env PYTHON_CONFIGURE_OPTS=\"--enable-framework CC=clang\" pyenv install 3.11.13"
echo ""
echo "3. 重新创建虚拟环境："
echo "   rm -rf .venv"
echo "   uv venv --python /usr/local/bin/python3.11  # 或 pyenv 的 Python 路径"
echo "   uv sync --extra vision"
echo ""
echo "注意：Homebrew 安装的 Python 默认是 framework 版本"
