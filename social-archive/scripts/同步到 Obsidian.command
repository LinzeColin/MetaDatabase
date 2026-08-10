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

# **生产是哪台，只有一个真源**（仓里的 deploy/PRODUCTION_HOST）。
# 这个文件是给他双击的、必须自包含，所以这里写的是那一刻的值；
# 换机器时由 scripts/refresh_desktop_launcher.py 一起刷新。
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

# **两条取法：浏览器下载的 zip，或者 ssh 拉。**
#
# 新生产机（OVH VPS-3，2026-08-10 起）**对公网只开 80/443**，ssh 不对外——
# 也就是说「ssh + tar」这条路在新机器上不是暂时连不上，是**根本走不通**。
# 所以默认先看下载文件夹：资料库页面右上角那个「下载全部 Markdown」点一下，
# 拿到的 zip 放着不用管，双击这个文件就会把它展开进库。
# ssh 那条留着，能连上时照旧能用（本机/旧机/以后开了 ssh 的机器）。
ZIP="${SOCIAL_ARCHIVE_MARKDOWN_ZIP:-}"
if [[ -z "$ZIP" ]]; then
  # 最近 3 天内、下载文件夹里最新的那个 Markdown 压缩包
  ZIP="$(find "$HOME/Downloads" -maxdepth 1 -type f \( -name 'markdown*.zip' -o -name '*social-archive*markdown*.zip' \) -mtime -3 2>/dev/null \
        | xargs -I{} stat -f '%m %N' {} 2>/dev/null | sort -rn | head -1 | cut -d' ' -f2-)"
fi

if [[ -n "$ZIP" && -f "$ZIP" ]]; then
  echo "用下载好的压缩包：$(basename "$ZIP")"
  if ! unzip -q -o "$ZIP" -d "$STAGE"; then
    finish "这个压缩包解不开：$ZIP" 3
  fi
  # 包里可能带一层顶层目录，也可能不带——现看，别假设
  if [[ ! -d "$STAGE/douyin" && ! -d "$STAGE/bilibili" ]]; then
    inner="$(find "$STAGE" -maxdepth 2 -type d \( -name douyin -o -name bilibili -o -name xiaohongshu \) | head -1)"
    [[ -n "$inner" ]] && STAGE="$(dirname "$inner")"
  fi
else
  echo "从 $HOST 取…"
  if ! ssh -o ConnectTimeout=25 "$HOST" \
        "sudo tar -C /var/lib/social-archive/exports -czf /tmp/sa-md-$STAMP.tgz markdown \
         && sudo chmod 644 /tmp/sa-md-$STAMP.tgz"; then
    finish "连不上服务器（新生产机对公网不开 ssh），下载文件夹里也没有 Markdown 压缩包。
  换个做法：打开资料库页面 → 右上角「下载全部 Markdown」→ 再双击这个文件。" 3
  fi
  scp -q -o ConnectTimeout=25 "$HOST:/tmp/sa-md-$STAMP.tgz" "$TGZ" || finish "取回失败。" 3
  ssh -o ConnectTimeout=20 "$HOST" "sudo rm -f /tmp/sa-md-$STAMP.tgz" >/dev/null 2>&1
  tar -xzf "$TGZ" -C "$STAGE" --strip-components=1 || finish "压缩包解不开。" 3
fi
rm -f "$TGZ"

# **合并进库之前先修标题。** 抖音那条取数路把「互动数 + 文案 + 文案」拼成了标题，
# 服务器上那批是修复上线之前生成的。只修能自证的那一档：去掉纯数字前缀之后
# 左右两半完全相同——其余一个字不碰。**不修的话，重跑会和已经修好的那份撞成两个文件。**
python3 - "$STAGE" "$ONLY" <<'PYEOF'
import re, sys, pathlib
stage, only = pathlib.Path(sys.argv[1]), (sys.argv[2] if len(sys.argv) > 2 else "")
dropped = 0
counts = {}
for md in sorted(stage.rglob("*.md")):
    body = md.read_text(encoding="utf-8")
    rels = re.search(r'^relation_types:\s*\[(.*?)\]', body, re.M)
    names = re.findall(r'"([a-z_]+)"', rels.group(1)) if rels else []
    for name in names:
        counts[name] = counts.get(name, 0) + 1
    if only and only not in names:
        md.unlink(); dropped += 1
