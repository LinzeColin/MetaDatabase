#!/usr/bin/env python3
r"""部署之前先证明：我要部署的这台，就是他打得到的那台。

## 它从哪来

2026-08-10，我一天里部署了三次（0.0.0.26 两次、0.0.0.27），每次都「回读生产」
并报告全绿。**三次都没到他手上。**

    从 Owner 的 Mac 打 https://social-archive-api.linzezhang.com/health
        → version 0.0.0.25，disk.free 70.36G / total 95.82G
    ssh 到部署目标（linze-ovh）上打同一个域名
        → version 0.0.0.27，disk.free  1.13G / total 38G

同一个域名背后是**两台机器**。他的浏览器在他的 Mac 上，所以他一直在跟旧的那台
说话，而我在给另一台升级。

## 为什么全套判据都没抓到

**每一条「生产回读」都是 ssh 到部署目标上打它自己的回环。**
第 7 步（鉴权路由）、第 8 步（下载页发的包）、第 8.5 步（真 Chrome 够不够得着）
——全都站在被测机器上。对「域名指到别处」这件事，它们结构上就是瞎的。

唯一从外面看的那条（`check_the_shipped_package_is_the_committed_code.py`）
当场红了，而我把它当成 Cloudflare 缓存放过去了。

## 它怎么判

拿一个**和代码无关**的数当机器指纹：`disk.total_bytes`（或 free）。
版本号可以一样地旧，两台机器的盘不会恰好一样大。

  · 从**跑这个脚本的机器**打公开域名（= 他所在的位置）
  · ssh 到部署目标上打它的回环
  · 两边的 `disk.total_gb` 必须相等 —— 不等就是两台机器，当场拦下

**不做「版本相等」的判断**：部署前两边版本本来就不同，那是正常的。
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import urllib.request

BROWSER_UA = {"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7)"}


def _public_health(base: str) -> dict:
    with urllib.request.urlopen(
            urllib.request.Request(base.rstrip("/") + "/health", headers=BROWSER_UA),
            timeout=30) as response:
        return json.loads(response.read())


def _target_health(host: str, port: int) -> dict:
    done = subprocess.run(
        ["ssh", "-o", "ConnectTimeout=20", host,
         f"curl -sS --max-time 20 http://127.0.0.1:{port}/health"],
        capture_output=True, text=True, check=False)
    if done.returncode != 0 or not done.stdout.strip():
        raise RuntimeError(f"读不到部署目标的 /health：{done.stderr.strip()[:200]}")
    return json.loads(done.stdout)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--public", default="https://social-archive-api.linzezhang.com")
    parser.add_argument("--host", default="linze-ovh")
    parser.add_argument("--port", type=int, default=18765)
    parser.add_argument("--expect-version", default="",
                        help="部署之后用：公开域名必须已经在跑这个版本（从这台机器看）")
    args = parser.parse_args()

    report: dict[str, object] = {
        "what_this_answers_zh": "我要部署的这台，是不是他打开产品时真正连到的那台。",
        "public": args.public,
        "deploy_target": f"{args.host}:{args.port}",
    }
    try:
        outside = _public_health(args.public)
    except Exception as error:                                    # noqa: BLE001
        report |= {"status": "FAIL", "error_code": "PUBLIC_UNREACHABLE",
                   "message_zh": f"从这台机器打不到公开域名：{error}——"
                                 "**判不了就是不能放行**，别默认「那就是同一台」"}
        print(json.dumps(report, ensure_ascii=False, indent=2))
        return 2
    try:
        inside = _target_health(args.host, args.port)
    except Exception as error:                                    # noqa: BLE001
        report |= {"status": "FAIL", "error_code": "TARGET_UNREACHABLE",
                   "message_zh": f"{error}"}
        print(json.dumps(report, ensure_ascii=False, indent=2))
        return 2

    def _disk(health: dict) -> tuple[float | None, str | None]:
        disk = health.get("disk") or {}
        return disk.get("total_gb"), health.get("version")

    out_total, out_version = _disk(outside)
    in_total, in_version = _disk(inside)
    report |= {
        "measured": {
            "public": {"version": out_version, "disk_total_gb": out_total},
            "deploy_target": {"version": in_version, "disk_total_gb": in_total},
        },
    }
    if out_total is None or in_total is None:
        report |= {"status": "FAIL", "error_code": "NO_FINGERPRINT",
                   "message_zh": "/health 里没有 disk.total_gb，指纹取不到——"
                                 "**取不到指纹不等于同一台**，先把这个字段补上"}
        print(json.dumps(report, ensure_ascii=False, indent=2))
        return 2
    if abs(out_total - in_total) > 0.01:
        report |= {
            "status": "FAIL",
            "error_code": "TWO_DIFFERENT_MACHINES",
            "message_zh": (
                f"**他打到的那台和我要部署的这台不是同一台**："
                f"公开域名 disk_total={out_total}G（version {out_version}），"
                f"部署目标 disk_total={in_total}G（version {in_version}）。"
                "部署上去他也看不到——先把域名指对，或者换成部署到他真正连到的那台。"),
        }
        print(json.dumps(report, ensure_ascii=False, indent=2))
        return 1
    if args.expect_version:
        # **上线之后，从他所在的位置回读一次。**（2026-08-10）
        #
        # 在这之前，「回读生产」全是 ssh 到目标机器上打回环——
        # 那证明不了他打开产品时看到的是新版。今天的代价：三次部署零次到达。
        if out_version != args.expect_version:
            report |= {
                "status": "FAIL",
                "error_code": "PUBLIC_STILL_ON_OLD_VERSION",
                "message_zh": (
                    f"部署报告成功，但**从这台机器打公开域名拿到的还是 {out_version}**"
                    f"（期望 {args.expect_version}）。他打开产品看到的就是这个数——"
                    "在他那边这次部署等于没发生。"),
            }
            print(json.dumps(report, ensure_ascii=False, indent=2))
            return 1
        report |= {"status": "PASS",
                   "message_zh": f"公开域名已经在跑 {out_version}（从这台机器实测），"
                                 f"同一台（disk_total {in_total}G）。"}
        print(json.dumps(report, ensure_ascii=False, indent=2))
        return 0
    report |= {"status": "PASS",
               "message_zh": f"同一台（disk_total {in_total}G）——部署上去他就能看到。"}
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
