#!/usr/bin/env python3
"""扩展往 chrome.storage 里写了、却没有任何地方读的键（v0.0.0.7）。

## 为什么单开一个

`find_unwired_code.py` 只看 Python 的符号引用，`find_endpoints_no_client_calls.py`
只看 HTTP 接口。两者都看不见第三种「建好了没接上」：

    往 chrome.storage.local 写了一份状态 → **没有任何界面读它**

本轮实际踩到的：`saAccountSyncQueueLastResult` 在 background.js 里写了三处
（正常结束、异常结束、放弃时各一次），**一个 get 都没有**。
我当时为「同步被反复打断后放弃」补了一条本地记录，自以为补上了
INV-NO-SILENT-ZERO 的缺口——而那条记录写进了没人看的地方。
真正让用户看见是后来改成向服务端报「关系终批 + failed」才实现的。

**写进没人读的地方，和没写是一回事，但它看起来像写了。**

## 判据

扫 `apps/` 下的 `.js`：找 `"saXxx"` 形状的 storage 键，
比对 `storage.local.set/remove` 与 `storage.local.get` 的出现。
只写不读就报出来。

## 豁免

有些键**本来就只写**（写给别的进程或下一次启动读），
写进 WRITE_ONLY_BY_DESIGN 并说清谁在读。
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
EXT = ROOT / "apps/browser-extension"

KEY = re.compile(r'"(sa[A-Z][A-Za-z0-9]+)"')

# 只写不读但**有正当理由**的键。每条写清谁读它。
WRITE_ONLY_BY_DESIGN: dict[str, str] = {}


def main() -> int:
    if not EXT.is_dir():
        print("找不到扩展目录，跳过（这是跳过，不是通过）")
        return 0

    sources = {p.name: p.read_text(encoding="utf-8") for p in EXT.rglob("*.js")}
    blob = "\n".join(sources.values())
    # 注释里提到一个键不算读它——本轮已经被自己的说明文字骗过三次
    code_only = "\n".join(
        line for line in blob.splitlines()
        if not line.lstrip().startswith("//") and not line.lstrip().startswith("*")
    )

    keys = sorted(set(KEY.findall(code_only)))
    write_only: list[str] = []
    for key in keys:
        if key in WRITE_ONLY_BY_DESIGN:
            continue
        # 常量名也算：const X = "saFoo" 之后代码里用 X
        const = re.search(rf'const\s+(\w+)\s*=\s*"{re.escape(key)}"', code_only)
        names = [re.escape(key)] + ([re.escape(const.group(1))] if const else [])
        alternation = "|".join(names)
        reads = re.findall(rf'storage\.local\.get\([^;]{{0,200}}?(?:{alternation})', code_only, re.S)
        writes = re.findall(rf'storage\.local\.(?:set|remove)\([^;]{{0,200}}?(?:{alternation})', code_only, re.S)
        if writes and not reads:
            write_only.append(f"  {key}  （写 {len(writes)} 处，读 0 处）")

    print(f"扫了扩展里 {len(keys)} 个 storage 键")
    if write_only:
        print(f"**只写不读的 {len(write_only)} 个** —— 写进没人读的地方，和没写是一回事：")
        for line in write_only:
            print(line)
        print("\n接上读它的地方，或写进 WRITE_ONLY_BY_DESIGN 并说清谁在读。")
        return 1
    print("每个写进去的键都有人读。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
