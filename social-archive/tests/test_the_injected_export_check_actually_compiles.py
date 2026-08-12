r"""送进容器那段脚本，得先能编译、且判得对（2026-08-12）。

## 为什么补这一道

`check_his_markdown_export_still_works.py` 把 `classify` 的源码抠出来、拼进一段
模板，再 `docker exec python3 -c` 送进生产容器。**本仓这一侧从来没有编译过它**——
1936 条测试全绿，而我刚把 `title_repair.py` 的文本一起注进去时，它带着
`from __future__ import annotations` 落在了模板中间：

    SyntaxError: from __future__ imports must occur at the beginning of the file

整段在容器里当场崩。抓到它的不是判据，是我手跑了一次。

所以这道测试做两件事，**都不连生产**：

1. 把注入后的那段真的 `compile()` 一遍——语法错在这里就红；
2. 把注入出来的 `classify` 拿真标题喂一遍——判据被注歪了也在这里红。
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CHECKER = ROOT / "scripts" / "check_his_markdown_export_still_works.py"


def _load():
    sys.path.insert(0, str(ROOT / "src"))
    spec = importlib.util.spec_from_file_location("export_checker_under_test", CHECKER)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def test_the_script_sent_into_the_container_compiles() -> None:
    compile(_load()._inside(), "<sent-into-the-container>", "exec")


def test_the_injected_classify_judges_real_titles_correctly() -> None:
    """注进去的那份判据，拿生产原文喂一遍——**只用标准库**，和容器里一样。

    掐掉模板里连生产的部分，只执行到 `classify` 定义为止。
    """
    injected = _load()._inside()
    head = injected.split("port = os.environ")[0].replace(
        "import io, json, os, urllib.request, zipfile", "import re")
    namespace: dict = {}
    exec(compile(head, "<injected>", "exec"), namespace)          # noqa: S102
    classify = namespace["classify"]

    for title, expected in (
            ("26.1万谁敢点开这个bgm谁敢点开这个bgm", 1),
            # 前一遍结尾多一个空格——老判据「正好对半分」在这条上永远算不出重复。
            ("2.2万厂二代卖掉父亲的公司，未必是一代不如一代 "
             "厂二代卖掉父亲的公司，未必是一代不如一代", 1),
            # 「14万亿」是他要说的话，不许动。
            ("14万亿巨额放水+50万亿存款到期，微观体感寒冷，钱到底去哪了？", 0),
            # 本来就重复两遍的正当文案，前面没有那截计数 → 不许动。
            ("咕咕嘎嘎咕咕嘎嘎", 0)):
        assert classify(f"# {title}\n")["doubled_caption"] == expected, title


def test_the_shared_rule_really_travelled_with_it() -> None:
    """防空转：判据必须是**注进去的**，不是容器里恰好有同名的东西。"""
    injected = _load()._inside()
    assert "def undouble_title" in injected
    assert "_REPEAT_MUST_COVER" in injected
    assert "from social_archive" not in injected          # 容器里不许靠 import
