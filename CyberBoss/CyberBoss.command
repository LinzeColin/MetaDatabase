#!/bin/bash
# 双击这个文件就行。
#
# 它把所有事一次做完：拉最新代码、装依赖、装命令、然后启动。
# 装过了就直接启动，不会再问一遍。
#
# 中途任何一步失败，屏幕上会用中文说清楚是什么问题、下一步做什么，
# 窗口不会自己关掉。

cd "$(dirname "${BASH_SOURCE[0]}")" || exit 1
REPO="$(cd .. && pwd)"
APP="$(pwd)/app"

BOLD=$'\033[1m'; GREEN=$'\033[32m'; RED=$'\033[31m'; DIM=$'\033[2m'; RESET=$'\033[0m'

command -v clear >/dev/null 2>&1 && [ -t 1 ] && clear
printf '%s\n' ""
printf '%s\n' "  ┌────────────────────────────────┐"
printf '%s\n' "  │        ${BOLD}CyberBoss${RESET}               │"
printf '%s\n' "  │    你的微信 AI 助手            │"
printf '%s\n' "  └────────────────────────────────┘"
printf '%s\n' ""

# 出错时不要一闪而过：让用户看得见发生了什么。
die() {
  printf '\n%s✗ %s%s\n\n' "$RED" "$1" "$RESET"
  [ -n "$2" ] && printf '  怎么办：%s\n\n' "$2"
  printf '%s按回车键关闭这个窗口。%s' "$DIM" "$RESET"
  read -r _
  exit 1
}

step() { printf '  %s\n' "$1"; }
ok()   { printf '  %s✓%s %s\n' "$GREEN" "$RESET" "$1"; }

# ── 1. Node ──────────────────────────────────────────────
if ! command -v node >/dev/null 2>&1; then
  die "这台电脑上没有 Node.js" "去 https://nodejs.org 下载安装（选 LTS 版本），装完再双击一次这个文件"
fi
NODE_MAJOR="$(node -p 'process.versions.node.split(".")[0]' 2>/dev/null)"
if [ -z "$NODE_MAJOR" ] || [ "$NODE_MAJOR" -lt 22 ]; then
  die "Node.js 版本太低（当前 v${NODE_MAJOR:-?}，需要 22 或更高）" "去 https://nodejs.org 下载新版装上，再双击一次这个文件"
fi
ok "Node.js v$(node -p 'process.versions.node')"

# ── 2. 最新代码 ──────────────────────────────────────────
# 只在干净的树上拉。有未提交的改动就跳过——不能替用户丢掉他的工作。
if command -v git >/dev/null 2>&1 && git -C "$REPO" rev-parse --git-dir >/dev/null 2>&1; then
  if [ -z "$(git -C "$REPO" status --porcelain 2>/dev/null)" ]; then
    step "正在检查更新……"
    if git -C "$REPO" pull --ff-only >/dev/null 2>&1; then
      ok "代码已是最新"
    else
      ok "跳过更新（现在拉不动，用本地这份继续）"
    fi
  else
    ok "跳过更新（本地有未提交的改动，不动它）"
  fi
fi

# ── 3. 依赖 ──────────────────────────────────────────────
cd "$APP" || die "找不到程序目录" "确认这个文件还在 CyberBoss 文件夹里"
if [ ! -d node_modules ]; then
  step "正在下载依赖，第一次会慢一点（几分钟）……"
  npm install --omit=dev --silent >/dev/null 2>&1 \
    || die "依赖下载失败" "多半是网络问题。连上网再双击一次这个文件"
fi
ok "依赖就绪"

# ── 4. 命令 ──────────────────────────────────────────────
if ! command -v cyberboss >/dev/null 2>&1; then
  step "正在安装 cyberboss 命令……"
  npm install -g . --silent >/dev/null 2>&1 || true
fi
# 装不进 PATH 也没关系：下面直接用绝对路径跑，用户照样能用。
if command -v cyberboss >/dev/null 2>&1; then
  ok "命令已安装（以后终端里敲 cyberboss 也能启动）"
  LAUNCH=(cyberboss)
else
  ok "就绪"
  LAUNCH=(node "$APP/bin/cyberboss.js")
fi

printf '\n%s────────────────────────────────────%s\n\n' "$DIM" "$RESET"

# ── 5. 跑起来 ────────────────────────────────────────────
"${LAUNCH[@]}"
CODE=$?

printf '\n'
if [ $CODE -ne 0 ]; then
  printf '%s上面这段红字说明了问题和下一步。%s\n' "$DIM" "$RESET"
fi
printf '%s按回车键关闭这个窗口。%s' "$DIM" "$RESET"
read -r _
