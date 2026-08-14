#!/usr/bin/env bash
# 给 Owner 的一条命令：先自检，再把扩展目录在访达里打开。
#
# 载入扩展这一步只能由人做（chrome://extensions 是浏览器设置页，
# 自动化工具进不去；Chrome 137 起也不再支持 --load-extension 命令行开关，
# 本机是 150）。这个脚本把能自动的部分做完，剩下三次点击留给 Owner。
set -euo pipefail
cd "$(dirname "$0")/.."

echo "① 装载前自检…"
if ! .venv/bin/python scripts/preflight_extension.py; then
  echo
  echo "自检没过——先别装，上面列的问题会让 Chrome 直接拒绝加载。"
  exit 1
fi

EXT_DIR="$(cd apps/browser-extension && pwd)"
echo
echo "② 接下来这三步只能你来："
echo "   1. Chrome 打开 chrome://extensions"
echo "   2. 右上角打开「开发者模式」"
echo "   3. 点「加载已解压的扩展程序」，选下面这个目录："
echo
echo "      $EXT_DIR"
echo
if command -v open >/dev/null 2>&1; then
  open "$EXT_DIR"
  echo "   （已在访达里打开该目录，直接拖进去也行）"
fi
echo
echo "③ 装好之后回来说一声，我接着把 T02 / T04 / T06 / T08 的真实验收跑完。"
