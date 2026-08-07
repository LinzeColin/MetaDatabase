#!/usr/bin/env python3
"""「加密存三份」——今天真的确认过几份（2026-08-07）。

## 为什么要有它

`docs/使用说明.md` 对 Owner 说：**「数据存在哪？你自己的服务器上，加密存三份。」**

库里 `object_replica` 那三行 `verified` 是**写入当时**的记录，不是今天的事实。
2026-08-07 拿新加的 `restore_object.py --presence-only` 在他生产机上真问了一遍：

    r2      PASS（对象还在，520 字节，age-x25519）
    oci     PASS（对象还在）
    github  读不到——那把 token 解析不了 LinzeColin/Private-Database

**而 GitHub 是 2026-08-04 迁移之后当主备份的那一份。**
三份里最要紧的那份，从生产机上够不着。

这条判据把「几份今天确认过」变成一个会说话的数，而不是继续假设三份都在。
它**不猜原因**（token 没权限？仓改名了？副本真没了？）——那要人去看。
它只负责让这件事不再是隐形的。

## 边界

· 只读：每家存储一次 HEAD / 一次列附件。不下载、不解密、不需要 age 私钥。
· 抽样，不是全量：552 个产物全查一遍要几百次往返。抽样能答
  「这家存储今天够不够得着」，**答不了「每一个对象都还在」**——报告里写明。
· 它不证明能还原出原文，那要 `--verify-only`（需要 age 私钥）。

    python3 scripts/check_the_three_copies_are_really_there.py --sample 3
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
EVIDENCE = ROOT / "evidence" / "G5" / "THREE_COPIES_TODAY.json"
STORES = ("r2", "oci", "github")


def summarise(per_store: dict[str, list[dict]]) -> tuple[list[str], dict]:
    """**取数与判断分开**，好拿构造出来的结果喂它证明它会红。"""
    problems: list[str] = []
    measured: dict[str, dict] = {}
    for store in STORES:
        rows = per_store.get(store) or []
        ok = [r for r in rows if r.get("status") == "PASS"]
        measured[store] = {
            "checked": len(rows), "present": len(ok),
            "codes": sorted({str(r.get("error_code")) for r in rows
                             if r.get("status") != "PASS"}),
        }
        if not rows:
            problems.append(f"**{store}：一个都没查**——这不是通过，是这条判据没跑到")
        elif not ok:
            # **「够不着」和「没了」要分开说**——读的人要做的事完全不同：
            # 前者去修凭据／配置，后者去补一份副本。混成一句会把人指错方向。
            blocked = [c for c in measured[store]["codes"]
                       if "NOT_VISIBLE" in c or "MISSING_CONFIG" in c
                       or c.endswith("CONFIG_MISSING") or "TOKEN_MISSING" in c]
            if blocked:
                problems.append(
                    f"**{store}：{len(rows)} 个抽样一个都**够不着**（{blocked}）——"
                    "**这不等于副本没了**，是这台机器上的凭据／配置到不了它。"
                    "在修好之前，说明书那句「加密存三份」在这台机器上验不出第三份")
            else:
                problems.append(
                    f"**{store}：{len(rows)} 个抽样一个都不在**"
                    f"（{measured[store]['codes']}）——"
                    "说明书对他说「加密存三份」，而这一份**真的找不到了**")
        elif len(ok) < len(rows):
            problems.append(
                f"**{store}：{len(rows)} 个抽样里只有 {len(ok)} 个在**"
                f"（{measured[store]['codes']}）")
    confirmed = sum(1 for store in STORES if measured[store]["present"] > 0)
    measured["copies_confirmed_today"] = confirmed
    if confirmed < 3:
        problems.append(
            f"**今天只确认了 {confirmed} 份，而说明书写的是三份。**"
            "在把这一句改掉、或者把够不着的那份修好之前，那句话是超售的。")
    return problems, measured


def _presence(artifact_id: str, store: str, host: str) -> dict:
    """在生产机上跑一次 presence。**env 要从 .env 加载**——三家的凭据路径都在那儿。"""
    command = (
        "cd /opt/social-archive && set -a && . ./.env && set +a && "
        f"timeout 120 .venv/bin/python scripts/restore_object.py "
        f"--artifact-id {artifact_id} --from-store {store} --presence-only"
    )
    done = subprocess.run(["ssh", "-o", "ConnectTimeout=25", host, "sudo bash -lc " + json.dumps(command)],
                          capture_output=True, text=True, check=False)
    line = (done.stdout or done.stderr or "").strip().splitlines()
    for raw in reversed(line):
        try:
            return json.loads(raw)
        except ValueError:
            continue
    return {"status": "FAIL", "error_code": "NO_JSON_BACK",
            "message": (done.stderr or "")[:120]}


def main() -> int:
    parser = argparse.ArgumentParser(description="三份副本今天还在不在（只读、抽样）")
    parser.add_argument("--host", default="linze-ovh")
    parser.add_argument("--sample", type=int, default=2)
    parser.add_argument("--brief", action="store_true")
    args = parser.parse_args()

    query = (
        "import sqlite3,json;"
        "c=sqlite3.connect('file:/var/lib/social-archive/runtime/social-archive.sqlite3?mode=ro',uri=True);"
        f"print(json.dumps([r[0] for r in c.execute('SELECT DISTINCT artifact_id FROM object_replica LIMIT {args.sample}')]))"
    )
    listing = subprocess.run(
        ["ssh", "-o", "ConnectTimeout=25", args.host, "sudo python3 -c " + json.dumps(query)],
        capture_output=True, text=True, check=False)
    try:
        artifacts = json.loads((listing.stdout or "").strip().splitlines()[-1])
    except (ValueError, IndexError):
        print(json.dumps({"status": "FAIL", "error_code": "ARTIFACT_LIST_UNREADABLE",
                          "message_zh": "读不到产物清单——**这不是通过**"},
                         ensure_ascii=False, indent=2))
        return 2

    per_store: dict[str, list[dict]] = {store: [] for store in STORES}
    for artifact_id in artifacts:
        for store in STORES:
            per_store[store].append(_presence(artifact_id, store, args.host))

    problems, measured = summarise(per_store)
    report = {
        "status": "PASS" if not problems else "FAIL",
        "sampled_artifacts": artifacts,
        "measured": measured,
        "problems": problems,
        "what_this_does_not_prove_zh": (
            "抽样只答「这家存储今天够不够得着」，**答不了「每一个对象都还在」**；"
            "也不证明能还原出原文——那要 --verify-only（需要 age 私钥）。"),
        "boundary_zh": "只读；每家一次 HEAD / 一次列附件；不下载、不解密。",
    }
    EVIDENCE.parent.mkdir(parents=True, exist_ok=True)
    EVIDENCE.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    if args.brief:
        print(f"  {report['status']} · 今天确认 {measured['copies_confirmed_today']}/3 份"
              f"（抽了 {len(artifacts)} 个产物）")
        for store in STORES:
            row = measured[store]
            print(f"    {store:<7} {row['present']}/{row['checked']}"
                  + (f"  {row['codes']}" if row["codes"] else ""))
    else:
        print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if not problems else 1


if __name__ == "__main__":
    sys.exit(main())
