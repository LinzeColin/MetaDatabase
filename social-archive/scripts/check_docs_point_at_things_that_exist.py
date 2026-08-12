#!/usr/bin/env python3
"""文档让人跑的东西，必须真的存在（v0.0.0.7 / T18）。

## 为什么

文档里最要命的一句，是**出事那天才会被人读到的那一句**。运维手册第 14 行写着

    bash scripts/restore.sh --dry-run <恢复点>

那一天再发现这个脚本不在，是最坏的时机——而且那时候没人有心情去翻仓库。

这道门只做一件很小的事：把文档里出现的 `scripts/xxx` 逐个去磁盘上找一下。

## 它扫哪些地方

**整个仓的 md**，只排掉不是我们写的目录（node_modules/.venv/dist…）。

范围这件事漏过两次，两次都是同一天：先只扫 `docs/`，直到我往
`evidence/HANDOFF_v0007.md` 里写了一段「要加新平台就跑这个」——
**接手的人第一份读的就是交接**，而它整个在门外。补上 evidence/ 之后，
一数才发现仓根还有一份 `HANDOFF.md`，19 处引用，同样在门外。

**列目录的白名单每补一次，就等下一次漏。** 所以反过来：全扫，只排除
明确不是我们写的。

## 只认仓根下的 `scripts/xxx`

`HANDOFF.md` 里有这么一句：

    python ../social-archive-taskpack-compat/v0.0.0.4/scripts/validate_compatibility.py

原来的正则见 `scripts/` 就算数，把这条**隔壁仓的路径**截出尾巴，报成
「让人跑一个不存在的脚本」。本仓当然没有那个文件——那不是缺陷，是指错原因。

## 「已删 `scripts/xxx`」是记录，不是指令

那种句子必须放行，否则每一条删除记录都会把这道门点红。判别按**行**做，
不按整份文档：交接不是作废文档，把它整份开白名单，等于对最要紧的那一份闭眼。

两处细节都是被真语料逼出来的：

· **放行看两行**（本行 + 上一行）。散文会折行，交接里「已删」在上一行、
  `stop_workers.sh` 折到了下一行，只看本行就会误报。
· **指控只看本行**。「说已删而它还在」这一侧要是也看两行，
  「已删 A。/ 现在改用 B。」里的 B 就会被上一行牵连——又是一次指错原因。

原来这里还有一张**按整份文档**开的白名单，为 `docs/DOMESTIC_WORKERS_ZH.md`
一份而设。加上按行判之后它变成了纯装饰：那份文档的两处引用，一处落在
「不要照着」那一行、一处靠折行窗口盖住，白名单拿掉什么都不会发生——
守它的判据当场把这件事点红了。装饰性的保护比没有保护更坏，它让人以为
查过了，所以已删掉。

## 代码块里那种「只有作者机器上才有」的路径

原来这里写着一句边界：「只查 `scripts/`，别的路径没人会照着敲」。
**同一天就被我自己推翻了**——我往交接里写了这段：

    unzip -q -o dist/social-archive-extension.zip -d /tmp/sa-wire

而 `dist/` 在 `.gitignore` 第 41 行。照着敲的人第一步就卡住。

这类漏**看不出来**：我这台机器上那个文件就在那儿，我怎么读都读不出问题。
正因为肉眼看不出来，才值得让机器每次都问一遍。判据只问 `.gitignore`，
**不问这个文件此刻在不在**——「在不在」恰恰是那个骗人的信号。

同一个代码块里先有一条造它的命令就算数（现在那段第一行是
`python3 scripts/build_extension_package.py`）。

## 边界

· `scripts/` 那一类查得最细，因为它最常被照着敲。
· 代码块里只查**被 .gitignore 挡住的**路径，不查所有路径——
  实测所有路径那种查法 5 处命中全是误报（`L0/L1`、`origin/main`
  这类带斜杠的散文和 git 引用），而 gitignore 那种查法 1 命中 0 误报。
· 只查存在，不查内容对不对——那是另一件事，也更难自动化。
"""

from __future__ import annotations

import os
import re
import subprocess
import sys
from pathlib import Path

