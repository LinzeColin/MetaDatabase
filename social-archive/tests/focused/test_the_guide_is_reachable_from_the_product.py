"""使用说明得是他打得开的一页，不是我记得的一段话（2026-08-07）。

验收条件第 2 条要的是**「一份普通人照着做得完的使用说明」**。
`docs/使用说明.md` 一直照着这条写，也有判据核着它每一步在产品里真的存在——

**但他打不开它。** 它躺在 git 工作树里，产品里没有任何入口指向它
（`index.html` 里那个 `help` 只是个 CSS 类名）。于是每次他要装、要连，
都是我在聊天里现敲一遍步骤。**那不叫使用说明，那叫我记得。**

现在：`scripts/build_guide_page.py` 把它转成 `apps/pwa/guide.html`，
服务端 `/guide` 供它，资料库顶栏和安装页各一个入口，
发布门用 `--check` 挡住「改了 md 忘了重生成」。
"""

from __future__ import annotations

import importlib
import importlib.util
import re
import sys
from pathlib import Path

from fastapi.testclient import TestClient

ROOT = Path(__file__).resolve().parents[2]
GUIDE_MD = ROOT / "docs/使用说明.md"
GUIDE_HTML = ROOT / "apps/pwa/guide.html"

_spec = importlib.util.spec_from_file_location(
    "_guide_builder", ROOT / "scripts/build_guide_page.py")
_builder = importlib.util.module_from_spec(_spec)
sys.modules["_guide_builder"] = _builder
_spec.loader.exec_module(_builder)


def _client(tmp_path, monkeypatch):
    root = tmp_path / "data"
    pwa = tmp_path / "pwa"
    pwa.mkdir()
    (pwa / "index.html").write_text("ok", encoding="utf-8")
    (pwa / "guide.html").write_text(
        GUIDE_HTML.read_text(encoding="utf-8"), encoding="utf-8")
    for key, value in {
        "SOCIAL_ARCHIVE_DATA_ROOT": root,
        "SOCIAL_ARCHIVE_RUNTIME_DB": root / "db.sqlite",
        "SOCIAL_ARCHIVE_STAGING_ROOT": root / "staging",
        "SOCIAL_ARCHIVE_PRIVATE_DATABASE_ROOT": root / "private",
        "SOCIAL_ARCHIVE_WATCH_ROOT": root / "import",
        "SOCIAL_ARCHIVE_PWA_ROOT": pwa,
    }.items():
        monkeypatch.setenv(key, str(value))
    import social_archive.api as api
    importlib.reload(api)
    return TestClient(api.app)


def test_the_guide_has_a_route(tmp_path, monkeypatch) -> None:
    response = _client(tmp_path, monkeypatch).get("/guide")
    assert response.status_code == 200
    assert "使用说明" in response.text


def test_both_pages_he_lands_on_link_to_it() -> None:
    """**入口要在他会到的地方。** 只有路由等于只有我知道。"""
    for relative in ("apps/pwa/index.html", "apps/pwa/extension-install.html"):
        text = (ROOT / relative).read_text(encoding="utf-8")
        assert 'href="/guide"' in text, f"{relative} 里没有通往使用说明的入口"


def test_no_markdown_leaks_into_what_he_reads() -> None:
    """**没转干净的 markdown 会原样印在他眼前。**

    这个仓已经栽过两次：`**` 直接进了 textContent，界面上就是两个星号。
    这里逐类查生成出来的正文——不是查"生成成功了没有"。
    """
    body = GUIDE_HTML.read_text(encoding="utf-8").split("</style>", 1)[1]
    for name, pattern in (
        ("未转的 **", r"\*\*"),
        ("未转的表格行", r"^\s*\|"),
        ("未转的反引号", r"`"),
        ("未转的链接 [x](y)", r"\[[^\]]+\]\([^)]+\)"),
        ("未转的标题 #", r"^#{1,6}\s"),
    ):
        hits = re.findall(pattern, body, re.M)
        assert not hits, f"{name}：{hits[:3]}"


def test_every_bullet_survived_the_conversion() -> None:
    """**「没有残留」不等于「转对了」。** 数一遍，别只看有没有脏字符。"""
    lines = GUIDE_MD.read_text(encoding="utf-8").splitlines()
    expected = len([l for l in lines if re.match(r"^\s*[-*·]\s+\S", l)]) \
        + len([l for l in lines if re.match(r"^\s*\d+[.)]\s+\S", l)])
    got = len(re.findall("<li>", GUIDE_HTML.read_text(encoding="utf-8")))
    assert got == expected, f"md 里 {expected} 条，页面上 {got} 条"


def test_it_refuses_to_render_what_it_cannot_parse() -> None:
    """**看不懂就报错，绝不糊过去。**

    「大概能转」是这里最危险的一种：判不出来的行会**看起来像正文**地印出去。
    所以拿一段它不认识的写法喂它，必须被点名，而不是被当成段落。
    """
    _, unknown = _builder.convert("# 标题\n\n+ 这是它不认识的项目符号写法\n")
    assert unknown, "它把不认识的写法当正文印出去了"
    assert "1" in unknown[0] or "3" in unknown[0], f"没给出行号：{unknown}"


def test_a_normal_paragraph_is_not_falsely_rejected() -> None:
    """**正例必须是绿的。** 一个见什么都说看不懂的转换器同样没法用。"""
    body, unknown = _builder.convert("# 标题\n\n这是一段普通的话。\n\n- 一条\n")
    assert not unknown, unknown
    assert "<h1>标题</h1>" in body and "<li>一条</li>" in body


def test_the_generated_page_is_in_sync_with_the_markdown() -> None:
    """改了 md 忘了重生成 → 他看到的是上一版。发布门里也有这一条。"""
    page, unknown = _builder.build()
    assert not unknown, unknown
    assert GUIDE_HTML.read_text(encoding="utf-8") == page, (
        "apps/pwa/guide.html 和使用说明对不上——跑一次 scripts/build_guide_page.py")
