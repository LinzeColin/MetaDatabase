"""他要能把自己的 Markdown 整包拿走（2026-08-10）。

## 为什么加这个

Owner 的原话：「zzybrim/douyin-obsidian 别人已经开发成功了，你跑了十天了，
还没有结果」。**他说得对。**

去看他的实况：`markdown` 目的地 **193/193**——那 193 条（含 86 条抖音）
**早在 8 月 3 号就全部生成成 Markdown 了**，带 frontmatter、原始链接、正文，
一直躺在服务器的 `exports/markdown` 下。

而 `obsidian` 是 **1/193**，并且那个「Obsidian 库」是**服务器上的一个目录**
（远端接口没配）——和他电脑上的 Obsidian 之间没有任何通路。
界面却写着「Obsidian 已连接」，那颗「把没送过去的 192 条补上」点了，
也只是在一个他从不打开的目录里多 192 个文件。

对比那个项目赢在哪：**它写进用户自己的库。**

浏览器写不了任意本地路径、服务器够不着他的电脑——能走通的那条路是
**「让他下载，自己拖进库里」**。这条判据守的就是那条路。
"""

from __future__ import annotations

import importlib
import io
import zipfile

from fastapi.testclient import TestClient


def _client(tmp_path, monkeypatch):
    root = tmp_path / "data"
    pwa = tmp_path / "pwa"
    pwa.mkdir()
    (pwa / "index.html").write_text("ok", encoding="utf-8")
    for key, value in {
        "SOCIAL_ARCHIVE_DATA_ROOT": root,
        "SOCIAL_ARCHIVE_RUNTIME_DB": root / "db.sqlite",
        "SOCIAL_ARCHIVE_STAGING_ROOT": root / "staging",
        "SOCIAL_ARCHIVE_PRIVATE_DATABASE_ROOT": root / "private",
        "SOCIAL_ARCHIVE_WATCH_ROOT": root / "import",
        "SOCIAL_ARCHIVE_EXPORT_ROOT": root / "exports",
        "SOCIAL_ARCHIVE_PWA_ROOT": pwa,
    }.items():
        monkeypatch.setenv(key, str(value))
    import social_archive.api as api
    importlib.reload(api)
    return TestClient(api.app), api.settings


def test_the_whole_library_comes_back_as_one_zip(tmp_path, monkeypatch) -> None:
    """**他点一下就该拿到全部**，而且包里的东西要是原样的 Markdown。"""
    client, settings = _client(tmp_path, monkeypatch)
    root = settings.export_root / "markdown"
    (root / "douyin").mkdir(parents=True)
    (root / "bilibili").mkdir(parents=True)
    (root / "douyin" / "一条抖音-abc123.md").write_text(
        "---\nplatform: \"douyin\"\n---\n\n# 一条抖音\n", encoding="utf-8")
    (root / "bilibili" / "一条B站-def456.md").write_text("# 一条B站\n", encoding="utf-8")

    response = client.get("/v1/library/markdown.zip")
    assert response.status_code == 200, response.text
    assert response.headers["content-type"] == "application/zip"
    # **条数要说出来**：他得知道这一包是不是全部，而不是下完了自己去数。
    assert response.headers.get("x-markdown-file-count") == "2"

    with zipfile.ZipFile(io.BytesIO(response.content)) as archive:
        names = sorted(archive.namelist())
        assert names == ["bilibili/一条B站-def456.md", "douyin/一条抖音-abc123.md"], names
        # **平台目录要留着**：他解压之后是按平台分好的，不是一堆散文件。
        body = archive.read("douyin/一条抖音-abc123.md").decode("utf-8")
        assert body.startswith("---"), body[:40]


def test_it_says_why_when_there_is_nothing_to_take(tmp_path, monkeypatch) -> None:
    """**空的时候要说清为什么**，不许回一个 0 字节的包让他以为自己没内容。"""
    client, _ = _client(tmp_path, monkeypatch)
    response = client.get("/v1/library/markdown.zip")
    assert response.status_code == 503
    assert "Markdown" in response.json()["detail"]


def test_the_archive_page_offers_the_download(tmp_path, monkeypatch) -> None:
    """**接口有了不算数，他得点得到。**

    这个仓栽过六次以上「建好了没接上」——最近一次就是抽屉里那段回执列表，
    服务端发 `export_receipts`、界面读 `destination_receipts`，恒空且不报错。
    """
    from pathlib import Path
    html = (Path(__file__).resolve().parents[2] / "apps/pwa/index.html").read_text(encoding="utf-8")
    assert "/v1/library/markdown.zip" in html, (
        "资料库那一页上没有下载全部 Markdown 的入口——"
        "接口建好了没人调，他还是拿不到自己的东西")
    assert "Obsidian" in html, "那颗按钮没说清拿到之后能干什么"
