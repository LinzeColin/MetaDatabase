#!/usr/bin/env python3
"""改版本号——**一条命令改完全部承重位**（v0.0.0.7 / G5）。

## 为什么不能手改

版本号散在**十二个承重位**上（见下面的 SITES），而在这个脚本出现之前，
`check_the_stated_version_is_the_real_one.py` 只盯着其中四个。
剩下八个全靠手改——其中三个是 2026-08-06 升 0.0.0.8 那天
**被三条不同的测试逐个撞出来的**，不是想出来的。手改的失败方式很具体，不是"漏了不好看"：

    VERSION 忘了改  →  deploy_to_production.sh 用它拼镜像 tag
                        （social-archive/core:${VERSION}），
                        而 compose.yaml 里 pin 的是另一个 tag
                        →  **部署起来的不是刚构建的那个镜像**

    manifest.json 忘了改  →  Owner 装的插件自报旧版本，
                        安装页拿它和 /health 比，比出"需要更新"，
                        而他更新完还是那个数 —— **无限来回弹**

    runtime-config.json 忘了改  →  插件里显示的版本和它自己的 manifest 不一致

这台机器上已经因为手改版本位出过两次错（两次都是漏了位）。
**重复三次以上的机械动作，先搜有没有现成脚本；没有就写一个。** 这就是那个脚本。

## 承重位 vs 历史引述

只改**承重位**：那些「当前版本是多少」的声明。
**不碰历史引述**——`.env.example` 与 `API_EDGE_POLICY.md` 的注释里那些
「（v0.0.0.7 / T03）」说的是"这件事发生在哪一版"，改了就变成假话。
判断方法很简单：把它改掉会让某个陈述从真变假的，就是历史引述。

## 用法

    python3 scripts/bump_version.py 0.0.0.8          # 只看会改哪些
    python3 scripts/bump_version.py 0.0.0.8 --apply  # 真改
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

# (文件, 找旧值的正则, 换成什么, 这地方为什么承重)
# 正则里的 {old} 会被旧版本号替换。
SITES: list[tuple[str, str, str, str]] = [
    ("pyproject.toml", r'(?m)^version\s*=\s*"{old}"', 'version = "{new}"',
     "**真源**。别处都跟它比"),
    ("VERSION", r"^{old}\s*$", "{new}\n",
     "部署脚本拿它拼镜像 tag；不改就会部署到另一个 tag 上去"),
    ("src/social_archive/__init__.py", r'(?m)^__version__\s*=\s*"{old}"',
     '__version__ = "{new}"', "包自己报的版本；上报、日志、诊断里都带着它"),
    ("apps/browser-extension/manifest.json", r'"version"\s*:\s*"{old}"',
     '"version": "{new}"',
     "**Owner 装的那个扩展报的版本**；安装页拿它和 /health 比，"
     "不改会让他陷在「去更新→已是最新→去更新」的循环里"),
    ("apps/browser-extension/runtime-config.json", r'"version"\s*:\s*"{old}"',
     '"version": "{new}"', "插件界面上显示的版本"),
    ("compose.yaml", r"image:\s*social-archive/core:{old}",
     "image: social-archive/core:{new}", "生产跑的镜像 tag（两处）"),
    ("compose.yaml", r"image:\s*social-archive/cli-tools:{old}",
     "image: social-archive/cli-tools:{new}", "sidecar 镜像 tag"),
    ("apps/obsidian-plugin/manifest.json", r'"version"\s*:\s*"{old}"',
     '"version": "{new}"',
     "Obsidian 插件报的版本；判据要求它和主版本一致"),
    ("apps/pwa/app.js", r'const PRODUCT_VERSION = "{old}"',
     'const PRODUCT_VERSION = "{new}"',
     "**资料库页面判断插件兼容性的那个数**（`compatible: version === PRODUCT_VERSION`）。"
     "它不跟着升，资料库会把刚更新好的插件判成不兼容——"
     "而 Owner 看到的就是「去更新」，更新完还是「去更新」"),
    ("README.md", r"(?m)^#\s+Social Archive v{old}", "# Social Archive v{new}",
     "仓库门面第一行"),
    ("AGENTS.md", r"(?m)^-\s*版本：`v{old}`", "- 版本：`v{new}`",
     "**接手的 agent 读的那一份**——它说错，后面每个人都被告知错的版本"),
    (".env.example", r"SocialArchive/{old}", "SocialArchive/{new}",
     "Reddit 请求的 User-Agent"),
]


def _truth() -> str:
    text = (ROOT / "pyproject.toml").read_text(encoding="utf-8")
    found = re.search(r'(?m)^version\s*=\s*"([0-9.]+)"', text)
    if not found:
        raise SystemExit("pyproject.toml 里找不到版本声明——真源坏了，不敢往下走")
    return found.group(1)


def main() -> int:
    parser = argparse.ArgumentParser(description="一条命令改完所有承重的版本位")
    parser.add_argument("new_version")
    parser.add_argument("--apply", action="store_true", help="真改；不给就只看")
    args = parser.parse_args()

    if not re.fullmatch(r"\d+(\.\d+){1,3}", args.new_version):
        print(json.dumps({"status": "FAIL", "error_code": "VERSION_SHAPE",
                          "message_zh": f"{args.new_version!r} 不像一个版本号"},
                         ensure_ascii=False))
        return 2
    old = _truth()
    if old == args.new_version:
        print(json.dumps({"status": "FAIL", "error_code": "SAME_VERSION",
                          "message_zh": f"当前就是 {old}，没什么可改的"}, ensure_ascii=False))
        return 2

    changes: list[dict] = []
    problems: list[str] = []
    for name, pattern, replacement, why in SITES:
        path = ROOT / name
        if not path.is_file():
            problems.append(f"{name} 不在——它本该声明版本（{why}）")
            continue
        text = path.read_text(encoding="utf-8")
        compiled = re.compile(pattern.replace("{old}", re.escape(old)))
        hits = compiled.findall(text)
        if not hits:
            # **找不到 = 失败，不是跳过。** 一个承重位悄悄没被改到，
            # 正是这个脚本存在的理由。
            problems.append(f"{name} 里找不到 {old} 的那一处（{why}）——"
                            "要么它已经漂了，要么这条规则过期了")
            continue
        updated = compiled.sub(replacement.replace("{new}", args.new_version), text)
        changes.append({"file": name, "occurrences": len(hits), "why": why})
        if args.apply:
            path.write_text(updated, encoding="utf-8")

    report = {
        "status": "PASS" if not problems else "FAIL",
        "applied": args.apply,
        "from": old,
        "to": args.new_version,
        "sites_changed": changes,
        "total_occurrences": sum(c["occurrences"] for c in changes),
        "problems": problems,
        "left_alone": ("`.env.example` 与 deploy/cloudflare/API_EDGE_POLICY.md 注释里的"
                       "「（v0.0.0.7 / Txx）」是**历史引述**，说的是这件事发生在哪一版，"
                       "改了就变成假话——故意不动。"),
        "next": ("改完跑一次 `python3 scripts/check_the_stated_version_is_the_real_one.py`，"
                 "再把 CHANGELOG 补上这一版。"),
    }
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if not problems else 4


if __name__ == "__main__":
    sys.exit(main())
