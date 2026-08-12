"""起 git 子进程时该用的环境（2026-08-07）。

git 钩子会把 `GIT_DIR` / `GIT_INDEX_FILE` / `GIT_WORK_TREE` 塞进环境。
子进程继承之后**会去问那个仓，而不是 `cwd=` 指的这个**——cwd 压不过 GIT_DIR。

2026-08-07 一天之内踩了三次，症状一模一样：**单独跑是绿的，pre-commit 里红**。
而最坏的一种不是红，是**静悄悄读了另一个仓**——那时候数是出得来的，只是错的。
`scan_plaintext_credentials.py` 就是这一种：它靠 `git ls-files` 列要扫的文件，
环境脏了它会去列别的仓，然后报「泄漏项=0」。

**做成函数而不是常量**：常量在模块加载那一刻定死，而环境是会中途变的
（一个进程里先干净后脏，或者反过来）。每次调用现算才对得上。

`scripts/check_git_calls_cannot_be_hijacked_by_hooks.py` 拦着全仓：
起 git 的调用必须显式写 `env=`——洗过的也好，`env=None`（明确要继承）也好，
重点是**有人做过这个决定**。
"""

from __future__ import annotations

import os

LEAKED_BY_GIT_HOOKS = ("GIT_DIR", "GIT_INDEX_FILE", "GIT_WORK_TREE",
                       "GIT_COMMON_DIR", "GIT_PREFIX", "GIT_OBJECT_DIRECTORY")


def clean_git_env() -> dict[str, str]:
    """当前环境去掉钩子塞的那几个变量。**每次现算。**"""
    return {k: v for k, v in os.environ.items() if k not in LEAKED_BY_GIT_HOOKS}
