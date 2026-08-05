"""少送了的那些，他自己就能补上（v0.0.0.7 / T11）。

2026-08-05 实测：Owner 连上 GitHub 与 Obsidian 之后，两边各只有 1 / 193 条。
不是坏了——投递只在**新内容进来时**发生，他后来才连上，此前入库的不会自己
追上去。而在他那一侧，「我连上了，我的档案应该都在那儿」是最自然的期待。

在这个按钮之前，把 192 条补上去的唯一办法是**在界面上逐条点 192 次**，
或者**让开发者登进服务器敲命令**——两条都不该是他要走的路。
"""

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
APP = ROOT / "apps/pwa/app.js"
API = ROOT / "src/social_archive/api.py"


def test_the_button_only_appears_when_something_is_actually_missing() -> None:
    """**没少送就不要出现。** 按钮本身就是一句话，凭空挂着会让人以为漏了东西。"""
    app = APP.read_text(encoding="utf-8")
    assert "function backfillButton(" in app, "卡片上没有补投按钮"
    body = app.split("function backfillButton(", 1)[1].split("\n  }", 1)[0]
    assert "if (!(missing > 0)" in body, "没少送也会显示按钮"
    assert 'item.state !== "connected"' in body, "还没连上就给补投按钮，点了只会失败"
    assert "content_total" in body and "exported_count" in body, (
        "缺多少不是从覆盖数算出来的——那会和卡片上那行「已送到 N / M」对不上"
    )


def test_bulk_writes_to_an_external_account_ask_first() -> None:
    """192 条不是一次点击该有的默默后果。"""
    app = APP.read_text(encoding="utf-8")
    handler = app.split("async function backfillDestination(", 1)[1].split("\n  }", 1)[0]
    assert "window.confirm" in handler, "批量往外部账号写之前不问一句"
    assert "几分钟" in handler, "没告诉他这要花时间——他会以为卡住了"


def test_the_endpoint_refuses_what_it_should() -> None:
    api = API.read_text(encoding="utf-8")
    block = api.split('@app.post("/v1/destinations/{destination_id}/backfill"', 1)[1].split("\n@app.", 1)[0]
    assert "known_ids()" in block, "不存在的目的地和没授权的目的地被混成一种错"
    assert "is_export_authorized" in block, "没授权也能往那里写"
    assert '"export_destination"' in block, "补投用的不是单条导出那个作业类型"
    assert "排队不等于送到" in block, (
        "接口报完排队数就完了——而覆盖数要等 worker 跑完才会变，"
        "不说清会让人以为点完就齐了"
    )


def test_the_missing_list_comes_from_what_actually_arrived() -> None:
    """判「还差哪些」要看 destination_binding（真的送到了），不是看作业表。

    看作业表会把还在队里的算成已送，于是补投第二次就少投一批。
    """
    db = (ROOT / "src/social_archive/db.py").read_text(encoding="utf-8")
    body = db.split("def content_ids_missing_from_destination(", 1)[1].split("\n    def ", 1)[0]
    assert "destination_binding" in body, "不是从「真的送到了」那张表判的"
    assert "FROM job" not in body, "从作业表判，会把还在队里的算成已送"


def _render(item: dict) -> str:
    """真的把 backfillButton 跑一遍，而不是在源码里找字符串。

    判据只比字符串的话，「条件写反了」这种错一个都抓不到——
    源码里 `if (!(missing > 0))` 和 `if (missing > 0)` 都能通过「含有 missing」
    这类检查。本会话已经在别处栽过：判据绿着，而它验的根本不是那件事。
    """
    import subprocess

    app = APP.read_text(encoding="utf-8")
    body = app.split("function backfillButton(item) {", 1)[1].split("\n  }", 1)[0]
    script = (
        "const escapeHtml = s => String(s).replace(/&/g,'&amp;').replace(/</g,'&lt;');\n"
        "function backfillButton(item) {" + body + "\n}\n"
        f"console.log(backfillButton({json.dumps(item)}));"
    )
    done = subprocess.run(["node", "-e", script], cwd=ROOT, capture_output=True,
                          text=True, check=True)
    return done.stdout.strip()


def test_a_connected_destination_that_is_behind_gets_a_button_with_the_real_number() -> None:
    html = _render({"destination_id": "obsidian", "state": "connected",
                    "content_total": 193, "exported_count": 1})
    assert 'data-backfill-destination="obsidian"' in html
    assert "192" in html, f"按钮上的数字不对：{html}"


def test_a_destination_that_is_already_complete_gets_no_button() -> None:
    html = _render({"destination_id": "github", "state": "connected",
                    "content_total": 193, "exported_count": 193})
    assert html == "", f"已经齐了却还挂着补投按钮：{html}"


def test_a_destination_that_is_not_connected_gets_no_button() -> None:
    """还没连上就给补投按钮，点了只会失败——那是在制造一次注定的失败。"""
    html = _render({"destination_id": "notion", "state": "needs_user_action",
                    "content_total": 193, "exported_count": 0})
    assert html == "", f"没连上却给了补投按钮：{html}"


def test_an_empty_library_gets_no_button() -> None:
    """库里一条都没有时，「把没送过去的 0 条补上」是句废话。"""
    html = _render({"destination_id": "obsidian", "state": "connected",
                    "content_total": 0, "exported_count": 0})
    assert html == "", f"空库也挂了按钮：{html}"
