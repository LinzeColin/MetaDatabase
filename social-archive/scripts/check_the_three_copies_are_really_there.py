#!/usr/bin/env python3
"""「加密存三份」——今天真的确认过几份（2026-08-07）。

## 为什么要有它

`docs/使用说明.md` 原来对 Owner 说：**「数据存在哪？你自己的服务器上，加密存三份。」**

2026-08-10 那句话改了：现在写的是**实测确认到的份数**，并且
`check_the_guide_matches_the_product.py` 的规则 ⑧ 逼说明书里那个数
必须等于本文件量出来的 `copies_confirmed_today`——
**说明书不会再超售了。但少一份仍旧是少一份**：这条判据答的是
「服务器没了的那天，真能拿回数据的地方有几处」，
那件事不因为改了一句话而变好。

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
                    "在修好之前，这一份在灾难那天也一样拿不回来")
            else:
                problems.append(
                    f"**{store}：{len(rows)} 个抽样一个都不在**"
                    f"（{measured[store]['codes']}）——这一份**真的找不到了**")
        elif len(ok) < len(rows):
            problems.append(
                f"**{store}：{len(rows)} 个抽样里只有 {len(ok)} 个在**"
                f"（{measured[store]['codes']}）")
    confirmed = sum(1 for store in STORES if measured[store]["present"] > 0)
    measured["copies_confirmed_today"] = confirmed
    if confirmed < 3:
        # **说明书已经不超售了**（2026-08-10 改成写实测数，规则 ⑧ 逼两边相等），
        # 所以这一条不再是「话说大了」，而是**能力本身还差一份**：
        # 服务器没了的那天，能拿回数据的地方只有 {confirmed} 处。
        # 这两件事要分开说——把它们混成一句，改一句话就会显得问题解决了。
        problems.append(
            f"**今天只确认了 {confirmed} 份，目标是 3 份。**"
            "说明书写的就是这个实测数，所以他读到的不假；"
            f"但服务器没了的那天，真能拿回数据的地方只有 {confirmed} 处。")
    return problems, measured


def _really_restores(artifact_id: str, store: str, host: str) -> dict:
    """**真取回来一次**：下载 → 解密 → 明文哈希对上。

    2026-08-10 才第一次做这件事。在这之前这条判据只跑 `--presence-only`
    （HeadObject），而说明书那句写的是「今天能确认**拿得回来**的是 N 处」——
    **「在那儿」不等于「拿得回来」**：密文可能坏、密钥可能对不上、
    取回路可能根本没通（这个仓栽过：三份副本全登记 verified，
    而 GitHub 那条取回路跑不通）。

    用 `--verify-only`：完整走一路但不落盘，不碰生产任何路径。
    铁律 7 的账：1 个对象 × 3 家 × 每天几次部署 × 31 天 ≈ 几百次 Class B，
    免费额度是 1000 万——而且这正是那条规矩说的「逐字节复核按天/周跑」，
    不是它禁止的「整包下载来判断存在」。
    """
    command = (
        "cd /opt/social-archive && set -a && . ./.env && set +a && "
        f"timeout 180 .venv/bin/python scripts/restore_object.py "
        f"--artifact-id {artifact_id} --from-store {store} --verify-only"
    )
    done = subprocess.run(["ssh", "-o", "ConnectTimeout=25", host, "sudo bash -lc " + json.dumps(command)],
                          capture_output=True, text=True, check=False)
    for raw in reversed((done.stdout or done.stderr or "").strip().splitlines()):
        try:
            return json.loads(raw)
        except ValueError:
            continue
    return {"status": "FAIL", "error_code": "NO_JSON_FROM_RESTORE"}


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
    parser.add_argument("--host", default=deploy_host())
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

    # **抽样只问「在不在」；再挑一个真取回来一次。**（2026-08-10）
    #
    # 说明书那句写的是「今天能确认**拿得回来**的是 N 处」，
    # 而在这之前这条判据只跑 HeadObject。**「在那儿」不等于「拿得回来」**——
    # 密文可能坏、密钥可能对不上、取回路可能根本没通（这个仓栽过：
    # 三份副本全登记 verified，而 GitHub 那条取回路跑不通）。
    #
    # 只取第一个产物、每家一次：铁律 7 的账是每天几百次 Class B，
    # 免费额度一千万；而且这正是那条规矩说的「逐字节复核按天/周跑」。
    restored: dict[str, dict] = {}
    if artifacts:
        for store in STORES:
            restored[store] = _really_restores(artifacts[0], store, args.host)

    problems, measured = summarise(per_store)
    measured["restore_probe_artifact"] = artifacts[0] if artifacts else None
    really = [store for store in STORES if (restored.get(store) or {}).get("status") == "PASS"]
    measured["restore_verified"] = really
    measured["copies_really_restorable_today"] = len(really)
    for store in STORES:
        row = restored.get(store) or {}
        if measured.get(store, {}).get("present", 0) > 0 and row.get("status") != "PASS":
            problems.append(
                f"**{store}：抽样说它在，而真取回来失败了**"
                f"（{row.get('error_code') or row.get('status')}）——"
                "「在那儿」不等于「拿得回来」，说明书那句写的是后者")
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
