import json

import pytest

from app.headless.publish import PublishError, ReleasePublisher, read_token
from tests.headless_fakes import FakeGitHub


def test_read_token_from_credentials_directory(tmp_path):
    (tmp_path / "github_token").write_text("abc123\n", encoding="utf-8")
    assert read_token({"CREDENTIALS_DIRECTORY": str(tmp_path)}) == "abc123"
    with pytest.raises(PublishError):
        read_token({})


def test_refuses_public_repo():
    publisher = ReleasePublisher("t", opener=FakeGitHub(private=False), sleep=lambda s: None)
    with pytest.raises(PublishError, match="不是私有仓"):
        publisher.assert_private_repo()


def test_one_draft_release_per_day_and_idempotent_assets(tmp_path):
    gh = FakeGitHub()
    publisher = ReleasePublisher("t", opener=gh, index_path=tmp_path / "idx.json", sleep=lambda s: None)
    release = publisher.ensure_release("2026-09-30", "n", "b")
    assert gh.releases[release.id]["draft"] is True
    assert release.tag == "serenity-report-2026-09-30"
    publisher.upload_asset(release, "a.md", b"1", "text/markdown")
    again = publisher.ensure_release("2026-09-30", "n", "b2")
    assert again.id == release.id  # 同一天复用同一个 Release
    publisher.upload_asset(again, "a.md", b"2", "text/markdown")
    assert gh.assets[release.id]["a.md"] == b"2"
    assert sum(1 for m, _ in gh.calls if m == "POST" and m and _.endswith("/releases")) == 1
    assert json.loads((tmp_path / "idx.json").read_text()) == {"2026-09-30": release.id}
