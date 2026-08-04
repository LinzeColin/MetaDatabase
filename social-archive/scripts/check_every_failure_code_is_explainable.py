#!/usr/bin/env python3
"""每一个失败码都要说得出人话（v0.0.0.7 / T14）。

## 为什么需要它

INV-NO-SILENT-ZERO 说的是「0 条时界面说得出为什么」。而失败文案词典是
**人手维护**的映射表——代码里新加一个失败码，没人提醒你去补词典。
补漏的后果不是少一句话，是界面说「我们没能记录下原因」，
而原因就写在 `last_error_code` 里。**明知原因却说不知道，比不说更糟。**

这一版里同一形态出现了两次：

  1. 生产库里躺着三个当前代码已删除的遗留码，词典不认（查数据才发现）
  2. **连接器层七个码整层没进过词典**（读代码就能发现，我只是没扫那一层）

第 2 条正是这个脚本要自动化的事：把「代码里到底有哪些失败码」
从「我记得扫过哪些文件」变成一条命令。

## 怎么找

按**写法**扫，不按文件列举——加一个新文件不会漏：

    Python   ConnectorError("CODE"      failure_code="CODE"
             "code": "CODE"             error_code="CODE"
    JS       failureCode: "CODE"        failure_code: "CODE"

只认 `^[A-Z][A-Z0-9_]{3,}$` 这种形状，避免把普通字符串当成码。

## 它不保证什么

只覆盖**字面量**。动态拼出来的码（`f"{prefix}_FAILED"`）扫不到——
所以别那样写失败码。
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

# 只扫**会走到界面**的路径。scripts/ 下的码是给运维看 systemd 日志的，
# 要求它们有中文界面文案是越界——但也别忘了它们仍然要能被人读懂。
SCAN_DIRS = ("src", "apps")
CODE_SHAPE = re.compile(r"^[A-Z][A-Z0-9_]{3,}$")

PATTERNS = (
    re.compile(r'ConnectorError\(\s*"([A-Z][A-Z0-9_]+)"'),
    re.compile(r'failure_code\s*[=:]\s*"([A-Z][A-Z0-9_]+)"'),
    re.compile(r'failureCode\s*[=:]\s*"([A-Z][A-Z0-9_]+)"'),
    re.compile(r'error_code\s*[=:]\s*"([A-Z][A-Z0-9_]+)"'),
    re.compile(r'"code"\s*:\s*"([A-Z][A-Z0-9_]+)"'),
    re.compile(r'code\s*:\s*"([A-Z][A-Z0-9_]+)"'),
)

# 不是失败码的大写字面量（状态、类型、算法名等）。每条写清它是什么。
NOT_A_FAILURE_CODE = {
    "L0", "L1", "L2", "L3",                       # 归档层级
    "UNEXPLAINED_ZERO",                           # 词典自己产生的兜底码
    "NOTHING_NEW", "SYNC_STALLED",                # 同上，由 describe_sync_outcome 产生
    "PLATFORM_MISMATCH",                          # 批次内条目级错误，不进 sync_run.last_error_code
    "CONTRACT_VIOLATION", "CONTRACTVIOLATION",    # 解析器内部标记
    "MISSINGBINARY",                              # 同上
}


def scan() -> dict[str, list[str]]:
    found: dict[str, list[str]] = {}
    for folder in SCAN_DIRS:
        base = ROOT / folder
        if not base.is_dir():
            continue
        for path in base.rglob("*"):
            if path.suffix not in {".py", ".js"} or not path.is_file():
                continue
            if path.resolve() == Path(__file__).resolve():
                continue  # 别把自己的正则字面量当成失败码
            try:
                text = path.read_text(encoding="utf-8")
            except (OSError, UnicodeDecodeError):
                continue
            for i, line in enumerate(text.splitlines(), 1):
                for pattern in PATTERNS:
                    for code in pattern.findall(line):
                        if not CODE_SHAPE.match(code) or code in NOT_A_FAILURE_CODE:
                            continue
                        found.setdefault(code, []).append(
                            f"{path.relative_to(ROOT)}:{i}"
                        )
    return found


def main() -> int:
    from social_archive.failure_copy import (
        INCOMPLETE_RUN_CODES,
        PRODUCT_FAULT_CODES,
        code_key,
        resolve,
    )

    found = scan()
    unexplainable: list[str] = []
    for code, places in sorted(found.items()):
        key = code_key(code)
        if resolve(code) is not None:
            continue
        if key in INCOMPLETE_RUN_CODES or key in PRODUCT_FAULT_CODES:
            continue
        unexplainable.append(f"  {code}  ←  {places[0]}" + (f"（共 {len(places)} 处）" if len(places) > 1 else ""))

    print(f"扫到失败码 {len(found)} 个（{', '.join(SCAN_DIRS)}）")
    if unexplainable:
        print(f"**说不出人话的 {len(unexplainable)} 个** —— 界面会显示「我们没能记录下原因」，")
        print("而原因就写在代码里。补进 failure_copy 的 _ALIASES / INCOMPLETE_RUN_CODES /")
        print("PRODUCT_FAULT_CODES，或说明它为什么不是失败码（NOT_A_FAILURE_CODE）。")
        for line in unexplainable:
            print(line)
        return 1
    print("每一个都能落到一句中文。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
