#!/usr/bin/env python3
r"""一个版本号只许对应一份插件（2026-08-11）。

## 这一条是从今天的账里翻出来的

VERSION 停在 `0.0.0.41` 的那段时间里，**真部署了 11 次**（14:26 → 22:01），
CHANGELOG 靠往版本号后面加 `+` 排了 17 节。

这次没出事——查过 `apps/browser-extension/` 在那段时间**一个提交都没有**，
所以他装的那份和后来发的那份是同一堆字节。**但那是运气，不是判据。**
这个仓已经记下过它出事的样子：一天发 6 个不同的扩展包全标 `v0.0.0.22`，
而产品判断「你装的是旧版」**只比版本号字符串**——
于是判据全绿、生产回读全绿，而当天所有修复都到不了他手上。

## 判据

**版本号最后一次改动之后，`apps/browser-extension/` 不许再变**——
除非这次改动里版本号也在跟着变（升版本身会写 manifest.json 和 runtime-config.json，
那两处正是版本号的承重位；它们跟着版本一起进同一个提交，不是缺陷）。

要改插件？先升版。它不拦重复部署（同一版发两次是正常的：改的是服务端），
只拦「插件的字节变了而版本号没变」这一种。

## 为什么不用账本

第一版想写一个 `版本 → 包哈希` 的文件，写完发现它得在部署过程中落盘，
而那正是部署第 0 步注释里记着的坑：**这一次部署会把下一次挡在「工作树干净」外面**。
从 git 现算就不需要任何状态：版本号是哪个提交定的、那之后插件动没动过，
`git` 自己全知道。
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from social_archive.git_env import clean_git_env  # noqa: E402

# 进他那个 zip 的东西。**改这一行之前先想清楚**：漏一个目录，
# 那个目录里的改动就能悄悄换掉他装的插件而版本号不动。
WATCHED = ("apps/browser-extension",)


def _git(*args: str) -> str:
    done = subprocess.run(["git", *args], cwd=ROOT, env=clean_git_env(),
                          capture_output=True, text=True, check=False)
    if done.returncode != 0:
        raise RuntimeError(f"git {' '.join(args)} 失败：{done.stderr.strip()[:200]}")
    return done.stdout.strip()


def main() -> int:
    parser = argparse.ArgumentParser(description="一个版本号只许对应一份插件")
    parser.add_argument("--brief", action="store_true")
    args = parser.parse_args()

    version = (ROOT / "VERSION").read_text(encoding="utf-8").strip()
    bump = _git("log", "-1", "--format=%H %ad", "--date=format:%m-%d %H:%M", "--", "VERSION")
    if not bump:
        print(json.dumps({"status": "FAIL", "error_code": "NO_VERSION_HISTORY",
                          "message_zh": "VERSION 没有任何提交记录——这条判据没有参照物，"
                                        "**这不是通过**"}, ensure_ascii=False, indent=2))
        return 4
    commit = bump.split()[0]

    # **比到工作树，不是比到 HEAD。** 发布门在提交之前跑：改动那时还没进 HEAD，
    # 用 `commit..HEAD` 的话它会在**下一次**提交才红——那时插件已经发出去了。
    changed = [line for line in
               _git("diff", "--name-only", commit, "--", *WATCHED).splitlines()
               if line.strip()]
    # 空扫必须说出来：如果这几个目录在 HEAD 里根本不存在，上面永远是空的，
    # 这道门就成了恒绿的摆设（`a-red-that-can-never-turn-green-is-not-a-signal` 的反面）。
    tracked = [line for line in _git("ls-files", "--", *WATCHED).splitlines() if line.strip()]

    # **升版本身会改插件**——`bump_version.py` 把版本号写进 manifest.json 和
    # runtime-config.json（13 个承重位里的两个）。所以「插件变了」这件事，
    # 只有在**版本号没跟着变**的时候才是缺陷。
    #
    # 这一条是这道门自己第一次跑就抓到的：我刚升完 0.0.0.43，它当场判我红，
    # 而那两个改动恰恰是升版写进去的。判据切在了一个它自己会踩的位置上。
    bumping = bool(_git("diff", "--name-only", commit, "--", "VERSION").strip())

    problems: list[str] = []
    if not tracked:
        problems.append(f"{WATCHED} 底下一个受控文件都没有——这道门的射程失效了，**不是通过**")
    if changed and not bumping:
        problems.append(
            f"版本号还是 {version}（{bump.split(maxsplit=1)[1]} 定的），"
            f"而插件从那之后改了 {len(changed)} 个文件：{changed[:5]}——"
            "**他那边的更新提示只比版本号字符串**，比不出这次改动，"
            "于是他装着旧的那份，而所有判据都是绿的。先升版再部署。")

    report = {
        "status": "FAIL" if problems else "PASS",
        "version": version,
        "version_set_by": bump,
        "watched": list(WATCHED),
        "tracked_files": len(tracked),
        "changed_since_bump": changed,
        "version_being_bumped_right_now": bumping,
        "problems": problems,
        "what_this_does_not_prove":
            "不保证插件是对的，只保证**它变了的时候版本号跟着变**。"
            "它也不拦同一版重复部署——改服务端而不动插件时那是正常的。",
    }
    out = ROOT / "evidence/G5/ONE_VERSION_ONE_PACKAGE.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    if args.brief:
        print(report["status"] if not problems else
              "FAIL：" + problems[0])
    else:
        print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if not problems else 4


if __name__ == "__main__":
    sys.exit(main())
