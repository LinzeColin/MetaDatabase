#!/bin/bash
# 双击这个文件，把服务器上的收藏同步进你的 Obsidian 库。
#
# **这个文件是自包含的** —— 不依赖任何别的脚本。
# 为什么：上一版它指向 `_scratch/…` 里的脚本，而 `_scratch/` 按规矩就是放临时
# 产物的，今天已经有另一棵 worktree 在半路整个消失过。Owner 唯一能用的工具
# 不该挂在一个随时会被回收的目录上。
#
# 需要的东西：ssh 能连上 linze-ovh（已经配好），以及 python3（macOS 自带）。
set -uo pipefail

HOST="${SOCIAL_ARCHIVE_HOST:-linze-ovh}"
VAULT="${1:-$HOME/Documents/Obsidian}"
SUBDIR="${SOCIAL_ARCHIVE_OBSIDIAN_SUBDIR:-Social Archive}"
ONLY="${SOCIAL_ARCHIVE_ONLY_RELATION:-}"
REMOTE="/var/lib/social-archive/exports/markdown"

clear
echo "把收藏同步到 Obsidian"
echo "────────────────────────────────"
echo

finish() {
  echo
  echo "────────────────────────────────"
  echo "$1"
  echo
  read -n 1 -s -r -p "按任意键关闭这个窗口"
  echo
  exit "${2:-0}"
}

[[ -d "$VAULT" ]] || finish "找不到 Obsidian 库：$VAULT（把库路径当第一个参数传进来）" 2

TARGET="$VAULT/$SUBDIR"
mkdir -p "$TARGET"
STAMP="$(date +%Y%m%dT%H%M%S)"
TGZ="$(mktemp -t sa-md).tgz"
STAGE="$(mktemp -d -t sa-md-stage)"

echo "从 $HOST 取…"
if ! ssh -o ConnectTimeout=25 "$HOST" \
      "sudo tar -C /var/lib/social-archive/exports -czf /tmp/sa-md-$STAMP.tgz markdown \
       && sudo chmod 644 /tmp/sa-md-$STAMP.tgz"; then
  finish "连不上服务器，或者服务器上还没有导出的 Markdown。把这段截给我就行。" 3
fi
scp -q -o ConnectTimeout=25 "$HOST:/tmp/sa-md-$STAMP.tgz" "$TGZ" || finish "取回失败。" 3
ssh -o ConnectTimeout=20 "$HOST" "sudo rm -f /tmp/sa-md-$STAMP.tgz" >/dev/null 2>&1
tar -xzf "$TGZ" -C "$STAGE" --strip-components=1 || finish "压缩包解不开。" 3
rm -f "$TGZ"

# **合并进库之前先修标题。** 抖音那条取数路把「互动数 + 文案 + 文案」拼成了标题，
# 服务器上那批是修复上线之前生成的。只修能自证的那一档：去掉纯数字前缀之后
# 左右两半完全相同——其余一个字不碰。**不修的话，重跑会和已经修好的那份撞成两个文件。**
python3 - "$STAGE" "$ONLY" <<'PYEOF'
import re, sys, pathlib
stage, only = pathlib.Path(sys.argv[1]), (sys.argv[2] if len(sys.argv) > 2 else "")
DIGITS = re.compile(r"^\d+(?:\.\d+)?(?:万|w)?$")
HEAD = re.compile(r"^# (.+)$", re.M)
TAIL = re.compile(r"-([0-9a-f]{8})\.md$")
UNSAFE = re.compile(r"[\\/:*?\"<>|#\[\]^]")

def clean(text):
    for i in range(0, min(len(text), 8) + 1):
        prefix, rest = text[:i], text[i:]
        if prefix and not DIGITS.match(prefix):
            continue
        half = len(rest) // 2
        if half > 3 and rest[:half] == rest[half:]:
            return rest[:half].strip()
    return text

kept = dropped = fixed = 0
counts = {}
for md in sorted(stage.rglob("*.md")):
    body = md.read_text(encoding="utf-8")
    rels = re.search(r'^relation_types:\s*\[(.*?)\]', body, re.M)
    names = re.findall(r'"([a-z_]+)"', rels.group(1)) if rels else []
    for name in names:
        counts[name] = counts.get(name, 0) + 1
    if only and only not in names:
        md.unlink(); dropped += 1; continue
    kept += 1
    found = HEAD.search(body)
    if not found:
        continue
    new = clean(found.group(1).strip())
    if new == found.group(1).strip():
        continue
    fixed += 1
    md.write_text(body[:found.start(1)] + new + body[found.end(1):], encoding="utf-8")
    tail = TAIL.search(md.name)
    slug = UNSAFE.sub("", new).strip()[:80] if tail else ""
    if slug:
        target = md.with_name(f"{slug}-{tail.group(1)}.md")
        if not target.exists():
            md.rename(target)

print(f"  修好 {fixed} 个标题" + (f"，按「{only}」筛掉 {dropped} 条" if only else ""))
print("\n按关系类型（读 frontmatter 数出来的）：")
for name in sorted(counts, key=lambda k: -counts[k]):
    print(f"  {name:<14} {counts[name]}")
PYEOF
[[ $? -eq 0 ]] || finish "整理文件时出错了。" 4

BEFORE="$(find "$TARGET" -name '*.md' 2>/dev/null | wc -l | tr -d ' ')"
rsync -a "$STAGE"/ "$TARGET"/ || finish "写进 Obsidian 库时失败了。" 5
rm -rf "$STAGE"
AFTER="$(find "$TARGET" -name '*.md' 2>/dev/null | wc -l | tr -d ' ')"

echo
echo "放进来了：$TARGET"
echo "  这次之前 $BEFORE 个，现在 $AFTER 个"
for platform in douyin bilibili xiaohongshu x generic-web kuaishou reddit instagram; do
  n="$(find "$TARGET/$platform" -name '*.md' 2>/dev/null | wc -l | tr -d ' ')"
  if [[ "$n" != "0" ]]; then printf '  %-14s %s\n' "$platform" "$n"; fi
done

finish "好了。打开 Obsidian，左边那个「$SUBDIR」文件夹里就是。" 0
