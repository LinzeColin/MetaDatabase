#!/usr/bin/env python3
"""加一个导出目的地要改五张表，少改一张不会有任何东西报错（v0.0.0.7）。

## 为什么单开一个

`check_every_platform_table_is_complete.py`（第 22 道门）解决的是**加平台**
那件事——接 YouTube 那天数了三次表，三次都少数了。**加目的地是同一个形状，
而它一直没有对应的门。**

2026-08-06 实测：往 `DESTINATION_IDS` 里加一个 `brandnewdest`，
**1020 条判据全过、23 道门全绿**。而用户在「自动导出」那张面板上会看到
一个没有名字的 `brandnewdest`（界面是 `destinationNames[id] || id`），
没有隐私说明（那一格空着），扩展的设置页也排不进顺序里。

**一个只在名字这一层出问题的缺陷，正是最不容易被判据发现的那种**——
服务端一切正常，接口也照回，只是给人看的那几个字没了。

## 五张表

  · `src/social_archive/destinations.py` 的 `_privacy_note`  —— 东西去了哪、钥匙在谁手里
  · `apps/pwa/app.js` 的 `destinationNames`                  —— 资料库那一侧的名字
  · `apps/browser-extension/shared.js` 的 `DESTINATION_NAMES` —— 扩展共用的名字
  · `apps/browser-extension/options.js` 的 `destinationNames` —— 设置页的名字
  · `apps/browser-extension/options.js` 的 `order`            —— 设置页的排列顺序

## 它不保证什么

- 只查**在不在**，不查**写得对不对**。名字写成「Notoin」它照样绿。
- 只查这五张认得出的表。将来新加的第六张，得有人把它加进来——
  **这正是这道门自己的盲点，写在这里让它可查**。
- `social_archive` 是本机主档案，不属于导出目的地，几张表里有它是额外的，不强求。
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

TABLES = (
    ("服务端·隐私说明", "src/social_archive/destinations.py", r"def _privacy_note\(.*?\n        \}"),
    ("资料库·名字", "apps/pwa/app.js", r"const destinationNames = \{.*?\};"),
    ("扩展·共用名字", "apps/browser-extension/shared.js", r"const DESTINATION_NAMES = Object\.freeze\(\{.*?\}\);"),
    ("设置页·名字", "apps/browser-extension/options.js", r"const destinationNames = \{[^\n]*\};"),
    ("设置页·顺序", "apps/browser-extension/options.js", r"const order\s*=\s*\[[^\]]*\]"),
)


def _destination_ids() -> list[str]:
    text = (ROOT / "src/social_archive/destinations.py").read_text(encoding="utf-8")
    block = re.search(r"^DESTINATION_IDS = \((.*?)\)", text, re.S | re.M)
    if not block:
        return []
    # **`[a-z_]` 会把带数字的 id 整个漏掉。**
    # 2026-08-06 自己的反例撞出来的：造一个叫 `karakeep2` 的目的地，
    # 这道门报 PASS——它压根没把那个 id 取出来。
    # **「没看见」和「看过了，没问题」长得一模一样**，正是这一整天在拆的那种东西。
    ids = re.findall(r'"([a-z0-9_]+)"', block.group(1))
    quoted = re.findall(r'"[^"]*"', block.group(1))
    if len(ids) != len(quoted):
        # 取出来的比引号里的少 = 有 id 的形状我没认出来，**必须报出来**，不能默默少查。
        raise SystemExit(json.dumps({
            "status": "FAIL", "error_code": "ID_SHAPE_NOT_RECOGNISED",
            "parsed": ids, "quoted": quoted,
            "message_zh": "DESTINATION_IDS 里有我认不出形状的 id——**这不是通过**，"
                          "少查一个和查过一个是两回事。",
        }, ensure_ascii=False, indent=2))
    return ids


def main() -> int:
    ids = _destination_ids()
    if not ids:
        # **一个 id 都没解析出来，和「每张表都齐」长得一样。**
        print(json.dumps({"status": "FAIL", "error_code": "NO_DESTINATION_IDS_PARSED",
                          "message_zh": "没从 DESTINATION_IDS 解析出任何目的地——"
                                        "**这不是通过**，是这道门的射程失效了。"},
                         ensure_ascii=False))
        return 4

    problems: list[dict[str, object]] = []
    checked: dict[str, int] = {}
    for label, relative, pattern in TABLES:
        source = ROOT / relative
        if not source.is_file():
            problems.append({"表": label, "文件": relative, "毛病": "文件不在"})
            continue
        found = re.search(pattern, source.read_text(encoding="utf-8"), re.S)
        if not found:
            # **找不到那张表，也不能当成「齐了」。**
            problems.append({"表": label, "文件": relative,
                             "毛病": "这张表找不到了——多半是改了写法，**先修这道门**再说"})
            continue
        blob = found.group(0)
        checked[label] = len(blob)
        missing = [i for i in ids if i != "social_archive" and not re.search(rf'\b{i}\b', blob)]
        if missing:
            problems.append({"表": label, "文件": relative, "缺": missing})

    print(json.dumps({
        "status": "PASS" if not problems else "FAIL",
        "destinations": ids,
        "tables_checked": checked,
        "problems": problems,
        "message_zh": (f"{len(ids)} 个目的地，{len(TABLES)} 张表都齐。"
                       if not problems else
                       "**有目的地没进某张表**——用户会看到一个没有名字的 id，"
                       "或者一格空的隐私说明。"),
        "what_this_does_not_prove": "只查在不在，不查写得对不对；名字拼错了它照样绿。",
    }, ensure_ascii=False, indent=2))
    return 0 if not problems else 4


if __name__ == "__main__":
    sys.exit(main())
