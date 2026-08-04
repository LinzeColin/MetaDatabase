"""诊断报告不许把「收敛掉的」藏起来（v0.0.0.7 / T08 / INV-NO-SILENT-ZERO）。

拦截缓冲区在 200 条封顶，解析前还会按地址去重并再封顶 30 条。
两处收敛都是必要的——不收敛的话 Owner 那一按会卡几分钟，
而他不知道是没坏还是坏了。

但**收敛得不留痕迹就危险**：报告上「抓到 200 条、读得懂 0 条」，
到底是平台没发那个请求，还是那条被挤掉了 / 没轮到读？
两件事的下一步完全不同，而这份报告是固化拦截前缀时唯一的依据。
"""

import importlib
import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

EXT = Path(__file__).resolve().parents[2] / "apps/browser-extension"


@pytest.fixture
def client_and_root(tmp_path, monkeypatch) -> tuple[TestClient, Path]:
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
    client.headers.update({"Authorization": "Bearer drill-token"})
    return client, root


def test_the_server_records_what_was_dropped_and_never_read(client_and_root) -> None:
    client, root = client_and_root
    response = client.post("/v1/extension/diagnostics", json={
        "platform": "bilibili", "page_url": "https://space.bilibili.com/1/favlist?x=1",
        "urls": ["https://api.bilibili.com/x/v3/fav/resource/list"],
        "capture_count": 200, "readable_count": 0,
        "dropped_count": 37, "not_parsed_count": 170,
        "note": "拦到 200 条（另有 37 条因为太多没收下）",
    })
    assert response.status_code == 200, response.text
    line = json.loads(
        (root / "diagnostics/extension-diagnostics.jsonl")
        .read_text(encoding="utf-8").strip().splitlines()[-1]
    )
    assert line["dropped_count"] == 37, "少收下的条数没落盘——报告读起来会像「平台没发那个请求」"
    assert line["not_parsed_count"] == 170, "没去读的条数没落盘"
    assert "body" not in line, "响应体绝不能上传"
    assert line["page_url"] == "https://space.bilibili.com/1/favlist", "查询串没被剥掉"


def test_the_popup_actually_sends_those_two_numbers() -> None:
    """服务端收得下，不等于弹窗送得上去。

    这是本项目栽过八次的那一族：两头都对，中间没接上。
    """
    popup = (EXT / "popup.js").read_text(encoding="utf-8")
    payload = popup.split("/v1/extension/diagnostics", 1)[1][:1200]
    assert "dropped_count" in payload, "弹窗没把少收下的条数送上去"
    assert "not_parsed_count" in payload, "弹窗没把没去读的条数送上去"
    assert "readback?.dropped" in payload and "readback?.notParsed" in payload, (
        "送的不是解析那一步真的算出来的数"
    )
