#!/usr/bin/env python3
"""扩展读了一个配置项，却没有任何地方能把它设起来（v0.0.0.7）。

## 为什么又要单开一个

已经有三道门在查「建好了没接上」，而它们各自都看不见这一种：

  · `find_settings_with_no_way_to_set_them.py` —— 只管 `src/` 里的
    `SOCIAL_ARCHIVE_*` 环境变量，**够不着扩展的 chrome.storage 配置**。
  · `find_write_only_storage_keys.py` —— 只管 `"saXxx"` 形状的键，
    而且只查 **写了没人读**；这里是反过来的：**读了没人写**。
  · `find_endpoints_no_client_calls.py` —— 只看路径字符串在不在客户端里，
    看不出那段代码走不走得到。

2026-08-05 实测到的实例：`obsidianLocalEnabled` / `obsidianLocalUrl` /
`obsidianLocalToken` 三个键在 `shared.js` 的 DEFAULT_CONFIG 里有默认值、
在 `background.js` 里被读了六处，**全仓没有任何一处写它们**。

于是 `exportLocalObsidian()` 第一行就 `return { status: "not_selected" }`，
「把抓到的东西直接写进本机 Obsidian 仓库」这个功能**一次都执行不了**。
连带着 `/v1/destinations/obsidian-local/receipts` 那个端点也永远收不到回执。

**默认值让它看起来是配好的。** 读得到、有默认值、代码路径俱全——
只有「谁来把它打开」这一环缺着，而那一环不写判据就没人会去数。

## 判据

从 `shared.js` 的 `DEFAULT_CONFIG` 取键名，在 `apps/` 下找有没有人写它：
`SA.setConfig({...})`、`chrome.storage.local.set({...})`、或表单里
`name="<键>"` 这种能落到 setConfig 的写法。只读不写的报出来。

## 豁免

有些键**本来就不该有界面**（由配对流程下发、或由代码自己维护），
写进 `SET_BY_MACHINE_NOT_BY_PEOPLE` 并说清谁写它。

## 它不保证什么

- **「有人写」不等于「用户点得到」。** 写它的可能也是一段走不到的代码——
  这道门只往前推一格，推不到底。
- 只扫 `apps/`。别的地方（比如手工改 storage）不算。
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
EXT = ROOT / "apps/browser-extension"
SHARED = EXT / "shared.js"

# 不该有界面的键：由机器写，不由人设。**每一条都要说清谁写它。**
SET_BY_MACHINE_NOT_BY_PEOPLE: dict[str, str] = {
    # 零门槛那条路：档案馆页面用自己的会话换令牌，通过桥交给扩展。
    # 用户一个字符都不用输——所以这两个本来就不该有输入框。
    "endpoint": "由托管配置或桥下发（SA_ADOPT_TOKEN），用户不输入任何字符",
    "token": "同上；零门槛的整个意义就是它不该由人来填",
    "libraryUrl": "随 token 一起由同源的档案馆页面下发（异源会被拒，见 background.js）",
}

# **和上面那张表不是一回事。** 上面是「本来就不该有界面」；这里是
# 「**功能还没接上**，所以还没有界面」——它是个待办，不是个决定。
#
# 所以这张表里的键**不会被静默跳过**：它们照样打印在报告里（`declared_gaps`），
# 只是不让门变红。一个被登记之后就再也看不见的缺口，等于没登记。
#
# 每一条都要写清**什么条件成立时把它从这里删掉**。
KNOWN_NOT_WIRED_YET: dict[str, str] = {
    "obsidianLocalEnabled": (
        "「把抓到的东西直接写进本机 Obsidian 仓库」整条还没接上："
        "background.js 里 exportLocalObsidian() 有完整实现，"
        "**但它从不向 /v1/destinations/obsidian-local/receipts 回执**，"
        "服务端因此永远不知道写没写成。先补回执再谈开关——"
        "现在就给个开关，等于让人打开一个服务端看不见的目的地。"
        "见 evidence/T11/THE_LOCAL_OBSIDIAN_PATH_IS_BUILT_BUT_UNREACHABLE.json"),
    "obsidianLocalUrl": "同上，随 obsidianLocalEnabled 一起接",
    "obsidianLocalToken": "同上；而且它是密钥，界面怎么收要单独想（不能明文躺在 storage 里给任何页面看）",
}


def _default_config_keys(text: str) -> list[str]:
    block = re.search(r"const DEFAULT_CONFIG = Object\.freeze\(\{(.*?)\}\);", text, re.S)
    if not block:
        return []
    return re.findall(r"^\s*(\w+)\s*:", block.group(1), re.M)


def main() -> int:
    if not SHARED.is_file():
        print(json.dumps({"status": "FAIL", "error_code": "SHARED_JS_MISSING"}, ensure_ascii=False))
        return 2
    keys = _default_config_keys(SHARED.read_text(encoding="utf-8"))
    if not keys:
        # **一个键都没解析出来，和「全都有人设」长得一样。**
        print(json.dumps({"status": "FAIL", "error_code": "NO_KEYS_PARSED",
                          "message_zh": "没从 DEFAULT_CONFIG 解析出任何键——"
                                        "**这不是通过**，多半是那个结构改了、判据的射程失效了。"},
                         ensure_ascii=False))
        return 4

    sources = {p: p.read_text(encoding="utf-8", errors="ignore")
               for p in sorted(EXT.rglob("*")) if p.is_file() and p.suffix in (".js", ".html")}

    unsettable: list[dict[str, object]] = []
    declared: list[dict[str, object]] = []
    for key in keys:
        if key in SET_BY_MACHINE_NOT_BY_PEOPLE:
            continue
        writers: list[str] = []
        for path, text in sources.items():
            if path == SHARED:
                continue          # 默认值不算「设过」
            for line_no, line in enumerate(text.splitlines(), 1):
                if line.lstrip().startswith("//"):
                    continue
                # 写法一：setConfig / storage.local.set 的对象字面量里出现 `key:`
                # 写法二：表单元素 name="key"
                if re.search(rf"\b{re.escape(key)}\s*:", line) or f'name="{key}"' in line:
                    writers.append(f"{path.relative_to(EXT)}:{line_no}")
                    break
        if not writers:
            readers = [f"{p.relative_to(EXT)}" for p, t in sources.items()
                       if p != SHARED and re.search(rf"\b{re.escape(key)}\b", t)]
            entry = {"key": key, "read_in": readers}
            if key in KNOWN_NOT_WIRED_YET:
                entry["declared_reason"] = KNOWN_NOT_WIRED_YET[key]
                declared.append(entry)
            else:
                unsettable.append(entry)

    print(json.dumps({
        "status": "PASS" if not unsettable else "FAIL",
        "keys_checked": len(keys),
        "exempt": list(SET_BY_MACHINE_NOT_BY_PEOPLE),
        "no_way_to_set": unsettable,
        # **登记过的缺口照样印出来。** 登记之后就再也看不见的，等于没登记。
        "declared_gaps": declared,
        "message_zh": ((f"扩展 DEFAULT_CONFIG 里没有未登记的死配置项"
                        f"（另有 {len(declared)} 项**已登记为还没接上**，见 declared_gaps）。")
                       if not unsettable else
                       "**这些键读得到、有默认值，却没有任何地方能把它设起来**——"
                       "靠它开关的那段代码一次都执行不了。"),
        "what_this_does_not_prove": "「有人写」不等于「用户点得到」——写它的也可能是走不到的代码。",
    }, ensure_ascii=False, indent=2))
    return 0 if not unsettable else 4


if __name__ == "__main__":
    sys.exit(main())
