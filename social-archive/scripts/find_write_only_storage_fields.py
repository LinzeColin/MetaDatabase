#!/usr/bin/env python3
"""写进 chrome.storage 的**字段**里，有没有谁写了却没人读（2026-08-12）。

## 为什么在 `find_write_only_storage_keys.py` 之外还要一道

那道门查的是**键**——`"saAccountSyncQueueLock"` 这种字符串字面量。
2026-08-12 合并 main 时漏进来的那个东西它一个字都看不见：

    chrome.storage.local.set({ [SYNC_QUEUE_LOCK_KEY]: { ...lock, heartbeatAt: Date.now() } })

键是好的（`SYNC_QUEUE_LOCK_KEY` 有人读），**而 `heartbeatAt` 是键的值里面的
一个字段，全代码库再没有第二处提到它**。于是每同步一批就白写一次 storage，
换不来任何东西。那道门绿着，因为它压根不往值里看。

**发现它靠的是合并后逐行读 diff，不是门。** 这道门就是把那次手工阅读固化下来。

## 判据

找 `chrome.storage.*.set(` 后面那个对象字面量，取出里面的字段名，
逐个数它在 `apps/` 下出现几次。**只出现在写的那一处 = 没人读**。

## 它不保证什么

- 只看字面量里直接写出来的字段名；`{...spread}` 带进去的看不见。
- 字段名太短（<6 字符）不查——`id`/`url` 这种到处都是，数了也没意义。
- 「有人提到」不等于「真的读了」：这道门只往前推一格，和它旁边那道一样。
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
EXT = ROOT / "apps/browser-extension"

SET_CALL = re.compile(r"chrome\.storage\.\w+\.set\(")
FIELD = re.compile(r"\b([a-z][A-Za-z0-9]{5,})\s*:")

# 写了没人读、但**有意如此**的字段：写清谁在读，否则不许进这个表。
WRITE_ONLY_BY_DESIGN: dict[str, str] = {}


def _object_after(text: str, start: int) -> str:
    """从 `set(` 后面把那一个对象字面量原样取出来（按花括号配对）。"""
    depth, out, seen = 0, [], False
    for ch in text[start:start + 4000]:
        if ch == "{":
            depth += 1
            seen = True
        elif ch == "}":
            depth -= 1
        out.append(ch)
        if seen and depth == 0:
            break
    return "".join(out)


def main() -> int:
    import argparse
    parser = argparse.ArgumentParser(description="storage 里写了没人读的字段")
    parser.add_argument("--brief", action="store_true")
    args = parser.parse_args()

    files = sorted(EXT.rglob("*.js"))
    corpus = {f: f.read_text(encoding="utf-8") for f in files}
    whole = "\n".join(corpus.values())

    written: dict[str, str] = {}
    for path, text in corpus.items():
        for match in SET_CALL.finditer(text):
            for field in FIELD.findall(_object_after(text, match.end())):
                written.setdefault(field, path.name)

    unread = []
    for field, where in sorted(written.items()):
        if field in WRITE_ONLY_BY_DESIGN:
            continue
        # 出现一次 = 只有写的那一处。整行注释不算引用（说明文字不是代码）。
        code = "\n".join(l for l in whole.splitlines() if not l.lstrip().startswith("//"))
        if len(re.findall(rf"\b{re.escape(field)}\b", code)) <= 1:
            unread.append({"field": field, "written_in": where})

    report = {
        "status": "FAIL" if unread else "PASS",
        "files_scanned": len(files),
        "fields_written_into_storage": len(written),
        "written_but_never_read": unread,
        "message_zh": ("每个写进 storage 的字段都至少有第二处提到它。"
                       if not unread else
                       "**这些字段写进了 chrome.storage，而全代码库没有第二处提到它们**——"
                       "每写一次都是白写，且看起来像是记下来了。"),
        "what_this_does_not_prove":
            "只看字面量里直接写出的字段名（`{...spread}` 带进去的看不见）；"
            "「有人提到」也不等于「真的读了」——这道门只往前推一格。",
        "why_zh": "隔壁那道门查的是 storage 的**键**，看不见键的**值里面**的字段。"
                  "2026-08-12 合并时漏进来的 heartbeatAt 就是从那个缝里过去的。",
    }
    print(report["status"] if args.brief and not unread
          else json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if not unread else 1


if __name__ == "__main__":
    sys.exit(main())
