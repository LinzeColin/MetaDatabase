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
    # **他更新之前点「连接账号」会怎样**（2026-08-10）。
    #
    # 更新这件事上面那条已经验了；这一条验的是**他还没更新的时候**——
    # 旧插件的权限申请在 service worker 里，那里任何权限都要不到，
    # 点下去授权框根本不会弹。拦截是 2026-08-10 加的，而
    # `grep -l outdated scripts/*_drill.py` 当时是空的：十六个演练没有一个走过它。
    # 旧插件不是我捏的，是 git 里 v0.0.0.22 那份真实构建。
    "stale_extension_is_blocked_drill.py",
    "extension_install_page_drill.py",
    "extension_save_page_drill.py",
    "extension_routing_drill.py",
    "extension_capture_drill.py",
    "extension_capture_buffer_drill.py",
    "extension_bridge_boundary_drill.py",
    "pwa_render_drill.py",
    # 他点插件图标看到的第一屏：三种状态各说各的话（2026-08-07）
    "popup_states_drill.py",
    "bilibili_end_to_end_drill.py",
    # **唯一打真平台接口的那一条**（2026-08-07 补上调用方）。
    #
    # 它此前归在 DRILLS.md 的「改到那条路时」——靠人判断，而这个仓已经
    # 记过这一档不可靠。后果是特定的：`SYNCABLE_NOW` 收 bilibili 的**全部
    # 依据**就是它生成的那份 evidence/G1/BILIBILI_ACQUISITION.json。
    # B 站哪天改了接口，那份文件仍旧是 PASS，产品继续对他说「B站能自动同步」，
    # 而他重连之后一条都进不来——**没有任何判据会红**，因为其余演练跑的
    # 全是我们自己写的假站。
    #
    # 代价可控：公开 REST、无签名、无 API key、不带 Cookie（L0 零费用）。
    # 打不通它会明确报出来（`live` 那段有 `_error` 就直接算 problem），
    # 不会静默成 PASS。
    "bilibili_acquisition_drill.py",
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
        # **这一句 2026-08-10 改过一次，因为它开始说得比实际少。**
        # 原话是「也不证明真平台的响应长什么样」——在把 bilibili_acquisition_drill
        # 收进来之后，这句话不再成立：那一条打的就是 B 站的真接口。
        # 往小里说自己的覆盖，和往大里说一样是错的：读的人会照着这句去补一件
        # 已经有人做了的事，或者反过来，以为某个缺口还有人盯着。
        "what_this_does_not_prove": (
            "不跑恢复类那三个（要真实备份）。**只有 bilibili_acquisition_drill 打的是"
            "真平台接口**（B 站的公开收藏夹，不带登录态）；其余每一条跑的都是仓里"
            "自己写的假站，所以它们答不了「那个平台今天改没改接口」。"
            "要登录态才看得见的响应（小红书／抖音／快手／Reddit／Instagram）"
            "一条都没验过——那只能发生在 Owner 自己的浏览器里。"
            "它回答的是：**这一版的每条链，在真 Chrome 里还走得通吗。**"),
    }
    out = ROOT / "evidence/G3/ALL_DRILLS.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\n{report['message_zh']}  没跑：{', '.join(NEEDS_REAL_INPUT)}（要真实备份）")
    return 0 if not bad else 4


if __name__ == "__main__":
    sys.exit(main())
