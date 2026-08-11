#!/usr/bin/env python3
r"""他的东西真的拿得回来吗——每次部署都真取一次（2026-08-11）。

## 这一格空了多久

`docs/DRILLS.md` 里三个恢复演练一直写着「定期」，而**「定期」没有闹钟**：
部署脚本里这三个脚本名出现 0 次。别的演练答的是**功能对不对**，
这三个答的是**东西还在不在、拿不拿得回来**——最贵的一格，没有任何自动触发。

不接进流程的原因是「要在生产机上跑、要几分钟」。今天量了：
运行库快照 **1.1 MB/批**，取一次 r2 + 一次 oci **实测 12 秒**（不是估的，是跑出来的）。
按铁律 7 算月操作量：备份每天约 120 轮 × 3 份 × 约 4 次 ≈ 4.5 万次/月，
是 R2 免费额度 Class A（100 万）的 **4.5%**；这个检查每次部署再加 4 次，
量级上看不见。**所以它没有理由停在「靠人记得」。**

## 它做什么

在生产机上，对**最新那批快照**，逐个可用的对象仓真跑一遍
`restore_runtime_db_drill.py`：下载 → 解密 → 解压 → 打开 → 数表 → 判是不是他的数据。

凭据全程由 systemd 发（`LoadCredential`），和备份服务自己拿的是同一套；
**这个脚本不读、不传、不打印任何密钥内容**，只经手它们的路径。

## 判据

**至少两份副本真的取得回来**，否则红。
第三份（GitHub）目前取不回——那把恢复令牌看不见 `LinzeColin/Private-Database`，
只有 Owner 能授权。取不回就如实写「取不回」，**不算通过、也不假装通过**。
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SECRETS = "/opt/social-archive/runtime/secrets"
BACKUPS = "/var/lib/social-archive/backups"

# 每一棵备份树各自要验什么。
#
# **private-database 这一格是量完才加的**：实测 2 秒（r2）。
# 它原来和另外两个一起挂在「定期」档，而「定期」没有闹钟——
# 拦着它的理由是「要在生产机上跑、要几分钟」，一量就发现那个理由对它根本不成立。
TARGETS = (
    {
        "key": "runtime-db",
        "drill": "restore_runtime_db_drill.py",
        "stores": ("r2", "oci"),
        "require": 2,
        "zh": "他的档案馆运行库（那 193 条内容就在这里面）",
    },
    {
        "key": "private-database",
        "drill": "restore_private_database_drill.py",
        "stores": ("r2",),
        "require": 1,
        "zh": "Private-Database 的 fact 包（哈希逐条对）",
    },
    {
        # 前两格答的是「索引取得回来吗」。**这一格答的是「索引和制品还对得上吗」**：
        # 索引说有 552 个制品，那些制品是不是真在对象仓里、字节是不是那个哈希。
        # 实测 1.3 秒/制品，全量约 12 分钟——**每次部署跑不起全量**，
        # 所以抽 25 个（32 秒），起点按版本号环形挪，几十版走完一圈。
        # 报告里必须写清「25/552」，不许长得像全量过了。
        "key": "disaster-recovery",
        "drill": "disaster_recovery_drill.py",
        "snapshots_from": "runtime-db",
        "stores": ("r2",),
        "require": 1,
        "sample": 25,
        "zh": "索引和制品对不对得上（抽样，不是全量）",
    },
)

# 每个仓要哪几把钥匙。名字是**路径的名字**，值从来不经过这个脚本。
CREDENTIALS = {
    "r2": (("r2_access_key_id", "R2_ACCESS_KEY_ID"),
           ("r2_secret_access_key", "R2_SECRET_ACCESS_KEY")),
    "oci": (("oci_access_key_id", "OCI_ACCESS_KEY_ID"),
            ("oci_secret_access_key", "OCI_SECRET_ACCESS_KEY")),
    "github": (("github_markdown_token", "GITHUB_TOKEN"),),
}


def _remote_script(target: dict, store: str) -> str:
    """在生产机上跑一次恢复演练。凭据由 systemd 发，命令行里只有路径。"""
    properties = [
        "--property=WorkingDirectory=/opt/social-archive",
        "--property=EnvironmentFile=/etc/social-archive/social-archive.env",
    ]
    for filename, variable in CREDENTIALS[store]:
        credential = filename if store != "github" else "github_token"
        properties.append(f"--property=LoadCredential={credential}:{SECRETS}/{filename}")
        properties.append(
            f"--property=Environment=SOCIAL_ARCHIVE_{variable}_FILE=%d/{credential}")
    snapshots = f"{BACKUPS}/{target.get('snapshots_from', target['key'])}"
    sample = ""
    if target.get("sample"):
        # **起点跟着版本号走**：同一版重复部署验同一批（可复现），
        # 发一版就挪一格（覆盖面往前推）。不用随机数——随机的东西没法回溯。
        tail = (ROOT / "VERSION").read_text(encoding="utf-8").strip().split(".")[-1]
        offset = (int(tail) if tail.isdigit() else 0) * target["sample"]
        sample = f" --limit {target['sample']} --offset {offset}"
    return (
        f'set -u; LAST=$(sudo ls -1 {snapshots} | tail -1); '
        f'T=$(sudo mktemp -d /var/tmp/restore-check-XXXX); '
        f'sudo systemd-run --pipe --wait --collect --quiet {" ".join(properties)} '
        f'/opt/social-archive/.venv/bin/python scripts/{target["drill"]} '
        f'--manifest {snapshots}/$LAST/manifest.json --from-store {store} --target $T{sample}; '
        # **成败要留住。** `sudo rm` 的退出码不能盖掉演练的（`pipe-to-tail-hides-the-exit-code`）。
        f'RC=$?; sudo rm -rf $T; echo "SNAPSHOT_BATCH=$LAST"; exit $RC'
    )


def restore_from(host: str, target: dict, store: str) -> dict:
    done = subprocess.run(
        ["ssh", "-o", "ConnectTimeout=20", host, _remote_script(target, store)],
        capture_output=True, text=True, check=False)
    result: dict = {"target": target["key"], "store": store, "exit_code": done.returncode}
    for line in reversed((done.stdout or "").strip().splitlines()):
        if line.startswith("SNAPSHOT_BATCH="):
            result["snapshot_batch"] = line.split("=", 1)[1]
            continue
        try:
            result["drill"] = json.loads(line)
            break
        except ValueError:
            continue
    if "drill" not in result:
        # 没有结构化结果也要说清楚——**不许把「读不懂」算成「没问题」**。
        tail = ((done.stdout or "") + (done.stderr or "")).strip()[-300:]
        result["drill"] = {"status": "FAIL", "error_code": "NO_STRUCTURED_RESULT",
                           "detail": tail}
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description="备份真的恢复得出来吗")
    parser.add_argument("--host", default=None)
    parser.add_argument("--only", default=None,
                        help="只验某一棵备份树（默认全验）")
    args = parser.parse_args()
    host = args.host or (ROOT / "deploy/PRODUCTION_HOST").read_text(encoding="utf-8").strip()

    targets = [t for t in TARGETS if not args.only or t["key"] == args.only]
    if not targets:
        print(json.dumps({"status": "FAIL", "error_code": "NO_SUCH_TARGET",
                          "asked_for": args.only,
                          "known": [t["key"] for t in TARGETS]},
                         ensure_ascii=False, indent=2))
        return 1

    problems: list[str] = []
    results: list[dict] = []
    for target in targets:
        attempts = [restore_from(host, target, store) for store in target["stores"]]
        good = [a for a in attempts if a["drill"].get("status") == "PASS"]
        for attempt in attempts:
            drill = attempt["drill"]
            if drill.get("status") != "PASS":
                problems.append(
                    f"{target['key']}／{attempt['store']} 取不回来："
                    f"{drill.get('error_code') or '未知'} "
                    f"{'；'.join(drill.get('problems') or []) or drill.get('message', '')}"[:220])
        if len(good) < target["require"]:
            problems.append(
                f"{target['key']}（{target['zh']}）能真正取回来的只有 {len(good)} 份，"
                f"要求至少 {target['require']} 份——"
                "**这一条红的意思是：出事的时候东西回不来。**")
        results.append({
            "key": target["key"], "zh": target["zh"],
            "restorable_copies": len(good), "required": target["require"],
            # 抽样的那一格必须把分母带出来，别让它长得像全量（`samples-cannot-support-universal-claims`）
            "coverage_zh": next((a["drill"].get("coverage_zh") for a in good
                                 if a["drill"].get("coverage_zh")), None),
            "content_rows_per_copy": {a["store"]: a["drill"].get("restored_counts", {}).get("content")
                                      for a in good if a["drill"].get("restored_counts")},
            "attempts": attempts,
        })

    print(json.dumps({
        "status": "FAIL" if problems else "PASS",
        "host": host,
        "targets": results,
        "problems": problems,
        "third_copy_zh":
            "第三份（GitHub）没在这里试——那把恢复令牌看不见 "
            "LinzeColin/Private-Database，**只有 Owner 能授权**。"
            "在他授权之前，这是「取不回」，不是「通过」。",
        "boundary_zh":
            "只读：远端副本只下载不改，落地在一次性目录、跑完就删；"
            "密钥由 systemd 发，这个脚本只经手路径、不读内容。",
    }, ensure_ascii=False, indent=2))
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
