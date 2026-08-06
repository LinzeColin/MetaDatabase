#!/usr/bin/env python3
"""把能自己跑的演练全跑一遍，一条命令出一张表。

## 为什么

DRILLS.md 里那一档「改到那条路时」是这张表**最弱的一格**——它靠人判断
「我这次改动碰到哪条链了」，而判断错的代价是那条链的证据这一版整个没有。

零参数化做完之后（每个演练自己起 Chrome、自己打包），这件事变成了
一条命令。判断不再需要：**交付之前全跑一遍**。

## 它不做什么

不跑要参数的那几个：
  · `extension_platform_wiring_drill` 一次验一个平台，要 --platform
  · 恢复类三个要真实的备份清单
它们的参数是它们的题目本身，塞不进"全跑一遍"。这一点在下面的输出里明说，
**不让人以为这一条覆盖了全部**。
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

# 零参数就能跑的。顺序按"越基础越靠前"：包本身 → 更新 → 各条链。
ZERO_ARG = [
    "shipped_package_drill.py",
    "extension_update_in_place_drill.py",
    "extension_install_page_drill.py",
    "extension_save_page_drill.py",
    "extension_routing_drill.py",
    "extension_capture_drill.py",
    "extension_capture_buffer_drill.py",
    "extension_bridge_boundary_drill.py",
    "pwa_render_drill.py",
    "bilibili_end_to_end_drill.py",
]

# 要参数、但参数是固定的那几个（一次验一个平台）。
PARAMETRISED = [
    ["list_shape_end_to_end_drill.py", "--platform", "xiaohongshu"],
    ["list_shape_end_to_end_drill.py", "--platform", "reddit"],
    ["list_shape_end_to_end_drill.py", "--platform", "instagram"],
    ["extension_platform_wiring_drill.py", "--platform", "xiaohongshu",
     "--sample-url", "https://www.xiaohongshu.com/explore/abc123",
     "--expect-custody", "forbidden", "--expect-connect-card"],
]

# 跑不了的，**要说出来**——不说就会被当成"全跑过了"。
NEEDS_REAL_INPUT = {
    "disaster_recovery_drill.py": "要真实的备份清单与远端存储",
    "restore_private_database_drill.py": "同上",
    "restore_runtime_db_drill.py": "同上",
}


def _run(argv: list[str], timeout: int) -> dict:
    started = time.monotonic()
    try:
        done = subprocess.run([sys.executable, str(ROOT / "scripts" / argv[0]), *argv[1:]],
                              capture_output=True, text=True, timeout=timeout, cwd=ROOT)
    except subprocess.TimeoutExpired:
        return {"drill": " ".join(argv), "status": "TIMEOUT",
                "seconds": round(time.monotonic() - started, 1),
                "problems": [f"超过 {timeout} 秒还没跑完"]}
    seconds = round(time.monotonic() - started, 1)
    text = (done.stdout or "").strip()
    payload: dict = {}
    if text:
        for candidate in (text, text.splitlines()[-1]):
            try:
                payload = json.loads(candidate)
                break
            except ValueError:
                continue
    if not payload:
        return {"drill": " ".join(argv), "status": "NO_JSON", "seconds": seconds,
                "problems": [f"没有回 JSON（exit {done.returncode}）："
                             + (text.splitlines()[-1][:160] if text else
                                (done.stderr or "").strip().splitlines()[-1][:160]
                                if (done.stderr or "").strip() else "空输出")]}
    return {"drill": " ".join(argv), "status": payload.get("status", "?"),
            "seconds": seconds, "problems": payload.get("problems") or []}


def main() -> int:
    parser = argparse.ArgumentParser(description="把能自己跑的演练全跑一遍")
    parser.add_argument("--timeout", type=int, default=420, help="单个演练的上限秒数")
    parser.add_argument("--only", default="", help="只跑名字里含这个词的")
    args = parser.parse_args()

    plan = [[name] for name in ZERO_ARG] + PARAMETRISED
    if args.only:
        plan = [argv for argv in plan if args.only in " ".join(argv)]
    results = []
    for argv in plan:
        result = _run(argv, args.timeout)
        results.append(result)
        mark = "✓" if result["status"] == "PASS" else "✗"
        print(f"  {mark} {result['drill']:<62} {result['status']:<8} {result['seconds']}s",
              flush=True)
        for problem in result["problems"][:2]:
            print(f"      {str(problem)[:150]}", flush=True)

    bad = [item for item in results if item["status"] != "PASS"]
    report = {
        "status": "PASS" if not bad else "FAIL",
        "ran": len(results),
        "failed": len(bad),
        "results": results,
        # **说清没跑的那几个**，否则这一条会被当成"全部覆盖"。
        "not_run": NEEDS_REAL_INPUT,
        "message_zh": (f"{len(results)} 个演练全绿。" if not bad
                       else f"{len(bad)}/{len(results)} 个演练没过。"),
        "what_this_does_not_prove": (
            "不跑恢复类那三个（要真实备份），也不证明真平台的响应长什么样"
            "（那要 Owner 的登录态）。它回答的是：**这一版的每条链，"
            "在真 Chrome 里还走得通吗。**"),
    }
    out = ROOT / "evidence/G3/ALL_DRILLS.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\n{report['message_zh']}  没跑：{', '.join(NEEDS_REAL_INPUT)}（要真实备份）")
    return 0 if not bad else 4


if __name__ == "__main__":
    sys.exit(main())
