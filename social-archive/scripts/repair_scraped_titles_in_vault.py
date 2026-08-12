#!/usr/bin/env python3
r"""把他 Obsidian 库里从页面上抓歪的标题修回真标题（2026-08-12）。

判据和生产库那一份**共用同一份实现**（`social_archive.title_repair`），
两边不许各写一套——同一批文本两把尺子，今年已经撞过五次。

## 两边坏得不一样，都要修

生产库里抓重的有 11 条，他库里只有 1 条。差在哪儿：这些笔记是**抓重之前**
导出的，文件名和 `# ` 标题行都还是好的；后来某次同步把抓重的标题写回了库里，
而笔记没有重新导出，于是留住了好的那一份。

这件事顺带给了一个**不是我自己说了算**的验证：把生产库那 11 条按判据修回去，
逐条和他笔记里的原文比——**11 条一模一样，0 条对不上**。

剩下那 1 条（`2.2万厂二代卖掉父亲的公司…`）两边都坏了，所以两边都要修。

## 边界

- 只改判定得出来的那些，别的一律不碰。
- 动手之前整份复制一次到 **vault 之外**（`~/.social-archive-backups/`）。
  放在 vault 里面会让 Obsidian 多出一整份重复笔记——上一轮差点这样。
- 拿不回来就跳过并列出来，不猜。
- 默认干跑。
"""

from __future__ import annotations

import argparse
import json
import re
import shutil
import sys
import time
import urllib.request
from pathlib import Path

try:
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))
except NameError:                                            # exec 进来的（生产容器只读，cp 不进去）
    pass

from social_archive.title_repair import is_all_chrome_no_title, undouble_title  # noqa: E402
from social_archive.utils import safe_slug                                      # noqa: E402

DEFAULT_VAULT = Path.home() / "Documents/Obsidian"
SUBDIR = "Social Archive"
BV = re.compile(r"/video/(BV[0-9A-Za-z]+)")
TITLE_LINE = re.compile(r"^# (.+)$", re.M)
NULL_AUTHOR = re.compile(r"^author: null\s*$", re.M)
API = "https://api.bilibili.com/x/web-interface/view?bvid={bv}"
HEAD = {"User-Agent": "Mozilla/5.0", "Referer": "https://www.bilibili.com/"}
GONE_FOR_GOOD = {62002, -404, 62004}


def real_title(bv: str, attempts: int = 3) -> tuple[str, str] | str | None:
    """`(标题, 作者)` = 拿到了；字符串 = 确定没了；None = 这次没拿到。

    「没了」和「这次没拿到」必须分开：上次全量跑 56 条有 4 条失败，
    逐个复查只有 1 条真的 code=62002，另外 3 条只是被限流。
    """
    for attempt in range(attempts):
        try:
            with urllib.request.urlopen(
                    urllib.request.Request(API.format(bv=bv), headers=HEAD),
                    timeout=20) as response:
                payload = json.loads(response.read())
        except Exception:                                    # noqa: BLE001
            time.sleep(1.5 * (attempt + 1))
            continue
        code = payload.get("code")
        if code in GONE_FOR_GOOD:
            return f"稿件已不可见（code={code}）"
        if code != 0:
            time.sleep(1.5 * (attempt + 1))
            continue
        data = payload.get("data") or {}
        title = str(data.get("title") or "").strip()
        author = str((data.get("owner") or {}).get("name") or "").strip()
        if title:
            return (title, author)
    return None


def _rename_to_match(path: Path, title: str, renamed: list, apply: bool = True) -> Path:
    """文件名也跟着改回真标题。**不改会在下一次导出时多出一份。**

    导出那一侧按 `safe_slug(标题)-<id 后 8 位>.md` 起名。标题修好了而文件名还留着
    抓重的那一串，下次导出就会照新标题写出**另一个文件**，旧的原地不动——
    他打开 Obsidian 看到的是同一条内容两份。这个仓的笔记数被弄乱过两次
    （193→198→246），就是这个形状。

    尾部那 8 位是内容 id，**必须原样保留**：它是「同一条内容」的唯一凭据，
    查重那道门也是按它数的。
    """
    tail = path.stem.rsplit("-", 1)[-1]
    target = path.with_name(f"{safe_slug(title, tail)}-{tail}.md")
    if target == path or target.exists():
        return path
    renamed.append({"from": path.name[:44], "to": target.name[:44]})
    if not apply:                       # 干跑也要把要改的名字列出来（先出提案，后落盘）
        return path
    path.rename(target)
    return target