# --root 让判据能在一份**临时副本**上验这个检查器，而不必去改仓里的真文档。
# 一个会写仓里文件的判据是不可重入的：跑到一半被打断，就把一个改坏的文档
# 留在工作树里；两次同时跑还会互相踩。
_ARGUMENT_ROOT = None
if "--root" in sys.argv:
    _position = sys.argv.index("--root")
    if _position + 1 < len(sys.argv):
        _ARGUMENT_ROOT = sys.argv[_position + 1]

ROOT = Path(_ARGUMENT_ROOT).resolve() if _ARGUMENT_ROOT else Path(__file__).resolve().parents[1]

# **只认仓根下的 `scripts/xxx`。**
#
# 原来的正则在任何地方见到 `scripts/` 就算数，于是 HANDOFF.md 里这一句
#     python ../social-archive-taskpack-compat/v0.0.0.4/scripts/validate_compatibility.py
# 被截出尾巴 `scripts/validate_compatibility.py`，报成「让人跑一个不存在的脚本」。
# **那是隔壁仓的路径**，本仓当然没有——又一次指错原因。
# 前面不许再跟路径分隔符（`/` 或 `.`），外部路径就不会被截尾巴。
SCRIPT_REFERENCE = re.compile(r"(?<![A-Za-z0-9_./-])scripts/[A-Za-z0-9_.-]+")

# **交接也是文档，而且是最可能被照着敲的那一份。**
#
# 这道门原来只扫 docs/。2026-08-05 我往 evidence/HANDOFF_v0007.md 里写了
# 一段「要加新平台就跑这个」，写完才想起来：接手的人第一份读的就是交接，
# 而它整个在这道门的视野之外——这道门存在的理由正好是挡这件事。
# 扫**整个仓**的 md，而不是列几个目录。
# 列目录这件事已经漏过两次：先漏了 evidence/（交接在里面），
# 补上之后又发现仓根的 HANDOFF.md 也在外面。白名单式的范围
# 每补一次就等下一次漏——不如反过来：全扫，只排除不是我们写的东西。
NOT_OURS = {".git", "node_modules", ".venv", "dist", "build", "__pycache__", ".pytest_cache"}

# 「已删 `scripts/xxx`」是**记录**，不是让人去跑。按整份文档开白名单太粗：
# 交接不是作废文档，把它整份放行等于对最要紧的那一份闭眼。所以按**行**判。
RECORDS_A_DELETION = ("已删", "已移除", "删掉", "不要照着", "已废弃", "不再")

# 代码块里那种一看就是要复制去敲的路径。
FENCE = "```"
COPY_PASTE_PATH = re.compile(
    r"(?<![A-Za-z0-9_./~-])([a-zA-Z][A-Za-z0-9_.-]*(?:/[A-Za-z0-9_.-]+)+\.[A-Za-z0-9]{1,5})")


# **git 钩子会把 GIT_DIR 之类塞进环境变量，子进程会继承。**
#
# 这道门最常跑的地方就是 pre-commit。在钩子里，`git check-ignore` 会拿着
# 继承来的 GIT_DIR 去问**主仓**，而不是 cwd 指的那个仓——同一条判据
# 单独跑是绿的、在钩子里跑是红的。第一次撞上时它表现为「偶发失败」，
# 而根本不偶发：只在钩子里必错。
#
# 判据要问的是「cwd 这个仓怎么说」，所以把这几个变量摘掉再问。
_LEAKED_BY_GIT_HOOKS = ("GIT_DIR", "GIT_INDEX_FILE", "GIT_WORK_TREE",
                        "GIT_COMMON_DIR", "GIT_PREFIX", "GIT_OBJECT_DIRECTORY")


def _is_gitignored(reference: str, cache: dict[str, bool]) -> bool:
    if reference not in cache:
        environment = {key: value for key, value in os.environ.items()
                       if key not in _LEAKED_BY_GIT_HOOKS}
        cache[reference] = subprocess.run(
            ["git", "check-ignore", "-q", reference], cwd=ROOT, env=environment,
            capture_output=True, check=False).returncode == 0
    return cache[reference]


