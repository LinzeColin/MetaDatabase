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
SNAPSHOTS = "/var/lib/social-archive/backups/runtime-db"

# 每个仓要哪几把钥匙。名字是**路径的名字**，值从来不经过这个脚本。
CREDENTIALS = {
    "r2": (("r2_access_key_id", "R2_ACCESS_KEY_ID"),
           ("r2_secret_access_key", "R2_SECRET_ACCESS_KEY")),
    "oci": (("oci_access_key_id", "OCI_ACCESS_KEY_ID"),
            ("oci_secret_access_key", "OCI_SECRET_ACCESS_KEY")),
    "github": (("github_markdown_token", "GITHUB_TOKEN"),),
}


def _remote_script(store: str) -> str:
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
    return (
        f'set -u; LAST=$(sudo ls -1 {SNAPSHOTS} | tail -1); '
        f'T=$(sudo mktemp -d /var/tmp/restore-check-XXXX); '
        f'sudo systemd-run --pipe --wait --collect --quiet {" ".join(properties)} '
        f'/opt/social-archive/.venv/bin/python scripts/restore_runtime_db_drill.py '
        f'--manifest {SNAPSHOTS}/$LAST/manifest.json --from-store {store} --target $T; '
        # **成败要留住。** `sudo rm` 的退出码不能盖掉演练的（`pipe-to-tail-hides-the-exit-code`）。
        f'RC=$?; sudo rm -rf $T; echo "SNAPSHOT_BATCH=$LAST"; exit $RC'
    )


def restore_from(host: str, store: str) -> dict:
    done = subprocess.run(
        ["ssh", "-o", "ConnectTimeout=20", host, _remote_script(store)],
        capture_output=True, text=True, check=False)
    result: dict = {"store": store, "exit_code": done.returncode}
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
    parser.add_argument("--stores", default="r2,oci",
                        help="真去取的那几份（github 那份要 Owner 先授权，见文档）")
    parser.add_argument("--require", type=int, default=2, help="至少几份要取得回来")
    args = parser.parse_args()
    host = args.host or (ROOT / "deploy/PRODUCTION_HOST").read_text(encoding="utf-8").strip()

    attempts = [restore_from(host, store) for store in args.stores.split(",") if store]
    restorable = [a for a in attempts if a["drill"].get("status") == "PASS"]
    problems: list[str] = []
    for attempt in attempts:
        drill = attempt["drill"]
        if drill.get("status") != "PASS":
            problems.append(
                f"{attempt['store']} 那份取不回来："
                f"{drill.get('error_code') or '未知'} "
                f"{'；'.join(drill.get('problems') or []) or drill.get('message', '')}"[:200])
    if len(restorable) < args.require:
        problems.append(
            f"能真正取回来的副本只有 {len(restorable)} 份，要求至少 {args.require} 份——"
            "**这一条红的意思是：出事的时候东西回不来。**")

    rows = {}
    for attempt in restorable:
        rows[attempt["store"]] = attempt["drill"].get("restored_counts", {}).get("content")

    print(json.dumps({
        "status": "FAIL" if problems else "PASS",
        "host": host,
        "restorable_copies": len(restorable),
        "content_rows_per_copy": rows,
        "attempts": attempts,
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
