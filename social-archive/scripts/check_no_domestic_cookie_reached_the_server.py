#!/usr/bin/env python3
"""国内平台的登录信息，服务器上此刻到底有没有（2026-08-07）。

## 为什么要有它

`docs/使用说明.md` 对 Owner 说的最重的一句：

    国内平台（B站、小红书、抖音、快手）的登录信息**永远不离开浏览器**，
    这一条是写死在代码里的。

仓里为这条不变量（INV-DOMESTIC-COOKIE-STAYS）立过好几道门——**但它们全在扫代码**。
代码对不对，和**他那台服务器上此刻有没有**，是两个问题：一次误配、一次手工
导入、一个还没删干净的旧版本，都能让第二个问题的答案变成「有」，
而所有扫代码的门照样全绿。

2026-08-07 第一次去他生产库里真数：`platform_credential` **0 行**。
承诺成立。这条判据把「第一次去数」变成「每次部署都数」。

## 为什么它是门不是播报

其余几条生产侧检查（8.7 同步实况、8.8 产品说的话、8.9 三份副本）都是播报——
那些是「他那份数据长什么样」，不是部署的属性。**这一条不同**：
服务器上出现一把国内平台的 Cookie，是这个产品对他最硬的那条承诺被破了。
出现就该拦住发布，而不是打一行字让人自己看见。

## 边界

· 只读，而且**只读到「有几行、哪个平台」**——不取 cipher、不取任何密文字段。
· 它答不了「浏览器里那份有没有被别的东西拿走」；它只答服务端库里有没有。

    python3 scripts/check_no_domestic_cookie_reached_the_server.py --brief
"""

from __future__ import annotations

import sys as _sys
from pathlib import Path as _Path
_sys.path.insert(0, str(_Path(__file__).resolve().parent))
from production_host import deploy_host  # noqa: E402

import argparse
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from social_archive.credentials import DOMESTIC_PLATFORMS          # noqa: E402
from social_archive.git_env import clean_git_env                   # noqa: E402,F401

EVIDENCE = ROOT / "evidence" / "G5" / "NO_DOMESTIC_COOKIE_ON_SERVER.json"
REMOTE_DB = "/var/lib/social-archive/runtime/social-archive.sqlite3"


def judge(rows: list[dict], table_seen: bool) -> tuple[list[str], dict]:
    """**取数与判断分开**，好拿「有一行小红书」喂它证明它真的会红。"""
    problems: list[str] = []
    # **表不在不算通过。** 读不到就是不知道，而不知道不能读成「没有」——
    # 这个仓在「空默认值吞掉不知道」上栽过很多次。
    if not table_seen:
        problems.append(
            "**读不到 platform_credential 这张表**——这不是通过，是没数到。"
            "在能数到之前，说明书那句「永远不离开浏览器」在这台机器上验不了")
    offenders = sorted({str(row.get("platform") or "") for row in rows
                        if str(row.get("platform") or "").lower() in DOMESTIC_PLATFORMS})
    if offenders:
        problems.append(
            f"**服务器上存着国内平台的登录信息**：{offenders}——"
            "说明书对他说这四家的登录信息永远不离开浏览器（INV-DOMESTIC-COOKIE-STAYS），"
            "而它现在就在服务端库里")
    measured = {
        "domestic_platforms": sorted(DOMESTIC_PLATFORMS),
        "credential_rows_total": len(rows),
        "by_platform": {p: sum(1 for r in rows if str(r.get("platform")) == p)
                        for p in sorted({str(r.get("platform")) for r in rows})},
        "domestic_rows": len(offenders),
        "table_readable": table_seen,
    }
    return problems, measured


def main() -> int:
    parser = argparse.ArgumentParser(description="国内平台 Cookie 有没有到过服务器（只读）")
    parser.add_argument("--host", default=deploy_host())
    parser.add_argument("--brief", action="store_true")
    args = parser.parse_args()

    # **只 SELECT platform**：cipher、cipher_sha256 那几列一个字节都不取。
    query = (
        "import sqlite3,json;"
        f"c=sqlite3.connect('file:{REMOTE_DB}?mode=ro',uri=True);"
        "t=[r[0] for r in c.execute('SELECT name FROM sqlite_master WHERE type=\"table\" "
        "AND name=\"platform_credential\"')];"
        "rows=[{'platform':r[0]} for r in c.execute('SELECT platform FROM platform_credential')] if t else [];"
        "print(json.dumps({'table_seen':bool(t),'rows':rows}))"
    )
    done = subprocess.run(
        ["ssh", "-o", "ConnectTimeout=25", args.host, "sudo python3 -c " + json.dumps(query)],
        capture_output=True, text=True, check=False)
    try:
        payload = json.loads((done.stdout or "").strip().splitlines()[-1])
    except (ValueError, IndexError):
        print(json.dumps({"status": "FAIL", "error_code": "PRODUCTION_UNREADABLE",
                          "message_zh": "读不到生产库——**这不是通过**"},
                         ensure_ascii=False, indent=2))
        return 2

    problems, measured = judge(payload.get("rows") or [], bool(payload.get("table_seen")))
    report = {
        "status": "PASS" if not problems else "FAIL",
        "measured": measured,
        "problems": problems,
        "what_this_answers_zh": (
            "**他那台服务器上此刻有没有**国内平台的登录信息。"
            "仓里那几道 INV-DOMESTIC-COOKIE-STAYS 的门扫的是代码——"
            "代码对不对和服务器上有没有，是两个问题。"),
        "boundary_zh": "只读；只取「有几行、哪个平台」，不取 cipher 或任何密文字段。",
    }
    EVIDENCE.parent.mkdir(parents=True, exist_ok=True)
    EVIDENCE.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    if args.brief:
        print(f"  {report['status']} · 凭据表 {measured['credential_rows_total']} 行，"
              f"其中国内平台 {measured['domestic_rows']} 行")
        for item in problems:
            print(f"    · {item}")
    else:
        print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if not problems else 1


if __name__ == "__main__":
    sys.exit(main())