if only:
    print(f"  按「{only}」筛掉 {dropped} 条")
print("\n按关系类型（读 frontmatter 数出来的）：")
for name in sorted(counts, key=lambda k: -counts[k]):
    print(f"  {name:<14} {counts[name]}")
PYEOF
[[ $? -eq 0 ]] || finish "整理文件时出错了。" 4

BEFORE="$(find "$TARGET" -name '*.md' 2>/dev/null | wc -l | tr -d ' ')"
rsync -a "$STAGE"/ "$TARGET"/ || finish "写进 Obsidian 库时失败了。" 5
rm -rf "$STAGE"

# **修标题 + 去重，做在库上而不是下载的那份上。**（2026-08-10 第二次踩同一个坑）
#
# 第一版只修从服务器下来的那份，而库里还留着上一轮同步的旧文件名——
# rsync 只加不删，于是新旧名字并存，他库里 193 变 198、5 个重复。
# **同一个错我犯了两次。** 做在库上就自愈：不管文件从哪来、上一轮留了什么，
# 跑完都收敛到同一个状态。
python3 - "$TARGET" <<'PYEOF'
import re, sys, pathlib, collections
vault = pathlib.Path(sys.argv[1])
DIGITS = re.compile(r"^\d+(?:\.\d+)?(?:万|w)?$")
HEAD = re.compile(r"^# (.+)$", re.M)
TAIL = re.compile(r"-([0-9a-f]{8})\.md$")
UNSAFE = re.compile(r"[\\/:*?\"<>|#\[\]^]")

def clean(text):
    text = text.strip()
    if text and DIGITS.match(text):
        return ""
    for i in range(0, min(len(text), 8) + 1):
        prefix, rest = text[:i], text[i:]
        if prefix and not DIGITS.match(prefix):
            continue
        half = len(rest) // 2
        if half >= 3 and rest[:half] == rest[half:]:
            return rest[:half].strip()
    return text

def url_label(body):
    m = re.search(r'^url:\s*"?([^"\n]+)"?', body, re.M)
    if not m:
        return ""
    m2 = re.match(r"https?://([^/]+)(/.*)?$", m.group(1).strip())
    if not m2:
        return ""
    host = m2.group(1).replace("www.", "")
    tail = "/".join([p for p in (m2.group(2) or "").split("/") if p][-2:])
    return f"{host}/{tail}" if tail else host

fixed = removed_dupes = authors = 0
for md in sorted(vault.rglob("*.md")):
    body = md.read_text(encoding="utf-8")
    # 作者字段里装着点赞数的（抖音 86 条里 31 条），清成 null
    au = re.search(r'^author:\s*"([^"]*)"\s*$', body, re.M)
    if au and DIGITS.match(au.group(1).strip()):
        body = body[:au.start()] + "author: null" + body[au.end():]
        md.write_text(body, encoding="utf-8")
        authors += 1
    found = HEAD.search(body)
    if not found:
        continue
    old = found.group(1).strip()
    new = clean(old) or url_label(body)
    if not new or new == old:
        continue
    fixed += 1
    md.write_text(body[:found.start(1)] + new + body[found.end(1):], encoding="utf-8")
    tail = TAIL.search(md.name)
    # **按字节截，不是按字符。**（2026-08-10 在生产导出目录上真崩过）
    #   OSError: [Errno 36] File name too long: '…咕咕嘎嘎😜咕咕嘎嘎🤪…-af61d356.md'
    # ext4/APFS 限 255 字节，中文 3 字节、emoji 4 字节——80 个字符能到 320 字节。
    # 他库里就有一个 268 字节的文件名，所以这不是理论问题。
    slug = ""
    if tail:
        slug = UNSAFE.sub("", new).strip()
        keep = 240 - len(f"-{tail.group(1)}.md".encode())
        while len(slug.encode()) > keep and slug:
            slug = slug[:-1]
    if slug:
        target = md.with_name(f"{slug}-{tail.group(1)}.md")
        if target == md:
            pass
        elif target.exists():
            # **正确命名的那一份已经在了 —— 这一份是重复的，删掉。**
            # 不删的话：服务器每次都把旧名字带回来，改完标题却因为
            # 「目标已存在」跳过重命名，两份并存且标题都干净，去重也分不出该删谁。
            # 他库里因此从 193 涨到 246、52 个重复，而且**稳定在错的状态**。
            md.unlink(); removed_dupes += 1; continue
        else:
            md.rename(target)

