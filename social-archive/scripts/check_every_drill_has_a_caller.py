#!/usr/bin/env python3
"""演练没有调用方，就等于没有演练（v0.0.0.22 / G3）。

## 为什么立这一道

2026-08-06 查了一遍：仓里 **15 个演练脚本，调用方是 0**。
不在发布门里、不在部署脚本里、不在任何文档的清单里——
它们唯一的触发方式是**我记得去跑**。

这不是假设的风险。同一天量到的：

  · 十一个真 Chrome 演练**全都加载源码目录**，而且加载前把
    `optional_host_permissions` 提升成 `host_permissions`。
    于是「他真正下载的那个包、在权限未授予的状态下会怎样」从没被走过。
  · 第一次真的去跑那个状态，当场发现读取失败时报的是
    「读不出当前页面的域名」——把人指向错的方向。

这个仓已经记下过同一句话：**判据没有调用方就不算做完**，
最贵的一次是 45 份 holdout 里 18 份从未真隔离，而判据早写好了却从没被打印过。

## 契约

每个 `scripts/*_drill.py` 必须在 `docs/DRILLS.md` 里有一行，写清**什么时候跑**：

    | 演练 | 什么时候跑 | 谁来跑 |

而标着「每次发布」的，必须真的出现在 `scripts/deploy_to_production.sh` 里——
**写在表里不算，要有人调它**。这一条正是这道门自己要防的东西，
所以它对自己也成立。

## 它不保证什么

不保证演练本身写得对，也不保证它最近跑过。只保证**有一条路会触发它**，
以及「什么时候跑」这件事写下来了、而不是留在某个人的记性里。
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
REGISTRY = ROOT / "docs" / "DRILLS.md"
DEPLOY = ROOT / "scripts" / "deploy_to_production.sh"
RELEASE_CADENCE = "每次发布"


def main() -> int:
    drills = sorted(path.name for path in (ROOT / "scripts").glob("*_drill.py"))
    problems: list[dict] = []
    if not drills:
        problems.append({"problem": "一个演练都没找到——这道门的射程失效了"})

    if not REGISTRY.is_file():
        print(json.dumps({
            "status": "FAIL", "error_code": "REGISTRY_MISSING",
            "path": str(REGISTRY.relative_to(ROOT)),
            "message_zh": "没有演练清单——每个演练都只靠人记得去跑",
        }, ensure_ascii=False, indent=2))
        return 4
    registry = REGISTRY.read_text(encoding="utf-8")
    deploy = DEPLOY.read_text(encoding="utf-8") if DEPLOY.is_file() else ""

    rows: dict[str, str] = {}
    for line in registry.splitlines():
        found = re.match(r"\|\s*`?(\w+_drill\.py)`?\s*\|\s*([^|]+)\|", line)
        if found:
            rows[found.group(1)] = found.group(2).strip()

    for name in drills:
        if name not in rows:
            problems.append({
                "drill": name,
                "problem": "清单里没有它——它唯一的触发方式是有人记得去跑。"
                           f"在 {REGISTRY.relative_to(ROOT)} 里补一行，写清什么时候跑",
            })
            continue
        if RELEASE_CADENCE in rows[name] and name not in deploy:
            problems.append({
                "drill": name,
                "problem": f"清单里写着「{RELEASE_CADENCE}」，"
                           "而部署脚本里没有调它——**写在表里不算，要有人调它**",
            })
    for name in sorted(set(rows) - set(drills)):
        problems.append({"drill": name,
                         "problem": "清单里有它，而 scripts/ 下没有这个文件——"
                                    "清单指着一个不存在的东西"})

    report = {
        "status": "PASS" if not problems else "FAIL",
        "drills_found": drills,
        "registry": str(REGISTRY.relative_to(ROOT)),
        "cadences": rows,
        "run_by_deploy": sorted(name for name in drills if name in deploy),
        "problems": problems,
        "message_zh": ("每个演练都有一条会触发它的路，或至少写清了什么时候跑。"
                       if not problems else
                       "**有演练没有任何调用方**——它等于不存在。"),
        "what_this_does_not_prove": (
            "不保证演练写得对，也不保证它最近跑过。只保证有一条路会触发它。"),
    }
    out = ROOT / "evidence/G3/DRILLS_HAVE_CALLERS.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if not problems else 4


if __name__ == "__main__":
    sys.exit(main())
