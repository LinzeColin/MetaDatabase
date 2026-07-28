#!/usr/bin/env bash
# CyberBoss 安装脚本。
#
# 它只做一件事：把 cyberboss 这个命令装到你的 PATH 上，这样你在任何目录敲
# cyberboss 都能用。装完之后再敲一次 cyberboss，就会进中文安装向导。
#
# 它不会碰你的数据，也不会用 sudo。

set -euo pipefail

RED=$'\033[31m'; GREEN=$'\033[32m'; DIM=$'\033[2m'; RESET=$'\033[0m'
APP_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/app" && pwd)"

say()  { printf '%s\n' "$*"; }
ok()   { printf '%s✓%s %s\n' "$GREEN" "$RESET" "$*"; }
die()  { printf '%s✗%s %s\n' "$RED" "$RESET" "$*" >&2; exit 1; }

say ""
say "正在安装 CyberBoss……"
say ""

# 1. Node 版本。低于 22 的话 node:sqlite 不存在，装了也跑不起来。
command -v node >/dev/null 2>&1 || die "没有找到 node。请先安装 Node.js 22 或更高版本：https://nodejs.org"
NODE_MAJOR="$(node -p 'process.versions.node.split(".")[0]')"
if [ "$NODE_MAJOR" -lt 22 ]; then
  die "Node.js 版本太低（当前 v$NODE_MAJOR，需要 22 或更高）。升级后再运行本脚本。"
fi
ok "Node.js v$(node -p 'process.versions.node')"

command -v npm >/dev/null 2>&1 || die "没有找到 npm。它一般跟 Node.js 一起安装。"

# 2. 依赖。已经装过就跳过，省得每次都等。
cd "$APP_DIR"
if [ ! -d node_modules ]; then
  say "${DIM}正在下载依赖，第一次会慢一点……${RESET}"
  npm install --omit=dev --silent
fi
ok "依赖就绪"

# 3. 装命令。不用 sudo：npm 的全局目录是当前用户自己的。
say "${DIM}正在把 cyberboss 命令装到 PATH 上……${RESET}"
npm install -g . --silent >/dev/null
ok "命令已安装"

# 4. 真的能用吗。装完必须实测一次，而不是假设 npm 说成功就成功了。
if ! command -v cyberboss >/dev/null 2>&1; then
  NPM_BIN="$(npm prefix -g)/bin"
  say ""
  say "${RED}命令装好了，但你的 PATH 上还没有它。${RESET}"
  say ""
  say "把下面这一行加到 ~/.zshrc（或 ~/.bashrc）的末尾，然后重开一个终端："
  say ""
  say "    export PATH=\"$NPM_BIN:\$PATH\""
  say ""
  exit 1
fi

cyberboss help >/dev/null 2>&1 || die "命令装好了但跑不起来。请把上面的输出发给开发者。"

say ""
say "────────────────────────────────────────"
ok "安装完成"
say "────────────────────────────────────────"
say ""
say "现在敲这一条，开始设置："
say ""
say "    cyberboss"
say ""
