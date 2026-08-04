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

from tests.focused._source_slices import run_diagnosis_body

ROOT = Path(__file__).resolve().parents[2]
EXT = ROOT / "apps/browser-extension"


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


def test_the_popup_tells_him_not_to_click_the_page() -> None:
    """弹窗一失去焦点就整个关掉，正在跑的诊断会断在半路。

    断在半路的后果不是「慢一点」：抓到的东西不会被读，结果也不会存到服务器，
    **而 Owner 只按一次**。用滚轮滚不会夺走焦点，点一下页面会——
    而这行字原来只写「请往下滚动几屏」，照着做最自然的动作恰好是先点一下页面。
    """
    popup = (EXT / "popup.js").read_text(encoding="utf-8")
    loop = run_diagnosis_body(popup)
    assert "别点页面" in loop, "没告诉他点页面会把这个窗关掉"
    assert "滚轮" in loop, "没说清用什么滚——「滚动」在鼠标上有两种做法，一种会关窗"
    assert "请往下滚动几屏…" not in loop, "那句会把人引去点页面的旧文案又回来了"


def test_the_report_says_which_capture_was_readable_not_just_how_many(client_and_root) -> None:
    """**T09（抓到即固化）要的是那个地址，不是一个数字。**

    只报 readable_count=3，等于说了「有三条能读」却不说是哪三条。
    拦截前缀正是从那个地址上取的——报告里少了它，Owner 那一按就白按，
    还得再按一次，而他只按一次。
    """
    client, root = client_and_root
    response = client.post("/v1/extension/diagnostics", json={
        "platform": "bilibili", "page_url": "https://space.bilibili.com/1/favlist",
        "urls": ["https://api.bilibili.com/x/v3/fav/resource/list?pn=1",
                 "https://api.bilibili.com/x/web-interface/nav"],
        "capture_count": 2, "readable_count": 1,
        "readable_urls": ["https://api.bilibili.com/x/v3/fav/resource/list?pn=1"],
        "note": "拦到 2 条，其中 1 条读得懂",
    })
    assert response.status_code == 200, response.text
    line = json.loads(
        (root / "diagnostics/extension-diagnostics.jsonl")
        .read_text(encoding="utf-8").strip().splitlines()[-1]
    )
    assert line["readable_urls"] == ["https://api.bilibili.com/x/v3/fav/resource/list?pn=1"], (
        "读得懂的那几条地址没落盘——固化拦截前缀时无从下手"
    )
    assert "body" not in json.dumps(line), "响应体绝不能上传"


def test_the_whole_chain_carries_the_readable_urls() -> None:
    """服务端收得下不等于弹窗送得上去，弹窗送得上去不等于 background 算得出来。

    这是本项目栽过九次的那一族：两头都对，中间没接上。三段都钉。
    """
    background = (EXT / "background.js").read_text(encoding="utf-8")
    parse = background.split("SA_PARSE_NET_CAPTURES", 1)[1][:5000]
    assert "readableUrls.push(capture.url)" in parse, "background 没记下是哪一条读得懂"
    assert "readableUrls," in parse or "readableUrls " in parse, "算出来了却没返回"
    popup = (EXT / "popup.js").read_text(encoding="utf-8")
    payload = popup.split("/v1/extension/diagnostics", 1)[1][:1400]
    assert "readable_urls" in payload, "弹窗没把它送上去"
    api = (ROOT / "src/social_archive/api.py").read_text(encoding="utf-8")
    assert "readable_urls" in api, "服务端模型里没有这一项，pydantic 会静默丢掉"


def test_the_button_does_not_promise_ten_seconds_it_cannot_keep() -> None:
    """按钮原来写「开始看（10 秒）」，而实际最长要 30 秒等待 + 十几秒安装。

    **他会以为卡住了，然后点别处——而弹窗一失焦就整个关掉**，诊断断在半路。
    一个说不准的时间承诺，比不给时间更坏。
    """
    html = (EXT / "popup.html").read_text(encoding="utf-8")
    assert "开始看（10 秒）" not in html, "又写回那个守不住的 10 秒了"
    assert "别关这个窗" in html, "没有告诉他这个窗不能关"


def test_he_is_told_about_the_permission_dialog_before_it_appears() -> None:
    """安装那一步进门就要平台授权，Chrome 会弹一个原生框。

    没人提前说的话，一个说自己「没有技术基础」的人最可能点「拒绝」——
    然后拿到 PLATFORM_PERMISSION_DENIED，而他并不知道自己刚拒绝的是什么。
    这一步在他**只按一次**的那条路上，不能靠他猜。
    """
    html = (EXT / "popup.html").read_text(encoding="utf-8")
    assert "允许" in html, "弹窗界面上没有一处提到那个授权框"
    popup = (EXT / "popup.js").read_text(encoding="utf-8")
    loop = popup.split("async function runDiagnosis", 1)[1][:4000]
    assert "浏览器要问你「允许吗」" in loop, "按钮在等授权时不说话，他不知道该点哪个"
