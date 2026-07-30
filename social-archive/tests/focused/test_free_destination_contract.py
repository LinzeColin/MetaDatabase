from pathlib import Path


def test_notion_path_never_uses_paid_multipart_or_upload_endpoint():
    root = Path(__file__).parents[2]
    source = (root / "src/social_archive/destinations.py").read_text(encoding="utf-8")
    assert "api.notion.com/v1/pages" in source
    assert "/v1/file_uploads" not in source
    assert "multipart" not in source.lower()


def test_github_release_assets_use_safe_chunk_margin_and_not_git_blobs():
    root = Path(__file__).parents[2]
    source = (root / "scripts/github_release_backup.py").read_text(encoding="utf-8")
    assert "MAX_PART = 1800 * 1024 * 1024" in source
    assert '"gh", "release", "upload"' in source
    assert "age-encrypted object backup" in source
