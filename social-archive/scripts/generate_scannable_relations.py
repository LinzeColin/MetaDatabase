#!/usr/bin/env python3
r"""把扩展那份 `SCANNABLE_RELATIONS` 生成成一个 Python 模块。

## 为什么要生成，而不是运行时去读那个 .js

服务端必须知道「扩展真正会去枚举哪些关系」——不知道就会把**允许**出现的
关系全列进同步范围，而扩展只送收藏那一档的终批，整次 run 永远不收敛
（Owner 的生产数据：20 次同步 0 次 completed）。

第一版的写法是 import 时读

    Path(__file__).resolve().parents[2] / "apps/browser-extension/content/platform-catalog.js"

在仓里跑得好好的——`parents[2]` 正好是仓根。**而装进镜像之后它是
`/usr/local/lib/python3.12/`**，文件不存在，我又特意写了「读不到就抛」，
于是：

    FileNotFoundError: '/usr/local/lib/python3.12/apps/browser-extension/content/platform-catalog.js'

**API 起不来。** 1402 条判据全绿，因为判据全跑在仓里。
抓到它的是「把镜像真起一次」，不是读代码。

## 所以改成生成

`.js` 仍是唯一真源；这里把它编译成 `src/social_archive/scannable_relations.py`
（一个纯字面量模块，跟着包一起装，**没有任何相对路径**）。
两边漂开由 `tests/focused/test_sync_scope_never_exceeds_what_can_be_scanned.py`
当场打红，并在错误里给出这条重新生成的命令。

    python3 scripts/generate_scannable_relations.py --apply
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CATALOG = ROOT / "apps/browser-extension/content/platform-catalog.js"
TARGET = ROOT / "src/social_archive/scannable_relations.py"

HEADER = '''"""扩展真正会去枚举的关系类型——**这个文件是生成的，不要手改。**

真源是 `apps/browser-extension/content/platform-catalog.js` 的
`SCANNABLE_RELATIONS`。改了那边之后跑：

    python3 scripts/generate_scannable_relations.py --apply

为什么不在运行时读那个 .js：装进镜像之后 `social_archive` 在
site-packages 里，仓的相对路径不存在，import 当场炸、API 起不来
（2026-08-10 实测，那次 1402 条判据全绿）。
"""

from __future__ import annotations

'''


def parse(text: str) -> dict[str, tuple[str, ...]]:
    block = re.search(r"const SCANNABLE_RELATIONS = Object\.freeze\(\{(.*?)\n  \}\);",
                      text, re.S)
    if not block:
        raise SystemExit("platform-catalog.js 里找不到 SCANNABLE_RELATIONS 块")
    found: dict[str, tuple[str, ...]] = {}
    for platform, items in re.findall(
            r"(\w+):\s*Object\.freeze\(\[(.*?)\]\)", block.group(1), re.S):
        found[platform] = tuple(re.findall(r'"([a-z_]+)"', items))
    if not found:
        raise SystemExit("SCANNABLE_RELATIONS 解析出 0 个平台——这不是「没有」，是解析坏了")
    return found


def render(found: dict[str, tuple[str, ...]]) -> str:
    lines = [HEADER, "SCANNABLE_RELATIONS: dict[str, tuple[str, ...]] = {"]
    for platform in sorted(found):
        items = ", ".join(f'"{name}"' for name in found[platform])
        lines.append(f'    "{platform}": ({items}{"," if len(found[platform]) == 1 else ""}),')
    lines.append("}")
    lines.append("")
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apply", action="store_true", help="真写；不给就只比对")
    args = parser.parse_args()
    wanted = render(parse(CATALOG.read_text(encoding="utf-8")))
    current = TARGET.read_text(encoding="utf-8") if TARGET.exists() else ""
    if wanted == current:
        print(f"  已经是最新的：{TARGET.relative_to(ROOT)}")
        return 0
    if not args.apply:
        print(f"  和 platform-catalog.js 漂开了：{TARGET.relative_to(ROOT)}", file=sys.stderr)
        print("  跑 `python3 scripts/generate_scannable_relations.py --apply` 生成", file=sys.stderr)
        return 1
    TARGET.write_text(wanted, encoding="utf-8")
    print(f"  已生成 {TARGET.relative_to(ROOT)}（{len(parse(CATALOG.read_text(encoding='utf-8')))} 个平台）")
    return 0


if __name__ == "__main__":
    sys.exit(main())
