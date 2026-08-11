"""每条内容都答得出「怎么进来的」（v0.0.0.7 / INV-TRUTH-TRACEABLE）。

## 为什么现在才有

清点各不变量的守卫时发现：**INV-TRUTH-TRACEABLE / INV-REAL-USABLE /
INV-HONEST-EVIDENCE 三条一个判据都没有**，只活在文档里。

溯源断掉的样子不是报错，是「库里躺着一条东西，没人说得清它从哪来」。
那和静默的零是同一种病的另一面：**数据在，出处没了。**

生产实测（2026-08-04）：193 条内容全部有观察记录，0 条孤儿制品——
这条不变量当时是成立的，**但没有任何东西在盯着它**。
"""

from __future__ import annotations

from pathlib import Path

import pytest

from social_archive.db import RuntimeStore


@pytest.fixture
def store(tmp_path: Path) -> RuntimeStore:
    db = RuntimeStore(tmp_path / "runtime.sqlite3")
    db.initialize()
    return db


def test_a_fresh_database_is_traceable(store: RuntimeStore) -> None:
    audit = store.provenance_audit()
    assert audit["broken"] == [], f"空库就已经断了：{audit}"
    assert audit["content_total"] == 0


def test_real_capture_leaves_a_traceable_trail(tmp_path: Path, settings, service) -> None:
    """走真实的 capture 路径，而不是手工插表——手工插会绕过产品自己的写法。"""
    from social_archive.models import CaptureRequest

    service.capture(CaptureRequest(
        platform="generic-web",
        url="https://example.com/a",
        title="示例",
        relation_type="bookmark",
        requested_levels=["L0", "L1"],
        destination_ids=["social_archive"],
    ))
    audit = service.store.provenance_audit()
    assert audit["content_total"] == 1
    assert audit["broken"] == [], f"真实入库之后溯源就断了：{audit}"
    assert audit["content_without_observation"] == 0


def test_orphaned_artifact_is_reported_not_ignored(store: RuntimeStore) -> None:
    """挂在不存在内容上的制品必须被点名。

    这是**必须为 0** 的项：非 0 不代表数据错，代表溯源链断了。
    """
    with store.connection() as con:
        con.execute("PRAGMA foreign_keys=OFF")
        con.execute(
            "INSERT INTO artifact(id,content_id,archive_level,artifact_type,sha256,"
            "byte_size,media_type,local_path,created_at,status) "
            "VALUES('art_orphan','cnt_does_not_exist','L1','metadata_json','x',1,'application/json','/tmp/x','2026-01-01T00:00:00Z','stored')"
        )
    audit = store.provenance_audit()
    assert audit["artifact_without_content"] == 1
    assert "artifact_without_content" in audit["broken"], (
        "孤儿制品没有被列进 broken——审计跑了但不说话，等于没跑"
    )


def test_content_without_any_observation_is_reported(store: RuntimeStore) -> None:
    """有内容却没有任何观察记录 = 说不清它怎么进来的。"""
    with store.connection() as con:
        con.execute(
            "INSERT INTO content(id,platform,external_content_id,canonical_url,content_type,"
            "first_observed_at,last_observed_at,availability) "
            "VALUES('cnt_nowhere','generic-web','x','https://example.com/x','link',"
            "'2026-01-01T00:00:00Z','2026-01-01T00:00:00Z','available')"
        )
    audit = store.provenance_audit()
    assert audit["content_without_observation"] == 1
    assert "content_without_observation" in audit["broken"]


def test_the_audit_is_actually_wired_to_an_endpoint() -> None:
    """**挂上来才算数。** 本会话已经五次栽在「建好了没接上」。"""
    api = (Path(__file__).resolve().parents[2] / "src/social_archive/api.py").read_text(encoding="utf-8")
    assert "provenance_audit(" in api, "溯源审计没有挂到接口上，等于没有人在看"
    assert '"provenance"' in api
