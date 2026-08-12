r"""把某一类关系从采集范围里去掉，**不许连累已经存下的那些**（2026-08-12）。

## 为什么要有这条

Owner 2026-08-12 定「先停浏览历史，点赞留着」，于是
`PLATFORM_RELATIONS["bilibili"]` 去掉了 `history`。

**那一刻要问的是：他库里已经存着的 70 条历史会怎样？**

同步有一条「消失检测」：完整扫过一轮而某条没再出现，两轮之后就把它关掉。
如果那条检测按**账号**判而不是按**关系类型**判，那么「不再扫 history」
会被读成「history 全都消失了」，他 70 条历史会被一次关光——
一个产品决策把用户的数据删了，而决策本身完全无辜。

## 实测（不是读代码推的）

只扫 `favorite`、`history` 一次都不扫，连跑两轮完整扫描：

    同步前：{favorite: 2 active, history: 3 active}
    两轮后：{favorite: 2 active, history: 3 active}

`apply_complete_scan` 的文档串写着 "Close only the exact scanned relation
scope"，实测和它一致。这条判据把那句话钉住——**它是一句承诺，不是注释**。

## 它不保证什么

只钉「不扫的关系不会被关」。「扫了而没看见的会不会被关」是另一件事，
这里不做断言：我试着用一次合成调用去触发它，没触发，
而**没触发不等于不会触发**——那要走完整条同步链才说得清，不在这条判据的射程里。
"""

from __future__ import annotations

import sys
import tempfile
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

from social_archive.db import RuntimeStore  # noqa: E402
from social_archive.models import CaptureRequest  # noqa: E402


@pytest.fixture()
def store(tmp_path: Path) -> RuntimeStore:
    made = RuntimeStore(tmp_path / "runtime.sqlite3")
    made.initialize()
    made.upsert_source_account(platform="bilibili", external_account_id="him",
                               display_name="B站", auth_method="browser_session",
                               auth_handle_ref=None, connection_state="connected")
    return made


def _save(store: RuntimeStore, relation: str, count: int) -> None:
    for index in range(count):
        store.capture(CaptureRequest(
            platform="bilibili",
            url=f"https://www.bilibili.com/video/BV{relation}{index}/",
            relation_type=relation, external_content_id=f"BV{relation}{index}",
            source_account_id="him", title=f"标题 {relation}{index}"))


def _active(store: RuntimeStore, relation: str) -> int:
    with store.connection() as con:
        return con.execute(
            "select count(*) from user_relation where relation_type=? and status='active'",
            (relation,)).fetchone()[0]


def test_an_unscanned_relation_is_never_closed(store: RuntimeStore) -> None:
    """他那 70 条浏览历史就是这个格子里的东西。"""
    _save(store, "history", 3)
    _save(store, "favorite", 2)
    assert _active(store, "history") == 3

    # 只扫 favorite，history 一次都不扫——正是去掉 history 之后每次同步的样子。
    for _ in range(2):
        store.apply_complete_scan("bilibili", ["rel_nonexistent"],
                                  relation_type="favorite", collection_key=None,
                                  source_account_id="him")

    assert _active(store, "history") == 3, (
        "**不再采集某一类关系，把已经存下的那一类关掉了**——"
        "一个产品决策不该删掉用户已有的东西")


def test_bilibili_no_longer_collects_history(store: RuntimeStore) -> None:
    """裁定本身也钉一下，免得哪天被无声改回来。

    只断言 history 不在里面、而 favorite 还在——**不写死整个列表**，
    否则将来正常增删关系都会无谓打红。
    """
    from social_archive.account_sync import PLATFORM_RELATIONS

    relations = PLATFORM_RELATIONS["bilibili"]
    assert "history" not in relations, (
        "B 站又开始采浏览历史了（Owner 2026-08-12 定的是「先停历史，点赞留着」）")
    assert "favorite" in relations and "like" in relations


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-q"]))
