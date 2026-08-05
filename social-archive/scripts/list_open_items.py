#!/usr/bin/env python3
"""把散在证据里的「还没做」汇总成一张清单（v0.0.0.7）。

## 为什么需要它

证据文件里到处是 `NOT_RUN`、`still_open`、`what_this_does_not_prove`。
每一条写下来的时候都是诚实的，问题在于**没有任何地方把它们汇到一起**。

本轮的教训很具体：我在 T15 的证据里亲手写过
「SYNC_QUEUE_LAST_RESULT_KEY 写了四处、没有任何界面读它」，
然后修了另一半就当整件事结了——**那句话原样躺在证据里过了很多轮**，
直到另一道门（find_write_only_storage_keys）独立地又抓到一次。

**记录下来不等于处理掉了。** 写进证据只保证「以后有人能查到」，
不保证「有人会查」。这个脚本让它每次跑发布门时都露一次面。

## 它不是门

未完成项本来就该存在——T06 的 Oracle 要 Owner 登录，T18 要部署。
所以它**只报数、只列出，永远退出 0**。让它变红只会逼人删条目。
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
EVIDENCE = ROOT / "evidence"

# 只看这一版的证据；历史版本（SA-xxx）是考古，不是待办。
IN_SCOPE = re.compile(r"^T\d\d$")

OPEN_MARKERS = ("NOT_RUN", "still_open", "still_missing", "still_unfixed",
                "what_is_still_missing", "待做", "未验", "尚未")

# **键名是当时起的，正文才是后来的结论。**
#
# `still_unfixed_nearby` 这种键名一旦写下就不会有人回去改，而它的正文
# 后来被更新成「**已修（2026-08-04）**」。于是这份清单把它继续报成未完成——
# 2026-08-05 实测 21 条里至少有 2 条是这样。
#
# **但脚本不替人下结论。** 只标出「正文里出现了表示已解决的词」，
# 请人去确认并把键名改掉。自动改判的话，像
# 「…仍未实现。但推迟的理由已经不成立」这种句子会被误判成已解决——
# 我第一次拿关键词筛就正好踩中这条。
RESOLVED_HINTS = ("已修", "已经建好", "已完成", "已接上", "已解决", "已经不成立")


def walk(node: object, path: str, out: list[str]) -> None:
    if isinstance(node, dict):
        for key, value in node.items():
            here = f"{path}.{key}" if path else str(key)
            # **父层已经说了「这条不成立了」，子层就不是待办。**
            #
            # T06 那份把作废的旧说法收在 `已经不成立的` 底下，
            # 而旧说法本身带着「尚未」二字——于是它被当成未完成项报出来。
            # 那不是待办，是**一条被引用的、已经失效的旧话**。
            if any(word in path for word in ("已经不成立", "已解决", "已修")):
                continue
            if any(m in str(key) for m in OPEN_MARKERS):
                if isinstance(value, str):
                    out.append(f"{here}: {value[:150]}")
                elif isinstance(value, list):
                    for item in value:
                        out.append(f"{here}: {str(item)[:150]}")
                else:
                    out.append(here)
            else:
                walk(value, here, out)
    elif isinstance(node, list):
        for index, item in enumerate(node):
            walk(item, f"{path}[{index}]", out)
    elif isinstance(node, str) and "NOT_RUN" in node:
        out.append(f"{path}: {node[:150]}")


def main() -> int:
    files = sorted(
        p for p in EVIDENCE.rglob("*.json")
        if IN_SCOPE.match(p.parent.name) or p.parent.name == "evidence"
    )
    total = 0
    per_task: dict[str, list[str]] = {}
    looks_done: list[str] = []
    for path in files:
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        found: list[str] = []
        walk(data, "", found)
        if found:
            key = f"{path.parent.name}/{path.name}"
            per_task[key] = found
            total += len(found)
            for item in found:
                if any(hint in item for hint in RESOLVED_HINTS):
                    looks_done.append(f"{key}: {item}")

    print(f"v0.0.0.7 证据里记录在案的未完成项：{total} 条，分布在 {len(per_task)} 份文件")
    verbose = "--verbose" in sys.argv or "-v" in sys.argv
    for key in sorted(per_task):
        items = per_task[key]
        print(f"  {key}（{len(items)} 条）")
        if verbose:
            for item in items:
                print(f"      · {item}")
    if looks_done:
        print(f"\n其中 **{len(looks_done)} 条的正文里出现了「已修 / 已经建好 / 已经不成立」这类词**——"
              "键名还叫 still_* / NOT_RUN，所以它们仍被算进上面那个数：")
        for item in looks_done:
            print(f"  · {item[:150]}")
        print("  ↳ **脚本不替你下结论**：请逐条确认，确实做完了就把键名改掉，"
              "否则这份清单会越来越像狼来了。（有的句子是"
              "「…仍未实现。但推迟的理由已经不成立」，那种仍是未完成。）")
    if not verbose:
        print("\n（加 --verbose 看每一条。这不是门，永远退出 0——"
              "未完成项本来就该存在，让它变红只会逼人删条目。）")
    return 0


if __name__ == "__main__":
    sys.exit(main())
