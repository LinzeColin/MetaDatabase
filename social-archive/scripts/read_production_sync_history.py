#!/usr/bin/env python3
"""他那台生产上，自动同步到底发生过没有（2026-08-07）。

## 为什么要有这个脚本

验收条件第 1 条是**「至少一个真实平台的收藏能自动读进档案馆」**。
我一直在证明「机制走得通」——按钮按得动、接口够得着、演练全绿——
**却从来没去问一句：他那台机器上，这件事到底发生过没有。**

问了才知道发生过：2026-08-03 那晚 bilibili 发现 67 条导入 67 条、
douyin 发现 56 条导入 56 条。**验收条件第 1 条早就在他的真数据上成立过。**

也才知道它是怎么停的：8/4 之后每一次同步都是 0 条，最后一次的错误码是
`PLATFORM_PERMISSION_MISSING`——正是「`chrome.permissions.request` 在
service worker 里结构上不可能成功」那个缺陷。他从那天起就用不了了。

**这两件事都只能从他的数据里读出来，读不出来就只能猜。**

## 边界

· **只读。** `mode=ro` 打开，只 SELECT。不写、不改、不重启。
· 不取任何内容正文、不取 Cookie、不取凭据表里的任何字段——
  只数数、只读状态码。证据文件里不会出现他收藏了什么。
· 数字**全部现算**，不许手写：手写的数必然往好里漂。

    python3 scripts/read_production_sync_history.py
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
EVIDENCE = ROOT / "evidence" / "G1" / "PRODUCTION_AGGREGATION_REALLY_HAPPENED.json"
DB = "/var/lib/social-archive/runtime/social-archive.sqlite3"

REMOTE = r'''
import json, sqlite3
c = sqlite3.connect("file:%s?mode=ro", uri=True)
c.row_factory = sqlite3.Row
def rows(sql):
    return [dict(r) for r in c.execute(sql)]
out = {
  "relations_by_type": rows(
      "select relation_type, count(*) as n from user_relation group by 1 order by 2 desc"),
  "content_by_platform": rows(
      "select platform, count(*) as n from content group by 1 order by 2 desc"),
  "accounts": rows(
      "select platform, connection_state, auth_method, auto_sync_enabled, "
      "last_verified_at, last_sync_at, last_error_code from source_account"),
  "sync_runs": rows(
      "select platform, status, discovered_count, imported_count, failed_count, "
      "completeness, last_error_code, started_at from sync_run order by started_at"),
  "jobs": rows("select job_type, status, count(*) as n from job group by 1,2 order by 3 desc"),
}
print(json.dumps(out, ensure_ascii=False))
''' % DB


def main() -> int:
    parser = argparse.ArgumentParser(description="读生产的同步历史（只读）")
    parser.add_argument("--host", default=deploy_host())
    # **给人看的那几行由脚本自己打。**
    # 第一版把格式化写成部署脚本里嵌的一段 Python，转义当场崩了
    # （`\"` 落进单引号里）。散文放进模板会踩元字符，这个仓已经踩过三次。
    parser.add_argument("--brief", action="store_true",
                        help="只打给人看的几行（部署里用）")
    args = parser.parse_args()

    done = subprocess.run(
        ["ssh", "-o", "ConnectTimeout=25", args.host,
         "cd /opt/social-archive && sudo .venv/bin/python -"],
        input=REMOTE, capture_output=True, text=True, check=False)
    if done.returncode != 0 or not done.stdout.strip():
        print(json.dumps({"status": "FAIL", "error_code": "PRODUCTION_UNREADABLE",
                          "message_zh": (done.stderr or "读不到生产数据")[:300]},
                         ensure_ascii=False, indent=2))
        return 2
    measured = json.loads(done.stdout)

    runs = measured["sync_runs"]
    imported = [r for r in runs if (r.get("imported_count") or 0) > 0]
    total_imported = sum(r["imported_count"] for r in imported)
    platforms_that_worked = sorted({r["platform"] for r in imported})
    latest = runs[-1] if runs else None

    report = {
        # **判据是「有没有真的进过东西」，不是「跑过几次」。**
        # 跑过 20 次而一条没进，那是 20 次失败，不是 20 次同步。
        "status": "PASS" if platforms_that_worked else "FAIL",
        "criterion_zh": "至少一个真实平台的收藏能自动读进档案馆（验收条件第 1 条）",
        "platforms_that_really_imported": platforms_that_worked,
        "items_imported_by_automatic_sync": total_imported,
        "runs_that_imported_something": [
            {k: r[k] for k in ("platform", "discovered_count", "imported_count", "started_at")}
            for r in imported],
        "why_it_stopped_zh": (
            f"最后一次同步（{latest['platform']} {latest['started_at']}）"
            f"进了 {latest['imported_count']} 条，错误码 {latest['last_error_code']}"
            if latest else "没有任何同步记录"),
        "accounts_now": measured["accounts"],
        "all_runs": runs,
        "content_by_platform": measured["content_by_platform"],
        "relations_by_type": measured["relations_by_type"],
        "jobs": measured["jobs"],
        "boundary_zh": ("只读、只数数：不取任何内容正文、不取 Cookie、"
                        "不碰凭据表。这份证据里不会出现他收藏了什么。"),
    }
    EVIDENCE.parent.mkdir(parents=True, exist_ok=True)
    EVIDENCE.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n",
                        encoding="utf-8")
    if args.brief:
        worked = report["platforms_that_really_imported"] or ["（一个都没有）"]
        print(f"  自动同步真的进过东西的平台：{'、'.join(worked)}"
              f"，共 {report['items_imported_by_automatic_sync']} 条")
        print(f"  {report['why_it_stopped_zh']}")
        for account in report["accounts_now"]:
            state = "开" if account["auto_sync_enabled"] else "关"
            print(f"    {account['platform']:12} {account['connection_state']:12} 自动同步={state}")
        return 0            # **播报不当门**：它取决于他浏览器的状态，不是部署的属性
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if report["status"] == "PASS" else 1


if __name__ == "__main__":
    sys.exit(main())
