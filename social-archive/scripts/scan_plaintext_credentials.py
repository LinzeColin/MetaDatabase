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

# **这道门原来只认浏览器 Cookie。**
#
# 2026-08-05 在验另一件事时顺手拿 `GITHUB_TOKEN = "ghp_…"` 造了 25 处泄漏，
# 它报 **0 处命中**。挨个试了一遍这个项目真正持有的那几种：
#
#     GitHub 经典令牌 ghp_…            认不出
#     GitHub 细粒度   github_pat_…     认不出
#     Notion 密钥     secret_…         认不出
#     Obsidian REST                    认不出
#     R2 / OCI 访问密钥                 认不出
#     X 的 auth_token                  认得（只有 Cookie 这一类认得）
#
# 而部署时挂的密钥有 12 个，上面这几种全在里面。**一道叫「查明文凭据」的门，
# 查不出这个仓最可能泄漏的那几种凭据。** 这个仓还有过一次 GitHub client secret
# 外泄的前科。
#
# 按**值的形状**认（真的密钥扫描器都这么做）：前缀是密钥自己带的，
# 改名字骗不过去。占位符由下面 PLACEHOLDER 那条继续过滤。
TOKEN_SHAPES = (
    ("GitHub 经典令牌", re.compile(r"\bghp_[A-Za-z0-9]{36}\b")),
    ("GitHub 细粒度令牌", re.compile(r"\bgithub_pat_[A-Za-z0-9_]{22,}")),
    ("GitHub OAuth 客户端密钥", re.compile(r"\bghs_[A-Za-z0-9]{36}\b")),
    ("Notion 集成密钥", re.compile(r"\b(?:secret_|ntn_)[A-Za-z0-9]{40,}")),
    ("Slack 令牌", re.compile(r"\bxox[baprs]-[A-Za-z0-9-]{10,}")),
    ("AWS/S3 兼容访问密钥 ID", re.compile(r"\bAKIA[0-9A-Z]{16}\b")),
    ("age 私钥", re.compile(r"\bAGE-SECRET-KEY-1[0-9A-Z]{50,}")),
    ("PEM 私钥块", re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH |PGP )?PRIVATE KEY-----")),
)

# 这个项目自己那 12 个密钥的环境变量名。名字不同于上面的形状检测：
# 形状认的是「这串东西长得像密钥」，名字认的是「这一行在给密钥赋值」。
# **关键词必须落在名字末尾，不能只是「名字里出现过」。**
#
# 第一版写成 `…(?:TOKEN|SECRET|…)[A-Z0-9_]*\s*[=:]`，于是
# `SECRETS_GROUP="socialarchive-secrets"` 被报成明文凭据——那是个**用户组名**。
# 全仓扫出的两处命中全是它。**一道见谁都喊的安全门，很快就没人看了**，
# 或者被加一条大而化之的豁免，然后真泄漏也一起被豁免掉。
SECRET_ENV_NAMES = re.compile(
    r"\b(?:SOCIAL_ARCHIVE_)?[A-Z0-9_]*"
    r"(?:TOKEN|SECRET|ACCESS_KEY|API_KEY|PASSWORD|IDENTITY)"
    r"\s*[=:]\s*[\"']?([A-Za-z0-9_\-+/%.]{20,})",
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
#
# **原来这条把一大批真密钥当成占位符扔掉了。** `0+|A+|x+` 这几个分支写在
# 一个只有 `^` 锚点的 match 里，于是它们按**前缀**匹配——凡是以 a / A / x /
# X / 0 开头的值，一律被当成占位符跳过。实测：
#
#     a1b2c3d4e5f6…（Obsidian REST 令牌的形状）  → 被跳过
#     AGE-SECRET-KEY-1…（**每一把 age 私钥**）    → 被跳过
#     x7f3b9…                                   → 被跳过
#
# 也就是说这道门对「以那几个字符开头的密钥」是瞎的，而 age 私钥
# **永远**以 AGE- 开头——那是全机唯一一把能解开所有异地备份的钥匙。
#
# 现在分成两类：**重复字符类必须整串匹配**（那才叫占位符），
# 词类仍按前缀（REDACTED_xxx、fixture-abc 都是占位）。
PLACEHOLDER_WORDS = re.compile(
    r"^(?:REDACTED|EXAMPLE|PLACEHOLDER|FAKE|TEST|DUMMY|"
    r"fixture[-_a-z0-9]*|sa-[a-z0-9-]*fixture[a-z0-9-]*|[a-z-]*fixture[a-z0-9-]*)",
    re.IGNORECASE,
)
PLACEHOLDER_REPEATS = re.compile(r"^(?:X+|A+|x+|0+)$", re.IGNORECASE)


def _is_placeholder(value: str) -> bool:
    return bool(PLACEHOLDER_WORDS.match(value) or PLACEHOLDER_REPEATS.fullmatch(value))


class _PlaceholderCompat:
    """保留 `PLACEHOLDER.match(...)` 这个既有写法，行为换成上面那个。"""

    @staticmethod
    def match(value: str):
        return _is_placeholder(value) or None


PLACEHOLDER = _PlaceholderCompat()


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
    # **按值的形状认**：前缀是密钥自己带的，改个变量名骗不过去。
    for kind, pattern in TOKEN_SHAPES:
        for match in pattern.finditer(text):
            value = match.group(0)
            if PLACEHOLDER.match(value):
                continue
            hits.append({"file": name, "kind": kind,
                         "line_no": text[:match.start()].count("\n") + 1,
                         "value_len": len(value)})
    # **按名字认**：形状认不出的自定义令牌（Obsidian REST、各家 API Key）
    # 只能从「这一行在给一个叫 …TOKEN/SECRET/ACCESS_KEY 的东西赋值」入手。
    for match in SECRET_ENV_NAMES.finditer(text):
        value = match.group(1)
        if PLACEHOLDER.match(value):
            continue
        # 指向文件的配置不是密钥本身：`..._TOKEN_FILE=/run/secrets/x` 要放过。
        if "/" in value or value.endswith("_FILE"):
            continue
        hits.append({"file": name, "kind": "secret_shaped_assignment",
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
        # **只看新增的行。**
        #
        # diff 里既有 `+`（要加进去的）也有 `-`（要删掉的）。整段丢给 scan_text，
        # 那些**正在被删掉的**密钥也会被报成命中——于是这道门会**拦住你清理密钥**：
        # 越想把它删干净，它越不让你提交。2026-08-05 就是这么撞上的：
        # 把判据里的样例改成运行时拼装（正是为了不留字面量），暂存后一扫，
        # 报的全是那几行**被删掉的**旧样例。
        #
        # 行首的 `+++` 是文件头，不是内容，一起排掉。
        added = "\n".join(
            line[1:] for line in diff.splitlines()
            if line.startswith("+") and not line.startswith("+++")
        )
        hits += scan_text(" ".join(argv), added)

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
        shown = hits[:20]
        for hit in shown:
            print(f"   {hit['file']}:{hit['line_no']} {hit['kind']} 值长 {hit['value_len']}", file=sys.stderr)
        # 总数上面已经报了，但**不说这张单子是截断的，读的人会以为就这些**。
        # 这是查明文凭据的那道门，少列一条就可能少堵一个泄漏点。
        if len(hits) > len(shown):
            print(f"   …… 还有 {len(hits) - len(shown)} 处没列出来"
                  f"（只显示前 {len(shown)} 条；完整清单用 --json 取）", file=sys.stderr)
        return 1
    print(f"干净：扫了 {scanned} 个文件 + {diff_scanned} 份 diff，0 处命中")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