def main() -> int:
    parser = argparse.ArgumentParser(description="把他库里从页面上抓歪的标题修回真标题")
    parser.add_argument("--apply", action="store_true", help="真的写文件（默认只看不改）")
    parser.add_argument("--vault", default=str(DEFAULT_VAULT))
    parser.add_argument("--subdir", default=SUBDIR,
                        help="笔记在哪个子目录下。生产上那批导出的 markdown 用 `markdown`——`/v1/library/markdown.zip` 就是从它打的，那一份坏了他下载下来就是坏的")
    parser.add_argument("--limit", type=int, default=0)
    parser.add_argument("--backup-root", default=str(Path.home() / ".social-archive-backups"),
                        help="备份放哪儿——**必须在 vault 之外**，否则 Obsidian 里多出一份重复笔记")
    args = parser.parse_args()

    folder = Path(args.vault) / args.subdir
    if not folder.is_dir():
        print(json.dumps({"status": "SKIPPED", "why": f"{folder} 不在"}, ensure_ascii=False))
        return 0

    doubled, all_chrome = [], []
    for path in sorted(folder.rglob("*.md")):
        text = path.read_text(encoding="utf-8", errors="replace")
        found = TITLE_LINE.search(text)
        if not found:
            continue
        current = found.group(1)
        repaired = undouble_title(current)
        if repaired and repaired.strip() != current.strip():
            doubled.append((path, text, current, repaired))
        elif is_all_chrome_no_title(current):
            bv = BV.search(text)
            all_chrome.append((path, text, current, bv.group(1) if bv else None))
    if args.limit:
        doubled, all_chrome = doubled[:args.limit], all_chrome[:args.limit]

    backup = None
    if args.apply:
        backup = Path(args.backup_root) / f"social-archive-vault-titles-{int(time.time())}"
        backup.parent.mkdir(parents=True, exist_ok=True)
        shutil.copytree(folder, backup)

    fixed_locally, fixed_from_api, unresolved = [], [], []
    renamed: list = []

    # 第一趟：抓重的。不联网，所有平台都能修。
    for path, text, current, repaired in doubled:
        if args.apply:
            path.write_text(TITLE_LINE.sub(lambda _m: f"# {repaired}", text, count=1),
                            encoding="utf-8")
            path = _rename_to_match(path, repaired, renamed)
        fixed_locally.append({"file": path.name[:40], "old": current[:40], "new": repaired[:40]})

    # 第二趟：整串都是页面零件的。只有 B 站查得回来。
    for path, text, current, bv in all_chrome:
        if not bv:
            unresolved.append({"file": path.name[:40], "old": current,
                               "why": "没有 BV 号（抖音没有公开接口，要他的登录态）",
                               "kind": "no_public_source"})
            continue
        got = real_title(bv)
        time.sleep(0.7)
        if isinstance(got, str):
            unresolved.append({"file": path.name[:40], "old": current, "bv": bv,
                               "why": got, "kind": "gone_for_good"})
            continue
        if got is None:
            unresolved.append({"file": path.name[:40], "old": current, "bv": bv,
                               "why": "重试 3 次仍没拿到（多半是限流）", "kind": "transient"})
            continue
        title, author = got
        if args.apply:
            updated = TITLE_LINE.sub(lambda _m: f"# {title}", text, count=1)
            if author:
                updated = NULL_AUTHOR.sub(f'author: "{author}"', updated, count=1)
            path.write_text(updated, encoding="utf-8")
        fixed_from_api.append({"file": path.name[:40], "old": current, "new": title[:44]})

    # 第三趟：**文件名也得跟上标题**，否则下一次导出会多出一整批重复笔记。
    #
    # 2026-08-12 实测：他库里 193 篇有 **146 篇**的文件名还是修之前那个标题
    # slug 出来的（`00-00-14-48-0fc30463.md`——播放进度）。笔记里的标题昨天
    # 已经修好了，文件名没人管。两个后果，第二个更严重：
    #
    #   · 他在 Obsidian 侧边栏看到的仍然是一串时间码，认不出是什么；
    #   · 导出那一侧按 `safe_slug(标题)-<id 后 8 位>.md` 起名，**下一次导出会照
    #     新标题写出 146 个新文件，旧的原地不动** —— 193 篇变成 339 篇。
    #     这个仓的笔记数被弄乱过两次（193→198→246），就是这个形状。
    for path in sorted(folder.rglob("*.md")):
        found = TITLE_LINE.search(path.read_text(encoding="utf-8", errors="replace"))
        if found:
            _rename_to_match(path, found.group(1), renamed, apply=args.apply)

    kinds: dict[str, int] = {}
    for item in unresolved:
        kinds[item["kind"]] = kinds.get(item["kind"], 0) + 1
    print(json.dumps({
        "mode": "APPLIED" if args.apply else "DRY-RUN（没有改任何文件）",
        "notes": len(list(folder.rglob("*.md"))),
        "scraped_twice_fixed_without_network": len(fixed_locally),
        "all_chrome_looked_up_from_the_public_api": len(fixed_from_api),
        "still_broken_by_kind": kinds,
        "backup": str(backup) if backup else "（干跑不备份）",
        "renamed_to_match_the_title": len(renamed),
        "renames": renamed[:5],
        "samples_fixed_locally": fixed_locally[:4],
        "samples_fixed_from_api": fixed_from_api[:4],
        "unresolved": unresolved[:8],
    }, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
