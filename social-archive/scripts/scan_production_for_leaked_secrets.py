#!/usr/bin/env python3
"""生产上有没有明文密钥落进日志或运行数据（v0.0.0.7 / T05）。

## 为什么单独有它

`scan_plaintext_credentials.py` 查的是**这个仓**。而密钥最可能泄漏的地方
不在仓里——是日志：某个脚本顺手把环境变量打出来，或者异常回溯里带着令牌。
「值不进日志」这条不变量写在设计里好几处，**而在 2026-08-05 之前从没真查过**。

不是没查，是**验它的工具认不出该找什么**：那两道扫描门当时都认不出
Notion secret_、Obsidian REST、R2/OCI 私密访问密钥，以及 **age 私钥**——
占位符过滤按前缀跳过 A 开头的值，而 age 私钥永远以 `AGE-` 开头。
补齐之后这条才第一次可查。

## 它绝不做的事

**不打印值。** 只报 文件:行号 / 种类 / **值的长度**。
一个把密钥打出来给你看的泄漏检查器，自己就是下一个泄漏点。

## 边界

· 全程只读：ssh 过去读文件和 journal，不写、不改、不重启。
· 只覆盖**认得出的形状**。自定义格式（没有前缀、名字也不像 TOKEN/SECRET 的）
  这道门看不见。**0 命中的意思是「已知形状里一个都没有」，不是「一定没有」。**
· 日志只看 --days 指定的窗口，更早的已被 journald 轮转掉。

## 用法

    python3 scripts/scan_production_for_leaked_secrets.py            # 默认 14 天
    python3 scripts/scan_production_for_leaked_secrets.py --days 30
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
SCANNER = ROOT / "scripts/scan_plaintext_credentials.py"

DATA_ROOTS = (
    "/var/lib/social-archive/diagnostics",
    "/var/lib/social-archive/evidence",
    "/var/lib/social-archive/exports",
    "/var/lib/social-archive/staging",
    "/opt/social-archive/logs",
)
UNITS = (
    "social-archive",
    "social-archive-backup",
    "social-archive-replication",
    "social-archive-private-database-sync",
    "social-archive-status",
)

# 远端跑的那一段。**它 import 的是我们送过去的同一个扫描器**——
# 不在这里再抄一份判定逻辑，否则两份必然漂开（这一天已经在别处吃过这个亏）。
REMOTE = '''
import importlib.util, json, pathlib, subprocess, sys
spec = importlib.util.spec_from_file_location("s", "/tmp/sa_scanner.py")
m = importlib.util.module_from_spec(spec); spec.loader.exec_module(m)
data_roots, units, days = json.loads(sys.argv[1])
files = 0
hits = []
for root in data_roots:
    base = pathlib.Path(root)
    if not base.is_dir():
        continue
    for path in base.rglob("*"):
        if not path.is_file() or path.stat().st_size > 8_000_000:
            continue
        try:
            text = path.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            continue
        files += 1
        hits += m.scan_text(str(path), text)
lines = 0
for unit in units:
    out = subprocess.run(["journalctl", "-u", unit, "--since", f"-{days} days", "--no-pager"],
                         capture_output=True, text=True).stdout
    lines += out.count("\\n")
    hits += m.scan_text("journal:" + unit, out)
# **只报位置与长度，绝不带值。**
print(json.dumps({
    "files_scanned": files, "journal_lines": lines,
    "hits": [{"where": h["file"], "line": h["line_no"], "kind": h["kind"],
              "value_len": h["value_len"]} for h in hits],
}, ensure_ascii=False))
'''


def main() -> int:
    parser = argparse.ArgumentParser(description="查生产上有没有明文密钥落进日志或运行数据")
    parser.add_argument("--host", default=deploy_host())
    parser.add_argument("--days", type=int, default=14, help="日志回看多少天")
    args = parser.parse_args()

    if not SCANNER.is_file():
        print(json.dumps({"status": "FAIL", "error_code": "SCANNER_MISSING"}, ensure_ascii=False))
        return 2

    push = subprocess.run(["scp", "-q", str(SCANNER), f"{args.host}:/tmp/sa_scanner.py"],
                          capture_output=True, text=True, check=False)
    if push.returncode != 0:
        print(json.dumps({"status": "FAIL", "error_code": "SCANNER_NOT_DELIVERED",
                          "detail": push.stderr.strip()[:200]}, ensure_ascii=False))
        return 4
    try:
        payload = json.dumps([list(DATA_ROOTS), list(UNITS), args.days])
        done = subprocess.run(
            ["ssh", "-o", "ConnectTimeout=20", args.host,
             f"sudo python3 - {payload!r} <<'SA_EOF'\n{REMOTE}\nSA_EOF"],
            capture_output=True, text=True, check=False)
    finally:
        # 跑完把扫描器从生产删掉——不在别人的机器上留东西。
        subprocess.run(["ssh", "-o", "ConnectTimeout=20", args.host, "rm -f /tmp/sa_scanner.py"],
                       capture_output=True, check=False)

    line = next((ln for ln in done.stdout.splitlines() if ln.strip().startswith("{")), "")
    if done.returncode != 0 or not line:
        print(json.dumps({"status": "FAIL", "error_code": "REMOTE_SCAN_FAILED",
                          "detail": (done.stderr or done.stdout).strip()[-300:]},
                         ensure_ascii=False))
        return 4
    result = json.loads(line)
    if result["files_scanned"] == 0 and result["journal_lines"] == 0:
        # **什么都没扫到和「干净」长得一样。**
        print(json.dumps({"status": "FAIL", "error_code": "NOTHING_WAS_SCANNED",
                          "message_zh": "一个文件、一行日志都没扫到——**这不是通过**，"
                                        "多半是路径不对或没有权限。"}, ensure_ascii=False))
        return 4

    hits = result["hits"]
    print(json.dumps({
        "status": "PASS" if not hits else "FAIL",
        "host": args.host,
        "files_scanned": result["files_scanned"],
        "journal_lines": result["journal_lines"],
        "journal_window_days": args.days,
        "hits": hits,
        "note": "只报位置与值长，**从不打印值本身**——一个把密钥打给你看的检查器，"
                "自己就是下一个泄漏点。",
        "what_this_does_not_prove": "只覆盖认得出的形状；0 命中 = 「已知形状里一个都没有」，"
                                    f"不是「一定没有」。日志只看了 {args.days} 天。",
    }, ensure_ascii=False))
    return 0 if not hits else 4


if __name__ == "__main__":
    sys.exit(main())
