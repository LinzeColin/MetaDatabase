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
  · 恢复类三个要远端凭据，**本机没有，所以这里不跑**。
  ★ 这一段两次说错过，两次都是**说得比实际严重**再被实测纠正：
    先是写着「真跑在部署第 8.95 步」——查无此步（脚本名出现 0 次）；
    改成「部署里也没有调用方，得有人记得去跑」——2026-08-11 当天就不成立了：
    三个恢复演练现在都挂在**部署第 8.69 步**，在生产机上真跑（三个共 50 秒）。
    本机不跑它们的理由只剩一条：**这台机器没有远端凭据。**
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
    # 答得慢的插件还认不认得出——上面那个演练三次掐断部署的真因就在这儿。
    "slow_extension_is_still_detected_drill.py",
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
    # **抖音**（2026-08-11 补）：他生产库里最大的那个账号（86 条），
    # 8/4 那次同步的错误码正是 BROWSER_SCAN_FAILED——就是这条路上的失败。
    # 而在此之前**这条路对抖音一次都没有被走过**：
    # background.js 的 SHAPE_READ_PLATFORMS 里有它，演练的 PLATFORMS 里没有。
    ["list_shape_end_to_end_drill.py", "--platform", "douyin"],
    ["list_shape_end_to_end_drill.py", "--platform", "reddit"],
    ["list_shape_end_to_end_drill.py", "--platform", "instagram"],
    # **整条链对着他真正下载的那个包走一遍**（2026-08-13 补上调用方）。
    #
    # 这件事此前写在 bilibili_end_to_end_drill.py 的文件头里，措辞是
    # 「每次部署之后**至少跑一次真包**」，并记着最后一次是 **v0.0.0.16**——
    # 而今天是 v0.0.0.70。**中间五十几版一次都没跑过。**
    # 靠人记得那一档，这个仓已经拔过很多次了。
    #
    # 交付包另有两道自动的门（shipped_package_drill 用未改权限的原包加载；
    # 部署第 8 / 8.2 步逐字节证明「下载页发的 = 本地的 = git 里的」），
    # 这一条补的是**整条链**：连接 → 取数 → 入库。
    ["bilibili_end_to_end_drill.py", "--from-shipped-zip"],
    # **选择器落在真页面上选不选得中**（2026-08-13）。
    #
    # 其余所有按形状读的演练打的都是**我们自己写的假站**——我编的响应形状，
    # 选择器当然选得中。这一条打真页面（公开、不登录、零费用）。
    # 两家各走各的路（演练里的 DEFAULT_MODE 是量出来的）：
    # B 站列表由 JS 渲染，只能真浏览器打开（21 命中）；小红书拒无头，
    # 而它服务端就把列表渲染好了，取 HTML 再解析（96 命中）。
    # **抖音仍答不了**——没有一张公开的、真的是列表的抖音页，
    # 它回 BLOCKED_CHANNEL 而不是 FAIL：「答不了」不等于「答案是坏的」。
    # **识别器在真页面上会不会乱抓**——只跑真见得到内容流的那两家（2026-08-13 实测）：
    # 量的是「面前摆了几个长得像列表的负载」——只有 douyin 真有（实测 12 个）。
    # instagram / xiaohongshu / reddit 在这台机器上都是 0 个候选，
    # 接进来只会每次多几条「没量到」。**这三个数我连错两版才量准**：
    # 先按路径挑埋点（抖音报 52/52），再补主机名（instagram 又报 17/17），
    # 最后改成结构判定才稳——按主机拉黑名单是打地鼠。
    ["douyin_recogniser_does_not_grab_the_wrong_list_drill.py", "--platform", "douyin"],
    ["list_selectors_meet_a_real_page_drill.py", "--platform", "bilibili"],
    ["list_selectors_meet_a_real_page_drill.py", "--platform", "xiaohongshu"],
    ["extension_platform_wiring_drill.py", "--platform", "xiaohongshu",
     "--sample-url", "https://www.xiaohongshu.com/explore/abc123",
     "--expect-custody", "forbidden", "--expect-connect-card"],
]

