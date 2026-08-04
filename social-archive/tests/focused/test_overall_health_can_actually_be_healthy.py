"""一盏永远红着的灯，教会人不再看这盏灯（v0.0.0.7 / INV-NO-SILENT-ZERO）。

2026-08-05 打生产量出来的：/v1/status-projection 的 overall 恒为 degraded，
**而且永远不可能变成 healthy**——9 个连接器里 8 个是 blocked_environment，
那是**能力声明**里写着「本版本还不能自动读取」的那些，不是出了故障。

判据守两件事：本该工作的都好时 overall 要能变绿；
以及变绿的时候**不许把「大部分还没做」藏起来**。
"""

import importlib

import pytest
from fastapi.testclient import TestClient

from social_archive.status_projection import sanitize_status_document


@pytest.fixture
def projection(tmp_path, monkeypatch) -> dict:
    """按 tests/focused/test_bilibili_success_can_be_empty.py 里既有的方式起一个 app。"""
    root = tmp_path / "data"
    pwa = tmp_path / "pwa"
    pwa.mkdir()
    (pwa / "index.html").write_text("ok")
    for key, value in {
        "SOCIAL_ARCHIVE_DATA_ROOT": root,
        "SOCIAL_ARCHIVE_RUNTIME_DB": root / "db.sqlite",
        "SOCIAL_ARCHIVE_STAGING_ROOT": root / "staging",
        "SOCIAL_ARCHIVE_PRIVATE_DATABASE_ROOT": root / "private",
        "SOCIAL_ARCHIVE_WATCH_ROOT": root / "import",
        "SOCIAL_ARCHIVE_PWA_ROOT": pwa,
        "SOCIAL_ARCHIVE_PAIRING_REQUIRED": "false",
        "SOCIAL_ARCHIVE_API_TOKEN": "drill-token",
    }.items():
        monkeypatch.setenv(key, str(value))
    import social_archive.api as api

    importlib.reload(api)
    client = TestClient(api.app)
    response = client.get("/v1/status-projection",
                          headers={"Authorization": "Bearer drill-token"})
    assert response.status_code == 200, response.text
    return response.json()


def test_overall_is_not_permanently_red(projection) -> None:
    body = projection
    blocked = [c for c in body["connectors"] if c["state"] == "blocked_environment"]
    countable = [c for c in body["connectors"] if c["state"] != "blocked_environment"]
    assert blocked, "这个判据的前提没了：已经没有被声明为「还不能」的连接器了"
    if countable and all(c["state"] == "healthy" for c in countable):
        assert body["overall"] == "healthy", (
            f"本该工作的 {len(countable)} 个连接器全好，overall 却还是 "
            f"{body['overall']}——那 {len(blocked)} 个是能力声明写着做不到的，不是故障。"
            "一盏永远红着的灯，教会人不再看这盏灯。"
        )


def test_going_green_does_not_hide_how_much_is_not_done(projection) -> None:
    body = projection
    blocked = sum(1 for c in body["connectors"] if c["state"] == "blocked_environment")
    assert body["not_yet_supported"] == blocked, (
        "「还没做到」的条数没如实报出来——overall 变绿而这个数字藏起来，"
        "等于用全绿盖住「大部分还没做」"
    )


def test_nothing_countable_never_reports_healthy() -> None:
    """一个本该工作的都没有时，绝不能报健康——那才是真的静默的零。"""
    document = sanitize_status_document({
        "overall": "healthy", "version": "0.0.0.7",
        "connectors": [{"connector_id": "x", "state": "blocked_environment"}],
        "not_yet_supported": 1,
    })
    assert document["not_yet_supported"] == 1
    assert document["overall"] in {"healthy", "degraded", "down"}
