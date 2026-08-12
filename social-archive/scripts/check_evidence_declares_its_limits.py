#!/usr/bin/env python3
"""INV-HONEST-EVIDENCE 的机器落点（v0.0.0.7）。

## 为什么需要它

清点各不变量的守卫时发现：**INV-TRUTH-TRACEABLE、INV-REAL-USABLE、
INV-HONEST-EVIDENCE 三条一个判据都没有。** 它们只活在文档里。

三条里 INV-HONEST-EVIDENCE 是可以机器查的，因为它有两个明确形状：

  1. **写清「这不能证明什么」。** 一份只写做到了什么、不写没做到什么的
     证据，读的人会默认它什么都证明了。本会话反复出现的伪完成
     （T14 标完成而 app.js 没读失败码、T04 只用接口 JSON 验「出现在表格」）
     都是这么来的。

  2. **BLOCKED 不许被改写成 PASS。** 有四份证据自己写着
     `must_not_be_rewritten_as_pass: true`——那是过去的我对未来的我设的防线。
     防线要有人守才算数。

## 射程

只管 v0.0.0.7 的证据（`evidence/T00`–`T18` 与 `evidence/` 顶层）。
历史版本（SA-xxx）与命令流水（COMMAND_LOG）不追溯——那是考古，不是纪律。
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
EVIDENCE = ROOT / "evidence"

# 声明局限的写法不止一种，按**语义**认，不强求某个固定键名。
LIMIT_MARKERS = (
    "does_not_prove", "not_proven", "limitation", "still_open", "still_missing",
    "still_unfixed", "what_is_missing", "not_run", "acceptance_self_check",
)

# 机器生成的快照/流水不是「主张」，不要求它们声明局限。
GENERATED = {"final-verification.json", "COMMAND_LOG.json"}


def in_scope(path: Path) -> bool:
    if path.name in GENERATED:
        return False
    parent = path.parent.name
    return bool(re.match(r"^T\d\d$", parent)) or parent == "evidence"


def declares_limits(node: object) -> bool:
    if isinstance(node, dict):
        if any(any(m in str(k) for m in LIMIT_MARKERS) for k in node):
            return True
        return any(declares_limits(v) for v in node.values())
    if isinstance(node, list):
        return any(declares_limits(v) for v in node)
    return "NOT_RUN" in str(node)


def main() -> int:
    problems: list[str] = []
    checked = 0
    locked = 0

    for path in sorted(EVIDENCE.rglob("*.json")):
        if not in_scope(path):
            continue
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            problems.append(f"  {path.relative_to(ROOT)}：读不了（{exc.__class__.__name__}）")
            continue
        if not isinstance(data, dict):
            continue
        checked += 1

        # 规则 2：自己上过锁的，不许变成 PASS
        if data.get("must_not_be_rewritten_as_pass"):
            locked += 1
            status = str(data.get("status") or "").upper()
            if status.startswith("PASS") or status in {"DONE", "COMPLETE", "COMPLETED"}:
                problems.append(
                    f"  {path.relative_to(ROOT)}：标了 must_not_be_rewritten_as_pass，"
                    f"status 却是 {status!r}。**这是伪完成，不是进展。**"
                )

        # 规则 1：写清这不能证明什么
        if not declares_limits(data):
            problems.append(
                f"  {path.relative_to(ROOT)}：没有写「这不能证明什么」。"
                "只写做到了什么，读的人会默认它什么都证明了。"
            )

    print(f"检查 v0.0.0.7 证据 {checked} 份（其中自锁 {locked} 份）")
    if problems:
        print(f"**不合格 {len(problems)} 处**：")
        for line in problems:
            print(line)
        return 1
    print("每一份都写了局限；自锁的没有一份被改写成 PASS。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
