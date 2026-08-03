#!/usr/bin/env python3
"""扫描明文凭据（v0.0.0.7 / T05）。

T05 的 Acceptance 有一条是「全仓扫描无明文」，Stop Condition 是
「任何一次扫描发现明文，立即停止整个 S2」。这个脚本就是那次扫描。

## 判据打在两个形态上，不是打在关键词上

只扫 "cookie" 这种词没有用——它在注释里到处都是，而真正的泄漏长得像
`auth_token\tAAAA...`。所以分两类判据：

  · **Netscape cookies.txt 行形态**：7 个 tab 分隔字段，域名开头。
    这是 gallery-dl / yt-dlp 要的格式，也是唯一会被写出来的形态。
  · **已知的高危 cookie 名后面跟着像值的东西**：auth_token / ct0 /
    sessionid / SAPISID 等，后面跟 16+ 个 base64/hex 字符。

两类都要，因为单看形态会漏掉被塞进 JSON 的单个值，
单看名字会被注释和字段名淹没。

## 扫描面

默认扫 logs/ evidence/ exports/ 与 `git diff HEAD`（含暂存与未暂存）。
可以 --all 扫整个受版本控制的仓库。

## 退出码

0 = 干净；1 = 发现疑似明文（此时 S2 必须停）；2 = 扫描本身失败。
**扫到 0 份文件也算失败**，报 2 而不是 0——"没扫到"和"没问题"长得一样，
这台机器已经吃过不止一次亏。
"""
from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

# Netscape cookies.txt：domain \t flag \t path \t secure \t expiry \t name \t value
COOKIE_LINE = re.compile(
    r"^#?(?:HttpOnly_)?\.?[a-z0-9][a-z0-9.-]*\.[a-z]{2,}\t"
    r"(?:TRUE|FALSE)\t\S+\t(?:TRUE|FALSE)\t\d+\t\S+\t\S{8,}",
    re.IGNORECASE | re.MULTILINE,
)

# 已知高危 cookie 名 + 像值的东西。名字后面允许 = : " 空格 tab 等分隔。
HIGH_RISK_NAMES = (
    "auth_token", "ct0", "twid", "kdt",              # X
    "sessionid", "csrftoken", "ds_user_id",          # Instagram
    "SAPISID", "SSID", "HSID", "SID", "__Secure-1PSID",  # Google/YouTube
    "reddit_session",
)
HIGH_RISK = re.compile(
    r"(?:" + "|".join(re.escape(n) for n in HIGH_RISK_NAMES) + r")"
    r"\s*[=:\t\"']\s*[\"']?([A-Za-z0-9_\-+/%.]{16,})",
)

# 这些是判据自己和文档，出现这些词是本来就该出现的。
SELF = {
    "scripts/scan_plaintext_credentials.py",
    "tests/focused/test_credential_custody.py",
    "src/social_archive/credentials.py",
}

# 明显的占位/示例值，不算泄漏。
PLACEHOLDER = re.compile(
    r"^(?:REDACTED|EXAMPLE|PLACEHOLDER|FAKE|TEST|DUMMY|XXX+|0+|A+|x+|"
    r"fixture[-_a-z0-9]*|sa-[a-z0-9-]*fixture[a-z0-9-]*|[a-z-]*fixture[a-z0-9-]*)",
    re.IGNORECASE,
)


def scan_text(name: str, text: str) -> list[dict]:
    hits = []
    for match in COOKIE_LINE.finditer(text):
        line = match.group(0)
        value = line.rsplit("\t", 1)[-1]
        if PLACEHOLDER.match(value):
            continue
        hits.append({"file": name, "kind": "netscape_cookie_line",
                     "line_no": text[:match.start()].count("\n") + 1,
                     "value_len": len(value)})
    for match in HIGH_RISK.finditer(text):
        value = match.group(1)
        if PLACEHOLDER.match(value):
            continue
        hits.append({"file": name, "kind": "high_risk_cookie_value",
                     "line_no": text[:match.start()].count("\n") + 1,
                     "value_len": len(value)})
    return hits


def tracked_files(all_files: bool) -> list[Path]:
    if all_files:
        out = subprocess.run(["git", "ls-files"], cwd=ROOT, text=True,
                             capture_output=True, check=True).stdout.split("\n")
        return [ROOT / p for p in out if p.strip()]
    paths: list[Path] = []
    for folder in ("logs", "evidence", "exports"):
        base = ROOT / folder
        if base.is_dir():
            paths += [p for p in base.rglob("*") if p.is_file()]
    return paths


def main() -> int:
    parser = argparse.ArgumentParser(description="扫描明文凭据")
    parser.add_argument("--all", action="store_true", help="扫描全部受版本控制的文件")
    parser.add_argument("--json", type=Path, default=None, help="把结果写成 JSON")
    args = parser.parse_args()

    hits: list[dict] = []
    scanned = 0
    for path in tracked_files(args.all):
        rel = str(path.relative_to(ROOT))
        if rel in SELF or ".venv" in rel or rel.startswith(".git/"):
            continue
        try:
            text = path.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            continue
        scanned += 1
        hits += scan_text(rel, text)

    # git diff 也要扫：文件可能还没提交，但已经在暂存区里等着被推上去。
    diff_scanned = 0
    for argv in (["git", "diff"], ["git", "diff", "--cached"]):
        try:
            diff = subprocess.run(argv, cwd=ROOT, text=True, capture_output=True,
                                  check=True).stdout
        except subprocess.CalledProcessError:
            continue
        diff_scanned += 1
        hits += scan_text(" ".join(argv), diff)

    result = {
        "scanned_files": scanned,
        "scanned_diffs": diff_scanned,
        "hits": hits,
        "clean": not hits,
    }
    if args.json:
        args.json.parent.mkdir(parents=True, exist_ok=True)
        args.json.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    if scanned == 0:
        print("!! 扫描面为 0 个文件——判据在空转，这和「没问题」长得一样", file=sys.stderr)
        return 2
    if hits:
        print(f"!! 发现 {len(hits)} 处疑似明文凭据（S2 必须停）：", file=sys.stderr)
        for hit in hits[:20]:
            print(f"   {hit['file']}:{hit['line_no']} {hit['kind']} 值长 {hit['value_len']}", file=sys.stderr)
        return 1
    print(f"干净：扫了 {scanned} 个文件 + {diff_scanned} 份 diff，0 处命中")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