# 跑不了的，**要说出来**——不说就会被当成"全跑过了"。
#
# **这几条理由 2026-08-10 之前是错的。** 原来写的是「要真实的备份清单与远端存储」，
# 而清单一直都在（`/var/lib/social-archive/backups/runtime-db/…/manifest.json`，
# 每 15 分钟一份）。真正跑不起来的原因是代码：`backup._s3_config` 少了凭据回退，
# `.env` 里的 `/run/secrets/…` 在 systemd unit 之外不存在，于是它报「r2 未配置」。
#
# 那个错理由的代价很实在：**"他的东西真能拿回来"这件事从来没被证明过，
# 而所有人（包括我）都以为那是环境不具备，不是缺陷。**
#
# 修好之后当天在他生产机上真跑通了（r2 与 oci 各一次，还原出的库
# content 193 / user_relation 194 / artifact 552，与线上逐项相同）。
#
# **2026-08-11：这三个全都有闹钟了。** 都挂在部署第 8.69 步，
# 经 `check_the_backup_can_actually_be_restored.py` 在生产机上跑（三个加起来实测
# 50 秒，凭据由 systemd 发）。这里**仍然**标成 not_run，因为本机确实没有远端凭据——
# 但那句「没有任何脚本会自动跑它」已经不成立了，别照着它下结论。
#
# 顺带修掉了这张表造成的一个假绿：`check_every_drill_has_a_caller.py`
# 原来做子串命中，于是**「我不跑它」这句话满足了「有人调它」**。现在那道门用 ast
# 把这张表里的名字剔掉再判——也就是说**在这里登记一个名字，不再能替它免掉调用方**。
NEEDS_REAL_INPUT = {
    "disaster_recovery_drill.py":
        "本机没有远端凭据；**它已经有自动调用方了**——部署第 8.69 步抽 25 个制品真跑（不是全量）",
    "restore_private_database_drill.py":
        "本机没有远端凭据；**它已经有自动调用方了**——部署第 8.69 步真跑（实测 2 秒）",
    "restore_runtime_db_drill.py":
        "本机没有远端凭据；**它已经有自动调用方了**——部署第 8.69 步在生产机上真跑一遍",
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
        # ✗ 是「没过」，— 是「没量到」。用同一个记号会把两件事混成一件：
        # 一个要去修产品，一个要去换通道。
        mark = ("✓" if result["status"] == "PASS"
                else "—" if result["status"] == "BLOCKED_CHANNEL" else "✗")
        print(f"  {mark} {result['drill']:<62} {result['status']:<8} {result['seconds']}s",
              flush=True)
        for problem in result["problems"][:2]:
            print(f"      {str(problem)[:150]}", flush=True)

    # **「答不了」既不算过，也不算没过——但绝不许读成"覆盖到了"。**（2026-08-13）
    #
    # 有几条演练打的是真平台页面，而平台会挡无头浏览器（小红书给风控页、
    # reddit 给人机验证）。那种时候产品没有任何问题，掐断部署是错的；
    # 可要是悄悄当成绿的，我们就会以为那一维验过了——而它没有。
    #
    # 所以单独一档：不进 `bad`（不掐部署），但**单独列出来、单独计数**，
    # 让「这次少验了哪一维」在日志里一眼看得见。
    blocked = [item for item in results if item["status"] == "BLOCKED_CHANNEL"]
    bad = [item for item in results if item["status"] not in ("PASS", "BLOCKED_CHANNEL")]
    report = {
        "status": "PASS" if not bad else "FAIL",
        "ran": len(results),
        "failed": len(bad),
        # **不是"全跑过了"**：这几条这次没量到，各自的原因在它们自己的输出里。
        "blocked_channel": [item["drill"] for item in blocked],
        "results": results,
        # **说清没跑的那几个**，否则这一条会被当成"全部覆盖"。
        "not_run": NEEDS_REAL_INPUT,
        "message_zh": (
            (f"{len(results) - len(blocked)}/{len(results)} 个演练全绿"
             + (f"；**另有 {len(blocked)} 条这次没量到**（平台挡了无头浏览器，"
                f"不是产品的问题，也不算验过）：{'、'.join(i['drill'] for i in blocked)}"
                if blocked else "。"))
            if not bad else f"{len(bad)}/{len(results)} 个演练没过。"),
        # **这一句 2026-08-10 改过一次，因为它开始说得比实际少。**
        # 原话是「也不证明真平台的响应长什么样」——在把 bilibili_acquisition_drill
        # 收进来之后，这句话不再成立：那一条打的就是 B 站的真接口。
        # 往小里说自己的覆盖，和往大里说一样是错的：读的人会照着这句去补一件
        # 已经有人做了的事，或者反过来，以为某个缺口还有人盯着。
        "what_this_does_not_prove": (
            "不跑恢复类那三个——**本机没有远端凭据**（不是没有备份：清单每 15 分钟一份）；"
            "它们由**部署第 8.69 步**在生产机上真跑，不在这一条的覆盖里。"
            "这里面**只有一条打真平台接口**（B 站的公开收藏夹，不带登录态）；其余每一条跑的都是仓里"
            "自己写的假站，所以它们答不了「那个平台今天改没改接口」。"
            "要登录态才看得见的响应（小红书／抖音／快手／Reddit／Instagram）"
            "一条都没验过——那只能发生在 Owner 自己的浏览器里。"
            "它回答的是：**这一版的每条链，在真 Chrome 里还走得通吗。**"),
    }
    out = ROOT / "evidence/G3/ALL_DRILLS.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\n{report['message_zh']}  没跑：{', '.join(NEEDS_REAL_INPUT)}"
          "（本机没有远端凭据；**它们由部署第 8.69 步在生产机上真跑**，不靠人记得）")
    return 0 if not bad else 4


if __name__ == "__main__":
    sys.exit(main())
