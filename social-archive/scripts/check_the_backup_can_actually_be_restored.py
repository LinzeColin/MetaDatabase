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

在生产机上，**给每个对象仓各挑一批它自己有收据的最新快照**，逐个真跑一遍
`restore_runtime_db_drill.py`：下载 → 解密 → 解压 → 打开 → 数表 → 判是不是他的数据。

凭据全程由 systemd 发（`LoadCredential`），和备份服务自己拿的是同一套；
**这个脚本不读、不传、不打印任何密钥内容**，只经手它们的路径。

## 判据

**三份副本都要真的取得回来**，否则红。

第三份（GitHub）此前一直报「取不回，只有 Owner 能授权」——**那句话是错的**，
2026-08-11 查清楚了，两个原因叠在一起，没有一个跟权限有关：

1. **比错了对照物**：这里一律取最新那批快照，而三份写齐只发生在每天 03:28
   那一次备份服务里；r2/oci 每 15 分钟一份。于是 github 永远落在一批
   根本没有它收据的快照上。现在每个 store 各挑自己最新的那一批。
2. **拿错了令牌**：`.env` 指的 `/run/secrets/github_token` 是容器内路径，
   宿主机上不存在；按文件名回退正好落到另一把**看不见那个仓**的令牌上。
   而同一台机器上的 `github_markdown_token` 对那个仓是 ADMIN——
   备份服务自己就是靠 `LoadCredential` 映射到它才写得成功的。

改完实测：三份全部真取回来（下载 → 解密 → 打开 → 判），各 193 条。
"""

from __future__ import annotations

import argparse
import base64
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
        "stores": ("r2", "oci", "github"),
        "require": 3,
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


# 给某个 store 挑「最新的、带这个 store 收据的那一批快照」。
#
# **一律取最新是错的**（2026-08-11 实测）：r2/oci 每 15 分钟写一份，
# 而三份写齐只发生在每天 03:28 那一次备份服务里。取最新那批 →
# github 永远落在一批根本没有它收据的快照上 → 判据恒红，
# 而且红得会骗人：报出来是「第三份取不回」，读起来像副本没了或权限不够，
# 实际是**拿错了对照物**。
PICK_LATEST = """
import json, os, sys
root, store = sys.argv[1], sys.argv[2]
for name in sorted(os.listdir(root), reverse=True):
    try:
        manifest = json.load(open(os.path.join(root, name, "manifest.json")))
    except Exception:
        continue
    if (manifest.get("receipts") or {}).get(store):
        print(name)
        break
