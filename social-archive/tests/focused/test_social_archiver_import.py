from __future__ import annotations

import importlib
import io
import zipfile

import pytest
from fastapi.testclient import TestClient

from social_archive.connectors.social_archiver_bundle import SocialArchiverBundleImporter


def bundle(entries: dict[str, str]) -> bytes:
    output = io.BytesIO()
    with zipfile.ZipFile(output, "w") as archive:
        for name, value in entries.items():
            archive.writestr(name, value)
    return output.getvalue()


def _api_client(tmp_path, monkeypatch) -> TestClient:
    root = tmp_path / "data"
    pwa = tmp_path / "pwa"
    pwa.mkdir()
    (pwa / "index.html").write_text("ok", encoding="utf-8")
    monkeypatch.setenv("SOCIAL_ARCHIVE_DATA_ROOT", str(root))
    monkeypatch.setenv("SOCIAL_ARCHIVE_RUNTIME_DB", str(root / "db.sqlite"))
    monkeypatch.setenv("SOCIAL_ARCHIVE_STAGING_ROOT", str(root / "staging"))
    monkeypatch.setenv("SOCIAL_ARCHIVE_PRIVATE_DATABASE_ROOT", str(root / "private"))
    monkeypatch.setenv("SOCIAL_ARCHIVE_WATCH_ROOT", str(root / "import"))
    monkeypatch.setenv("SOCIAL_ARCHIVE_PWA_ROOT", str(pwa))
    monkeypatch.setenv("SOCIAL_ARCHIVE_PAIRING_REQUIRED", "false")
    import social_archive.api as api

    return TestClient(importlib.reload(api).app)


def test_social_archiver_zip_imports_markdown_without_extracting():
    payload = bundle({"Reddit/item.md": "---\nurl: https://www.reddit.com/r/test/comments/1\nplatform: reddit\ntitle: 示例\n---\n正文"})
    items = SocialArchiverBundleImporter().parse_zip(payload, bundle_name="export.zip", platform_hint="import", relation_type="saved", limit=100)
    assert len(items) == 1
    assert items[0].platform == "reddit"
    assert items[0].raw_metadata["import_format"] == "social_archiver_zip"


def test_social_archiver_zip_rejects_path_traversal():
    payload = bundle({"../escape.md": "https://unit.test"})
    with pytest.raises(ValueError, match="不安全路径"):
        SocialArchiverBundleImporter().parse_zip(payload, bundle_name="bad.zip", platform_hint="import", relation_type="saved", limit=100)


def test_service_import_preserves_bundle_and_is_idempotent(service, settings, store):
    payload = bundle({"X/item.md": "---\nurl: https://x.com/example/status/1\nplatform: x\ntitle: X 收藏\n---\n正文"})
    first = service.import_social_archiver_bundle(payload, filename="social-archiver.zip", platform_hint="import", relation_type="saved", limit=100)
    content_before = store.get_content(first["content_ids"][0])
    second = service.import_social_archiver_bundle(payload, filename="social-archiver.zip", platform_hint="import", relation_type="saved", limit=100)
    assert first["bundle_sha256"] == second["bundle_sha256"]
    assert first["content_ids"] == second["content_ids"]
    assert first["job_ids"] == second["job_ids"]
    assert (settings.watch_root / first["bundle_path"]).is_file()
    content_after = store.get_content(first["content_ids"][0])
    assert content_before is not None and content_after is not None
    assert len(content_before["relations"]) == len(content_after["relations"]) == 1
    assert len(content_before["artifacts"]) == len(content_after["artifacts"]) == 1
    assert len(store.list_library(platform="x")) == 1


def test_social_archiver_api_accepts_raw_zip_body_and_is_idempotent(tmp_path, monkeypatch):
    client = _api_client(tmp_path, monkeypatch)
    payload = bundle({"Reddit/item.md": "---\nurl: https://www.reddit.com/r/example/comments/import\nplatform: reddit\ntitle: API import\n---\n正文"})
    headers = {"Content-Type": "application/zip", "X-Archive-Filename": "owner-export.zip"}
    first = client.post("/v1/import/social-archiver", content=payload, headers=headers)
    second = client.post("/v1/import/social-archiver", content=payload, headers=headers)
    assert first.status_code == second.status_code == 200
    assert first.json()["imported"] == second.json()["imported"] == 1
    assert first.json()["bundle_sha256"] == second.json()["bundle_sha256"]
    assert first.json()["content_ids"] == second.json()["content_ids"]


def test_pwa_exposes_zero_tech_social_archiver_import():
    from pathlib import Path
    root = Path(__file__).parents[2] / "apps/pwa"
    html = (root / "index.html").read_text(encoding="utf-8")
    js = (root / "app.js").read_text(encoding="utf-8")
    # **钉的是意图，不是那句字面。**（2026-08-10）
    #
    # 原来断言的是「导入 Social Archiver / Markdown ZIP」这句原话。
    # 而弹窗里从 v0.0.0.21 起就有**两个**来源，第二个是「平台官方的
    # 『下载我的数据』包」——那是 X / Instagram 的主路径。按钮只写第一个，
    # 等于把那个能力藏在一个别的工具的名字后面：拿着 X 官方导出包的人认不出它。
    #
    # 改名之后这条断言红了——**它红得对**（字面确实变了），但它守的东西没变。
    # 所以改成钉「按钮上两个来源都点了名」，比原来更强。
    import re as _re
    button = _re.search(r'id="openImport"[^>]*>(.*?)</button>', html, _re.S)
    assert button, "找不到 #openImport 那颗按钮——零技术门槛的导入入口没了"
    label = _re.sub(r"<[^>]+>", " ", button.group(1))
    assert "导入" in label and "官方" in label, (
        f"导入按钮只写了一个来源：{label.strip()!r}——"
        "弹窗里支持两个，另一个是平台官方导出包（X / Instagram 的主路径）")
    assert "openImport" in html and "archiveFile" in html
    assert "/v1/import/social-archiver" in js
    # v0.0.0.22：文件类型放开了——bilibili-cli 那类工具导出的是一个裸的
    # JSON/YAML 清单，原来只认 .zip 等于那条导入路从入口就关着。
    # 仍然必须收 .zip（Social Archiver 那条本来就是打包的），所以钉的是"含 .zip"。
    assert '.zip' in html and 'accept=' in html
    # v0.0.0.22：内容类型改成 application/octet-stream——上传的不一定是压缩包了。
    assert '"Content-Type": "application/octet-stream"' in js
    assert '"X-Archive-Filename": safeArchiveFilename(file)' in js
    assert "body: file" in js
    assert "MAX_SOCIAL_ARCHIVER_BUNDLE_BYTES = 200 * 1024 * 1024" in js
