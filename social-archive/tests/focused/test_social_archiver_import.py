from __future__ import annotations

import io
import zipfile

import pytest

from social_archive.connectors.social_archiver_bundle import SocialArchiverBundleImporter


def bundle(entries: dict[str, str]) -> bytes:
    output = io.BytesIO()
    with zipfile.ZipFile(output, "w") as archive:
        for name, value in entries.items():
            archive.writestr(name, value)
    return output.getvalue()


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


def test_pwa_exposes_zero_tech_social_archiver_import():
    from pathlib import Path
    root = Path(__file__).parents[2] / "apps/pwa"
    html = (root / "index.html").read_text(encoding="utf-8")
    js = (root / "app.js").read_text(encoding="utf-8")
    assert "导入 Social Archiver / Markdown ZIP" in html
    assert "openImport" in html and "archiveFile" in html
    assert "/v1/import/social-archiver" in js
