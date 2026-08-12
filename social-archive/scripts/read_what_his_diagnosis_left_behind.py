#!/usr/bin/env python3
r"""他按过那颗诊断按钮没有？按了的话，留下的地址和字段骨架是什么（2026-08-12）。

## 为什么需要这个

说明书现在请他做一件事：在抖音收藏页按一次诊断按钮。按下去之后，

    地址   → `diagnostics/extension-diagnostics.jsonl`
    骨架   → `diagnostics/unreadable-payload-shapes.jsonl`

两样都落在**他自己的服务器上**。而在这个脚本之前，**没有任何东西会告诉我
他按过了**——我得记得自己去翻。

「机制建好了、没人去看」是这个仓一路在拔的形状，只不过这一次断在我这一头：
他做完了他那一份，而我不知道。

## 它怎么报

**是播报，不是门。** 他还没按是完全正常的状态，不该让部署红。
按了的话，把要紧的两样直接印出来：**该盯哪个地址**，和**响应长什么样**。

## 边界

- 只读、只印结构：骨架里本来就只有字段名/类型/长度（见 `payload_shape` 的硬边界）。
- 台账里那两条 B 站记录是部署验收用的合成数据，**明确排除**，
  免得它们看起来像"他按过了"。
- 我自己验证记录器时打的那一条（url 里带 `__verify_shape_recorder__`）同理排除。
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

DIAGNOSTICS = Path("/var/lib/social-archive/diagnostics")
SYNTHETIC_MARKS = ("部署验收用", "合成记录", "__verify_shape_recorder__")


def _load(path: Path) -> list[dict]:
    if not path.is_file():
        return []
    rows = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            rows.append(json.loads(line))
        except ValueError:
            continue
    return rows


def _is_real(row: dict) -> bool:
    blob = json.dumps(row, ensure_ascii=False)
    return not any(mark in blob for mark in SYNTHETIC_MARKS)


def main() -> int:
    parser = argparse.ArgumentParser(description="他那一按留下了什么")
    parser.add_argument("--root", default=str(DIAGNOSTICS))
    parser.add_argument("--brief", action="store_true")
    parser.add_argument("--host", default="",
                        help="给了就把自己送进那台机器的容器里跑（台账只在容器里）")
    args = parser.parse_args()

    if args.host:
        # 容器 rootfs 只读，`docker cp` 进不去；把自己 base64 送进去跑，
        # 这样判读逻辑只有一份实现，不用在部署脚本里再抄一遍。
        import base64
        import shlex
        import subprocess
        blob = base64.b64encode(
            Path(__file__).read_text(encoding="utf-8").encode()).decode()
        # **argv 单独拼**：塞进 f-string 里要靠 PEP 701 的同引号嵌套，
        # 语法上在 3.12+ 成立，读起来却像坏的，改一次就容易改错。
        argv = "['r', '--brief']" if args.brief else "['r']"
        inner = (f"import base64,sys;sys.argv={argv};"
                 f"exec(base64.b64decode('{blob}'))")
        done = subprocess.run(
            ["ssh", "-o", "ConnectTimeout=25", args.host,
             f"sudo docker exec social-archive-core-api-1 python3 -c {shlex.quote(inner)}"],
            capture_output=True, text=True, timeout=180)
        sys.stdout.write(done.stdout)
        sys.stderr.write(done.stderr)
        return done.returncode

    root = Path(args.root)

    reports = [r for r in _load(root / "extension-diagnostics.jsonl") if _is_real(r)]
    shapes = [r for r in _load(root / "unreadable-payload-shapes.jsonl") if _is_real(r)]

    platforms = sorted({str(r.get("platform") or "?") for r in reports})
    # 该盯哪个地址：他那一按抓到的全部地址，按平台归拢。
    addresses: dict[str, list[str]] = {}
    for row in reports:
        addresses.setdefault(str(row.get("platform") or "?"), [])
        for url in (row.get("urls") or [])[:40]:
            if url not in addresses[str(row.get("platform") or "?")]:
                addresses[str(row.get("platform") or "?")].append(url)

    payload = {
        "status": "PASS",
        "he_has_pressed_it": bool(reports),
        "platforms_he_diagnosed": platforms,
        "real_diagnostic_reports": len(reports),
        "payload_shapes_recorded": len(shapes),
        "addresses_by_platform": {k: v[:12] for k, v in addresses.items()},
        "shapes": [{"platform": r.get("platform"), "url": r.get("url"),
                    "failure_code": r.get("failure_code"), "sketch": r.get("sketch")}
                   for r in shapes[-3:]],
        "message_zh": ("他还没按过那颗诊断按钮（台账里只有部署验收用的合成记录）。"
                       if not reports else
                       f"**他按过了**：{'、'.join(platforms)}；"
                       f"留下 {len(shapes)} 份响应骨架。下一步是照骨架写解析器、"
                       f"并把地址填进 INTERCEPT_PREFIXES。"),
        "what_this_does_not_prove": "只说台账里有什么，不代表那个地址一定就是收藏列表。",
    }
    if args.brief:
        print(f"  {payload['message_zh']}")
        for platform, urls in payload["addresses_by_platform"].items():
            for url in urls[:4]:
                print(f"    {platform}: {url[:96]}")
    else:
        print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