def main() -> int:
    documents = [path for path in sorted(ROOT.rglob("*.md"))
                 if not (set(path.relative_to(ROOT).parts) & NOT_OURS)]
    if not documents:
        print("一份 md 都没扫到，跳过——**这不是通过**。")
        return 0

    missing: list[str] = []
    stale_records: list[str] = []
    only_on_the_authors_machine: list[str] = []
    ignored_checked = 0
    ignored_cache: dict[str, bool] = {}
    checked = 0
    for document in documents:
        lines = document.read_text(encoding="utf-8").splitlines()
        in_fence = False
        block_start = 0
        for number, line in enumerate(lines, 1):
            if line.strip().startswith(FENCE):
                in_fence = not in_fence
                block_start = number if in_fence else 0
                continue
            if in_fence:
                # **`dist/…` 在我这台机器上有，克隆下来的人没有。**
                #
                # 2026-08-05 我往交接里写了「跑这个演练」，第一行是
                #     unzip -q -o dist/social-archive-extension.zip -d /tmp/sa-wire
                # 而 dist/ 在 .gitignore 第 41 行。照着敲的人第一步就卡住。
                #
                # 这类漏我**看不出来**：我的机器上那个文件就在那儿。
                # 正因为看不出来，才值得让机器每次都问一遍。
                # 同一个代码块里先有一条造它的命令（scripts/…）就算数。
                builds_it = any("scripts/" in earlier
                                for earlier in lines[block_start:number - 1])
                for reference in sorted(set(COPY_PASTE_PATH.findall(line))):
                    if reference.startswith(("http", "www.")):
                        continue
                    # 判据只问 .gitignore，**不问这个文件此刻在不在**——
                    # 它在我这儿在，正是这类漏看不出来的原因。
                    if not _is_gitignored(reference, ignored_cache):
                        continue
                    ignored_checked += 1
                    if builds_it:
                        continue
                    only_on_the_authors_machine.append(
                        f"{document.relative_to(ROOT)}:{number} 让人用 {reference}，"
                        "而它被 .gitignore 挡着——克隆下来没有这个文件，"
                        "同一个代码块里也没有一条造它的命令")
            # **看这一行和它上面那一行。**
            #
            # 只看本行时，交接里这句被判成「让人跑一个不存在的脚本」：
            #     已删 `compose.workers.yaml`（…）+ `scripts/start_workers.sh`
            #     + `scripts/stop_workers.sh`。原先 6 个测试**反转**成了…
            # 「已删」在上一行，stop_workers 折到了下一行——散文本来就会折行。
            #
            # 取两行而不是整段：整段里可能前半句说「已删 A」、后半句说「去跑 B」，
            # 那样 B 就被前半句挡住了。两行把这个风险摁在一个折行之内。
            #
            # 而且**两行只用在放行那一侧**。指控那一侧（「说已删，它却还在」）
            # 仍然只看本行：否则
            #     已删 scripts/foo.sh。
            #     现在改用 scripts/final_verify.py。
            # 第二行会被上一行的「已删」牵连，报成「说它已删而它还在」——
            # 又是一次指错原因。**放宽用宽窗，指控用窄窗。**
            window = line + ("\n" + lines[number - 2] if number >= 2 else "")
            is_record = any(word in window for word in RECORDS_A_DELETION)
            accuses_deletion = any(word in line for word in RECORDS_A_DELETION)
            for reference in sorted(set(SCRIPT_REFERENCE.findall(line))):
                checked += 1
                here = f"{document.relative_to(ROOT)}:{number}"
                if (ROOT / reference).exists():
                    # 反过来也值得一说：写着「已删」而它还在，说明删漏了，
                    # 或者这句记录是错的。两种都会让人相信一个不成立的事实。
                    if accuses_deletion and "不要照着" not in line:
                        stale_records.append(f"{here} 说 {reference} 已删，而它还在")
                    continue
                if is_record:
                    continue
                missing.append(f"{here} 让人跑 {reference}，而它不在")

    print(f"扫了全仓 {len(documents)} 份文档，{checked} 处 scripts/ 引用、"
          f"{ignored_checked} 处代码块里被 .gitignore 挡着的路径")
    if missing or stale_records or only_on_the_authors_machine:
        for item in missing:
            print(f"  **不合格**：{item}")
        for item in stale_records:
            print(f"  **记录与事实不符**：{item}")
        for item in only_on_the_authors_machine:
            print(f"  **只有作者机器上有**：{item}")
        print("  ↳ 文档里最要命的一句，是出事那天才会被人读到的那一句。")
        return 1
    print("文档让人跑的每一个脚本都在；写着「已删」的也确实不在了。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
