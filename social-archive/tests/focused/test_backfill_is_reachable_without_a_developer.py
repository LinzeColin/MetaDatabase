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
