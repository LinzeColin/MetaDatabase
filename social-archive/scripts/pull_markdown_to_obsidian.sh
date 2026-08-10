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

# **只要某一种关系时，在这里筛掉。**（2026-08-10）
#
# 为什么要有这个：Owner 库里 86 条抖音，**69 条是「点赞」，只有 16 条是「收藏」**
# ——那 69 条是 2026-08-03 旧版本代码带进来的（现在的取数路对抖音只扫收藏）。
# 他要的是收藏夹，而库里八成不是。**默认一条不丢**，要挑就显式挑。
#
#   SOCIAL_ARCHIVE_ONLY_RELATION=favorite bash scripts/pull_markdown_to_obsidian.sh
ONLY="${SOCIAL_ARCHIVE_ONLY_RELATION:-}"
if [[ -n "$ONLY" ]]; then
  printf '只要 relation_types 含「%s」的那些…\n' "$ONLY"
  while IFS= read -r file; do
    grep -q "\"$ONLY\"" <(sed -n '1,/^---$/p;/^---$/,/^---$/p' "$file" | grep '^relation_types:') || rm -f "$file"
  done < <(find "$STAGE" -name '*.md')
fi

# **合并进库之前先修标题。**（2026-08-10）
#
# 服务器上那批文件是「标题修复」上线之前生成的（部署卡在主机磁盘 5G 闸门上），
# 所以拉下来还是「互动数 + 文案 + 文案」。2026-08-10 因为漏了这一步出过事故：
# 我在他库里手工修好 47 个标题、连文件名一起换，**接着又跑了一次这个脚本**，
# rsync 把服务器那份脏的又加回来——同一条内容两个文件，他库里从 194 变 241。
# **是我把他的库弄乱的。** 修法不是「记得别重跑」，是在这里先修。
PY_BIN="$(dirname "$0")/../.venv/bin/python"
[[ -x "$PY_BIN" ]] || PY_BIN="python3"
"$PY_BIN" "$(dirname "$0")/repair_markdown_titles.py" "$STAGE" --apply

BEFORE="$(find "$TARGET" -name '*.md' 2>/dev/null | wc -l | tr -d ' ')"
rsync -a "$STAGE"/ "$TARGET"/

# **把成分如实报出来。** 他要的是收藏夹；不说清楚的话，
# 一堆点赞混在里面而他不知道——那和「没做」差不多。
printf '\n按关系类型（读 frontmatter 数出来的）：\n'
for rel in favorite like history saved watch_later manual_save bookmark; do
  n="$(grep -rl "\"$rel\"" "$STAGE" --include='*.md' 2>/dev/null | wc -l | tr -d ' ')"
  [[ "$n" != "0" ]] && printf '  %-14s %s\n' "$rel" "$n"
done

rm -rf "$STAGE"
AFTER="$(find "$TARGET" -name '*.md' 2>/dev/null | wc -l | tr -d ' ')"

printf '\n放进来了：%s\n' "$TARGET"
printf '  这次之前 %s 个 md，现在 %s 个\n' "$BEFORE" "$AFTER"
for platform in douyin bilibili xiaohongshu x generic-web; do
  count="$(find "$TARGET/$platform" -name '*.md' 2>/dev/null | wc -l | tr -d ' ')"
  [[ "$count" != "0" ]] && printf '  %-14s %s\n' "$platform" "$count"
done
printf '\n打开 Obsidian，左边就会多一个「%s」文件夹。\n' "$SUBDIR"
