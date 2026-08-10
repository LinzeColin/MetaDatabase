#!/usr/bin/env bash
# 把服务器上已经导出的 Markdown 拉进你自己电脑上的 Obsidian 库。
#
# ## 为什么有这个
#
# Owner 的原话：「zzybrim/douyin-obsidian 别人已经开发成功了，你跑了十天了，
# 还没有结果」。去看他的实况：markdown 目的地 193/193——那 193 条
# （含 86 条抖音）2026-08-03 就全部生成成 Markdown 了，一直躺在服务器上；
# 而 obsidian 目的地是 1/193，且那个「库」是服务器上的一个目录，
# **和他电脑上的 Obsidian 之间没有任何通路**。
#
# 服务器够不着他的电脑，浏览器写不了任意本地路径——**能走通的是从他这边拉**。
# 这个脚本就是那一跳，在他自己的机器上跑，用他已经配好的 ssh。
#
# ## 用法
#
#   bash scripts/pull_markdown_to_obsidian.sh                 # 用默认库
#   bash scripts/pull_markdown_to_obsidian.sh /path/to/Vault  # 指定库
#
# 反复跑是安全的：同名文件覆盖，不删你自己写的东西
# （rsync 不带 --delete，所以你在那个文件夹里加的笔记不会被清掉）。
set -euo pipefail

HOST="${SOCIAL_ARCHIVE_HOST:-linze-ovh}"
VAULT="${1:-$HOME/Documents/Obsidian}"
SUBDIR="${SOCIAL_ARCHIVE_OBSIDIAN_SUBDIR:-Social Archive}"
REMOTE_EXPORT="/var/lib/social-archive/exports/markdown"

if [[ ! -d "$VAULT" ]]; then
  printf '找不到 Obsidian 库：%s\n' "$VAULT" >&2
  printf '把库的路径作为第一个参数传进来，例如：\n  bash %s ~/Documents/我的库\n' "$0" >&2
  exit 2
fi

TARGET="$VAULT/$SUBDIR"
mkdir -p "$TARGET"

# **服务器上那个目录要 sudo 才读得到**（属主是 socialarchive）。
# 先打成一个包再拉，避免 rsync 走 sudo 的那一堆麻烦。
STAMP="$(date +%Y%m%dT%H%M%S)"
REMOTE_TGZ="/tmp/sa-markdown-$STAMP.tgz"
LOCAL_TGZ="$(mktemp -t sa-markdown).tgz"

printf '从 %s 取…\n' "$HOST"
ssh -o ConnectTimeout=25 "$HOST" \
  "sudo tar -C '$(dirname "$REMOTE_EXPORT")' -czf '$REMOTE_TGZ' '$(basename "$REMOTE_EXPORT")' && sudo chmod 644 '$REMOTE_TGZ'"
scp -q -o ConnectTimeout=25 "$HOST:$REMOTE_TGZ" "$LOCAL_TGZ"
ssh -o ConnectTimeout=20 "$HOST" "sudo rm -f '$REMOTE_TGZ'"

# 解到临时目录再同步进库——**先落盘再合并**，中途失败不会把库弄成半截。
STAGE="$(mktemp -d -t sa-markdown-stage)"
tar -xzf "$LOCAL_TGZ" -C "$STAGE" --strip-components=1
rm -f "$LOCAL_TGZ"

BEFORE="$(find "$TARGET" -name '*.md' 2>/dev/null | wc -l | tr -d ' ')"
rsync -a "$STAGE"/ "$TARGET"/
rm -rf "$STAGE"
AFTER="$(find "$TARGET" -name '*.md' 2>/dev/null | wc -l | tr -d ' ')"

printf '\n放进来了：%s\n' "$TARGET"
printf '  这次之前 %s 个 md，现在 %s 个\n' "$BEFORE" "$AFTER"
for platform in douyin bilibili xiaohongshu x generic-web; do
  count="$(find "$TARGET/$platform" -name '*.md' 2>/dev/null | wc -l | tr -d ' ')"
  [[ "$count" != "0" ]] && printf '  %-14s %s\n' "$platform" "$count"
done
printf '\n打开 Obsidian，左边就会多一个「%s」文件夹。\n' "$SUBDIR"
