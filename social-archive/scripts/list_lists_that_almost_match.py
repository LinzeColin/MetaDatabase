#!/usr/bin/env python3
"""全仓找「几乎一样但不完全一样」的字符串清单（v0.0.0.7）。

## 它要抓的是什么

同一个概念被抄在好几处，然后**其中一处漏了一项**。这一类缺陷的特点是：
没有异常、没有失败码、没有零——只是某个界面比别处少认一种情况。

2026-08-06 实测到的那次：「同步还在跑」那七个状态在全仓有 **14 处**，
其中 **5 处少了 `authorizing`**。后果是账号正在授权那一段，
弹窗的活动计数是 0、不显示进度、不去轮询——**明明在跑，界面说没在跑**。

**按名字搜是搜不齐的**：同一个概念在扩展里就有三个名字
（`ACTIVE_SYNC_STATES` / `activeStates` / `running`），还有 8 处压根没有名字。
所以这个脚本**按内容认**：把每一段字面量里的字符串收成集合，
两两比相似度，只报「像得可疑但又不相同」的那些。

## 为什么它不是一道门

今天跑出来 18 对，**逐个看过，全都是有意的变体**
（多一个 `paused`、多一个 `blocked_environment`、多一个 `healthy`…）。
要把它做成门，就得把这 18 对全登记成白名单——**而那么大的白名单会变成摆设**，
这一天已经因为「装饰性白名单」返工过一次。

所以它是**给人看的清单**，永远退出 0（和 `list_open_items.py` 同一个定位）。
它的价值在于：改动一处概念清单之后跑一遍，看有没有把某一处落下。

## 用法

    python3 scripts/list_lists_that_almost_match.py            # 默认 70% 起报
    python3 scripts/list_lists_that_almost_match.py --min 0.85 # 只看更像的
"""

from __future__ import annotations

import argparse
import itertools
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
LITERAL = re.compile(r"[\[\{\(][^\[\]\{\}\(\)]{15,400}[\]\}\)]", re.S)
NAME = re.compile(r'"([a-z][a-z0-9_]{2,30})"')


def _groups() -> list[tuple[str, int, frozenset[str]]]:
    out: list[tuple[str, int, frozenset[str]]] = []
    for folder in ("src", "apps"):
        base = ROOT / folder
        if not base.is_dir():
            continue
        for path in sorted(base.rglob("*")):
            if not path.is_file() or path.suffix not in (".py", ".js"):
                continue
            if "__pycache__" in str(path):
                continue
            text = path.read_text(encoding="utf-8", errors="ignore")
            for match in LITERAL.finditer(text):
                names = frozenset(NAME.findall(match.group(0)))
                if len(names) >= 3:
                    out.append((str(path.relative_to(ROOT)),
                                text[: match.start()].count("\n") + 1, names))
    return out


def main() -> int:
    parser = argparse.ArgumentParser(description="找几乎一样但不完全一样的字符串清单")
    parser.add_argument("--min", type=float, default=0.70, help="相似度下限（Jaccard）")
    args = parser.parse_args()

    groups = _groups()
    print(f"扫了 src/ 与 apps/ 下 {len(groups)} 段字符串清单（每段至少 3 个）")
    if not groups:
        # **一段都没扫到，和「没有可疑的」长得一样。**
        print("**一段都没扫到**——这不是「干净」，是这个脚本的射程失效了。")
        return 0

    seen: set[tuple] = set()
    hits: list[tuple] = []
    for (f1, l1, a), (f2, l2, b) in itertools.combinations(groups, 2):
        if a == b or not (a & b):
            continue
        score = len(a & b) / len(a | b)
        if score < args.min:
            continue
        key = (tuple(sorted(a)), tuple(sorted(b)))
        if key in seen:
            continue
        seen.add(key)
        hits.append((score, f1, l1, f2, l2, sorted(a - b), sorted(b - a)))

    hits.sort(reverse=True)
    print(f"像得可疑、但不相同的成对：{len(hits)}（相似度 ≥ {args.min:.0%}）\n")
    for score, f1, l1, f2, l2, only_a, only_b in hits:
        print(f"  {score:.0%}  {f1}:{l1}")
        print(f"        {f2}:{l2}")
        print(f"        前者多：{only_a or '—'}    后者多：{only_b or '—'}")

    print("\n**这份清单不替你下结论。** 多出来的那一项可能是有意的变体"
          "（比如「可取消」那份要多一个 paused），也可能就是漏了一项。"
          "逐对看一眼；确实是有意的，最好在代码里写一句为什么。")
    # 永远退出 0：有意的变体本来就该存在，让它变红只会逼人删条目。
    return 0


if __name__ == "__main__":
    sys.exit(main())