# 同一条内容留一个文件：按那 8 位哈希分组，保留标题已经干净的那份
groups = collections.defaultdict(list)
for md in vault.rglob("*.md"):
    m = TAIL.search(md.name)
    if m:
        groups[m.group(1)].append(md)
removed = 0
for _, files in groups.items():
    if len(files) < 2:
        continue
    # **同一条内容只留一个文件。**（2026-08-10 第三次踩这个坑）
    #
    # 前两次的判据是「保留标题已经干净的那份」。而我在**服务器**上也跑了一次
    # 修复、改了 48 个文件名之后，rsync 把新名字带进来，库里出现了
    # **两份标题都干净、只是文件名不同**的情况——那条规则分不出该删谁，
    # 于是 193 变 198。
    #
    # 改成看**文件名是不是它自己标题该有的样子**（规范名），留规范的那份。
    # 都不规范就留第一个——总之只留一个。
    def canonical(f):
        h = HEAD.search(f.read_text(encoding="utf-8"))
        title = (h.group(1).strip() if h else "")
        want = UNSAFE.sub("", clean(title) or url_label(f.read_text(encoding="utf-8")) or title).strip()
        keep = 240 - len(f".md".encode()) - 9
        while len(want.encode()) > keep and want:
            want = want[:-1]
        m = TAIL.search(f.name)
        return bool(m) and f.name == f"{want}-{m.group(1)}.md"
    scored = [(canonical(f), f) for f in files]
    good = [f for ok, f in scored if ok] or [files[0]]
    for f in files:
        if f != good[0]:
            f.unlink(); removed += 1

total_removed = removed + removed_dupes
print(f"  库里修好 {fixed} 个标题" + (f"、{authors} 处作者字段" if authors else "") + (f"，清掉 {total_removed} 个重复文件" if total_removed else ""))

# **把库里现在的成分打出来。**（2026-08-10）
# 用「只补收藏」跑完，屏幕上是「按 favorite 筛掉 147 条 / 这次之前 193 个，现在 193 个」
# ——**看起来像什么都没发生**。真相是那些非收藏的早就在库里了（上几轮全量同步放进去的），
# 这个按钮只管少放新的进来、不删旧的。屏幕得把这件事说清楚。
kinds = collections.Counter()
for md in vault.rglob("*.md"):
    m = re.search(r'^relation_types:\s*\[(.*?)\]', md.read_text(encoding="utf-8"), re.M)
    for name in (re.findall(r'"([a-z_]+)"', m.group(1)) if m else []):
        kinds[name] += 1
if kinds:
    zh = {"favorite": "收藏", "like": "点赞", "history": "观看历史", "saved": "已保存",
          "watch_later": "稍后再看", "manual_save": "手动存的", "bookmark": "书签"}
    print("  你库里现在：" + " · ".join(f"{zh.get(k, k)} {v}" for k, v in kinds.most_common()))
    others = sum(v for k, v in kinds.items() if k != "favorite")
    if kinds.get("favorite") and others:
        print(f"  （收藏之外那 {others} 条是早期版本抓进来的；这两个按钮都不删你库里已有的东西）")
PYEOF
AFTER="$(find "$TARGET" -name '*.md' 2>/dev/null | wc -l | tr -d ' ')"

echo
echo "放进来了：$TARGET"
echo "  这次之前 $BEFORE 个，现在 $AFTER 个"
for platform in douyin bilibili xiaohongshu x generic-web kuaishou reddit instagram; do
  n="$(find "$TARGET/$platform" -name '*.md' 2>/dev/null | wc -l | tr -d ' ')"
  if [[ "$n" != "0" ]]; then printf '  %-14s %s\n' "$platform" "$n"; fi
done

finish "好了。打开 Obsidian，左边那个「$SUBDIR」文件夹里就是。" 0