"""


def _b64(text: str) -> str:
    """把脚本编码后再上命令行——中间隔着两层 shell，别赌它们怎么解释转义。"""
    return base64.b64encode(text.encode("utf-8")).decode("ascii")


def github_secret_from_unit(host: str) -> str | None:
    """备份服务把**哪一个文件**当 github_token 用——真源是那个单元，不是这里。

    这台机器上有两把 GitHub 令牌，而它们能看见的东西不一样（实测）：

        runtime/secrets/github_token           看不见 Vault 仓
        runtime/secrets/github_markdown_token  ADMIN

    `.env` 里写的是 `/run/secrets/github_token`——**那是容器内的路径**，
    宿主机上不存在；按文件名回退又正好落到上面那把看不见仓的。
    备份服务自己是靠 `LoadCredential=github_token:<markdown 那把>` 绕过去的，
    所以这里照抄它的映射，而不是再猜一次。取不到就明说，不静默用一把可能是错的。
    """
    done = subprocess.run(
        ["ssh", "-o", "ConnectTimeout=20", host,
         "sudo systemctl cat social-archive-backup.service"],
        capture_output=True, text=True, check=False)
    for line in (done.stdout or "").splitlines():
        line = line.strip()
        if line.startswith("LoadCredential=github_token:"):
            return line.split(":", 1)[1].strip()
    return None


def _remote_script(target: dict, store: str, github_secret: str | None) -> str:
    """在生产机上跑一次恢复演练。凭据由 systemd 发，命令行里只有路径。"""
    properties = [
        "--property=WorkingDirectory=/opt/social-archive",
        "--property=EnvironmentFile=/etc/social-archive/social-archive.env",
    ]
    exports = []
    for filename, variable in CREDENTIALS[store]:
        credential = filename if store != "github" else "github_token"
        source = github_secret if store == "github" else f"{SECRETS}/{filename}"
        properties.append(f"--property=LoadCredential={credential}:{source}")
        # **不能用 `Environment=...=%d/xxx`。**（2026-08-11 实测）
        # `%d` 只有写在单元文件里才展开；经 `systemd-run --property=Environment=`
        # 传进去时它是**字面量**，程序拿到的就是字符串 "%d/github_token"。
        # r2/oci 侥幸没事，是因为 `_s3_config` 有一条按文件名回退的路；
        # github 没有那条路，于是报「缺少 gh 或 GitHub 令牌」——一句指向错方向的话。
        # 反斜杠是给**外层** shell 看的：`sh -c "..."` 那层不许展开
        # `$CREDENTIALS_DIRECTORY`，要留给 systemd 起的那个内层 shell 自己展开。
        exports.append(
            rf'export SOCIAL_ARCHIVE_{variable}_FILE=\"\$CREDENTIALS_DIRECTORY/{credential}\";')
    snapshots = f"{BACKUPS}/{target.get('snapshots_from', target['key'])}"
    sample = ""
    if target.get("sample"):
        # **起点跟着版本号走**：同一版重复部署验同一批（可复现），
        # 发一版就挪一格（覆盖面往前推）。不用随机数——随机的东西没法回溯。
        tail = (ROOT / "VERSION").read_text(encoding="utf-8").strip().split(".")[-1]
        offset = (int(tail) if tail.isdigit() else 0) * target["sample"]
        sample = f" --limit {target['sample']} --offset {offset}"
    inner = (" ".join(exports)
             + f' exec /opt/social-archive/.venv/bin/python scripts/{target["drill"]}'
               f' --manifest {snapshots}/$LAST/manifest.json --from-store {store}'
               f' --target $T{sample}')
    return (
        # **脚本要 base64 送过去。**（2026-08-11 实测）
        # 先前用 `json.dumps(...)` 直接塞进命令行：JSON 把换行写成 `\n`，
        # 而远端 shell 在双引号里**不解释**这个转义——脚本被压成一行带字面 `\n` 的东西，
        # python 报 SyntaxError，取回来是空串。于是每一棵树、每一个 store 都判成
        # 「没有任何一批带这个收据的快照」——**一个我自己造出来的、全线飘红的假象**。
        f'set -u; LAST=$(sudo python3 -c "import base64;exec(base64.b64decode(\'{_b64(PICK_LATEST)}\'))"'
        f' {snapshots} {store}); '
        f'if [ -z "$LAST" ]; then '
        f'echo {json.dumps(json.dumps({"status": "FAIL", "error_code": "NO_MANIFEST_WITH_THIS_RECEIPT", "message": f"{snapshots} 底下没有任何一批带 {store} 收据的快照"}, ensure_ascii=False))}; '
        f'exit 4; fi; '
        f'T=$(sudo mktemp -d /var/tmp/restore-check-XXXX); '
        f'sudo systemd-run --pipe --wait --collect --quiet {" ".join(properties)} '
        f'/bin/sh -c "{inner}"; '
        # **成败要留住。** `sudo rm` 的退出码不能盖掉演练的（`pipe-to-tail-hides-the-exit-code`）。
        f'RC=$?; sudo rm -rf $T; echo "SNAPSHOT_BATCH=$LAST"; exit $RC'
    )


def restore_from(host: str, target: dict, store: str, github_secret: str | None = None) -> dict:
    if store == "github" and not github_secret:
        # **取不到映射就明说**，不要退回去用一把可能看不见那个仓的令牌——
        # 那正是这次要修掉的假红。
        return {"target": target["key"], "store": store, "exit_code": 0,
                "drill": {"status": "FAIL", "error_code": "GITHUB_CREDENTIAL_MAPPING_NOT_FOUND",
                          "message": "备份单元里读不到 LoadCredential=github_token:<路径>，"
                                     "**这不是通过**：不知道该用哪把令牌就不许猜"}}
    done = subprocess.run(
        ["ssh", "-o", "ConnectTimeout=20", host, _remote_script(target, store, github_secret)],
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

    github_secret = github_secret_from_unit(host)
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
        attempts = [restore_from(host, target, store, github_secret)
                    for store in target["stores"]]
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
            "第三份（GitHub）现在**也真取一次**。它此前报「取不回、只有 Owner 能授权」"
            "是两个自己的毛病叠出来的：比的是一批没有它收据的快照，用的是一把看不见"
            "那个仓的令牌——**都跟权限无关**。",
        "boundary_zh":
            "只读：远端副本只下载不改，落地在一次性目录、跑完就删；"
            "密钥由 systemd 发，这个脚本只经手路径、不读内容。",
    }, ensure_ascii=False, indent=2))
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
