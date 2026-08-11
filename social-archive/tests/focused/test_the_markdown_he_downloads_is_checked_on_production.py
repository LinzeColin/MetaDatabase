r"""他点「下载全部 Markdown」拿到的那个 zip，有人在生产上验吗（2026-08-11）。

## 这道门为什么在

《使用说明》第二节两条取法，第一步都是同一颗按钮。而在此之前
**没有任何一步在生产上验过它**：单元判据跑在本机 `TestClient` 上，
部署脚本里一次都没出现过 `markdown.zip`。我上一次真去点它是 0.0.0.29，
到补这道门时已经隔了十几版——
`never-verified-the-final-artifact-itself` 那条教训的同一个形状。

第一次真跑就有收获（虽然是我自己的毛病）：

    第一版判据：标题「以互动数开头」→ 生产上 29 个命中
    读清楚之后：真正的缺陷是**后半截和前半截重复**（「2.0万文案文案」），
                而「10万个冷知识」这种正当标题被一起算了进去
    改准之后：**重复的 0 个**，仅仅以数字开头的 92 个（正常内容）

## 这里测的是什么

`classify()` 是**同一份代码**：脚本用 `inspect.getsource` 把它塞进
`docker exec` 送进容器，判据直接 import 它。所以下面这些例子测的
就是生产上真正跑的那段逻辑，不是它的一份手抄。

生产上的那次实测（数字、不含正文）落在 `evidence/G3/HIS_MARKDOWN_EXPORT.json`。
"""

from __future__ import annotations

import importlib.util
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts/check_his_markdown_export_still_works.py"


def _module():
    spec = importlib.util.spec_from_file_location("markdown_export_check", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def _note(title: str, author: str | None = None) -> str:
    line = f'author: "{author}"' if author is not None else "author: null"
    return f'---\nplatform: "douyin"\n{line}\n---\n\n# {title}\n\n原始链接：https://x\n'


def test_a_good_note_is_not_flagged() -> None:
    got = _module().classify(_note("真正的一次性她来了", "雪瑜"))
    assert got == {"empty_heading": 0, "doubled_caption": 0,
                   "starts_with_number": 0, "like_count_author": 0}


def test_an_empty_heading_is_caught() -> None:
    """我在生产上写出过 4 个空标题。"""
    assert _module().classify(_note(""))["empty_heading"] == 1


def test_the_doubled_caption_is_caught() -> None:
    """抖音那种「互动数＋文案＋同一段文案」。"""
    got = _module().classify(_note("2.0万真正的一次性她来了真正的一次性她来了"))
    assert got["doubled_caption"] == 1
    assert got["starts_with_number"] == 1


def test_a_title_that_merely_starts_with_a_number_is_not_a_defect() -> None:
    """**这条是那 29 个假命中的墓志铭。**

    「10万个冷知识」以数字开头，但它不是「互动数＋重复文案」——
    把它算成缺陷，我就会去修一个不存在的问题，或者把他的正当标题改掉。
    """
    got = _module().classify(_note("10万个冷知识第一集讲的是海水为什么是咸的"))
    assert got["doubled_caption"] == 0, "正当标题被当成了缺陷"
    assert got["starts_with_number"] == 1, "参考数也该记上"


def test_a_like_count_in_the_author_field_is_caught() -> None:
    """他那条笔记的 frontmatter 曾经写着 `author: "26.6万"`。"""
    assert _module().classify(_note("随便", "26.6万"))["like_count_author"] == 1
    assert _module().classify(_note("随便", "雪瑜"))["like_count_author"] == 0


def test_the_deploy_actually_runs_this_check() -> None:
    """**没有调用方的判据不算判据。** 它必须每次部署都真去点那颗按钮。"""
    deploy = (ROOT / "scripts/deploy_to_production.sh").read_text(encoding="utf-8")
    name = "check_his_markdown_export_still_works.py"
    assert name in deploy, f"部署脚本没有调用 {name}——那条路又回到没人验的状态"
    step = deploy[deploy.index(name):]
    nxt = step.find('\nstep "')
    step = step[:nxt] if nxt > 0 else step
    assert "fail " in step, "它红了不中止部署，等于没验"
    assert "| tail" not in step and "| head" not in step, "别把成败接进管道"


def test_it_never_prints_the_token_or_any_body() -> None:
    """**只读、只数数。** 这条守的是它自己的边界。"""
    source = SCRIPT.read_text(encoding="utf-8")
    assert 'print(json.dumps(out' in source
    for leak in ('out["titles"]', 'out["sample"]', "print(token", "out[\"token\"]"):
        assert leak not in source, f"它会把不该出来的东西打出来：{leak}"
    assert "token.strip()" not in source.replace("handle.read().strip()", "")
