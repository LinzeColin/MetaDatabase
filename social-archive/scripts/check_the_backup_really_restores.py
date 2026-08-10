#!/usr/bin/env python3
"""把运行库快照真的还原一次，打开它，数他的行（2026-08-10）。

## 为什么单开这一个

`check_the_three_copies_are_really_there.py` 答的是「副本在不在」，
今天已经升到「单个产物真取得回来」。**而真正丢了会疼的是运行库本身**——
他的 193 条内容、三个账号、194 条关系全在那一个 SQLite 里。

那件事本来有演练（`restore_runtime_db_drill.py`：下载 → 解密 → 解压 →
打开 → 数表），**而它从来没跑过**。`evidence/G3/ALL_DRILLS.json` 里
一直挂在 `not_run`，理由写的是「要真实的备份清单与远端存储」——
**那个理由是错的**：清单每 15 分钟就有一份新的。真因是
`backup._s3_config` 少了凭据回退（`.env` 里的 `/run/secrets/…`
在 systemd unit 之外不存在），于是它报「r2 未配置」。

代价很实在：**「他的东西真能拿回来」这件事，在这条流水线里从来没被证明过，
而所有人都以为那是环境不具备、不是缺陷。**

2026-08-10 修好之后第一次真跑通（r2 与 oci 各一次）：

    restored_counts = {content: 193, user_relation: 194, artifact: 552,
                       object_replica: 1656, destination_receipt: 391}
    live_counts_now = 同上，逐项相同

## 它怎么跑

在**生产机上**跑（凭据和密钥都在那儿，一步都不离开那台机器）。
落地目录是 /tmp 下的临时目录，演练自己会拒绝落进数据面；跑完就删。

## 边界

· 只读远端；不写任何生产路径。
· 每次只取**一份**快照 × 每家一次：铁律 7 的账是每天几次部署 × 3 家，
  远在免费额度之下，而且这正是那条规矩说的「逐字节复核按天/周跑」。
· 它答的是「快照还原得开、行数对得上」，**不逐行比内容**。
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
EVIDENCE = ROOT / "evidence" / "G5" / "BACKUP_REALLY_RESTORES.json"
STORES = ("r2", "oci")


def _ssh(host: str, command: str, timeout: int = 600) -> str:
    done = subprocess.run(
        ["ssh", "-o", "ConnectTimeout=25", host, "sudo bash -lc " + json.dumps(command)],
        capture_output=True, text=True, check=False, timeout=timeout)
    return (done.stdout or done.stderr or "").strip()


def _latest_manifest(host: str) -> str | None:
    out = _ssh(host, "ls -1d /var/lib/social-archive/backups/runtime-db/*/ 2>/dev/null | sort | tail -1")
    line = out.strip().splitlines()[-1] if out.strip() else ""
    return (line.rstrip("/") + "/manifest.json") if line.startswith("/var/lib/") else None


def _restore(host: str, manifest: str, store: str) -> dict:
    target = f"/tmp/sa-restore-verify-{store}"
    command = (
        f"rm -rf {target} && cd /opt/social-archive && set -a && . ./.env && set +a && "
        f"timeout 420 .venv/bin/python scripts/restore_runtime_db_drill.py "
        f"--manifest {manifest} --from-store {store} --target {target}"
    )
    out = _ssh(host, command)
    _ssh(host, f"rm -rf {target}")                     # 自己开的自己收
    for raw in reversed(out.splitlines()):
        try:
            return json.loads(raw)
        except ValueError:
            continue
    return {"status": "FAIL", "error_code": "NO_JSON_FROM_DRILL",
            "tail": out.splitlines()[-1][:200] if out.splitlines() else ""}


def main() -> int:
    parser = argparse.ArgumentParser(description="把运行库快照真的还原一次并数行")
    parser.add_argument("--host", default=deploy_host())
    parser.add_argument("--brief", action="store_true")
    args = parser.parse_args()

    manifest = _latest_manifest(args.host)
    if not manifest:
        report = {"status": "FAIL", "error_code": "NO_MANIFEST",
                  "message_zh": "主机上一份快照清单都找不到——**这不是通过**，"
                                "是备份本身没在跑"}
        EVIDENCE.parent.mkdir(parents=True, exist_ok=True)
        EVIDENCE.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
        print(json.dumps(report, ensure_ascii=False, indent=2))
        return 2

    per_store = {store: _restore(args.host, manifest, store) for store in STORES}
    ok = [store for store, row in per_store.items() if row.get("status") == "PASS"]
    problems: list[str] = []
    for store in STORES:
        row = per_store[store]
        if row.get("status") != "PASS":
            problems.append(
                f"**{store}：快照还原不出来**（{row.get('error_code') or row.get('status')}）"
                "——「副本在那儿」不等于「拿得回来」，这一条答的是后者")
    # **还原出来的行数要和活库对得上。** 演练自己会带 live_counts_now，
    # 差异可以有（快照之后又写了几行），但**content 变少**说明快照那一刻就缺东西。
    for store in ok:
        row = per_store[store]
        got = (row.get("restored_counts") or {}).get("content")
        live = (row.get("live_counts_now") or {}).get("content")
        if got is None or live is None:
            problems.append(f"**{store}：还原成功却没数出行数**——这不是通过，是没量到")
        elif got < live * 0.9:
            problems.append(
                f"**{store}：还原出来只有 {got} 条，活库有 {live} 条**——"
                "差得太多，那份快照不能当成他的数据")

    report = {
        "status": "PASS" if not problems else "FAIL",
        "manifest": manifest,
        "stores_restored": ok,
        "per_store": per_store,
        "problems": problems,
        "message_zh": (f"运行库快照真的还原出来了（{'、'.join(ok)}），行数与活库对得上。"
                       if not problems else "**「拿得回来」这件事没成立。**"),
        "what_this_does_not_prove": (
            "只验一份最新快照、只数表的行数，不逐行比内容；"
            "也不验第三份（GitHub）——那把恢复 token 看不见那个仓，是 Owner 的授权问题。"),
    }
    EVIDENCE.parent.mkdir(parents=True, exist_ok=True)
    EVIDENCE.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    if args.brief:
        print(f"  {report['message_zh']}")
        for problem in problems:
            print(f"    {problem}")
    else:
        print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if not problems else 4


if __name__ == "__main__":
    sys.exit(main())
