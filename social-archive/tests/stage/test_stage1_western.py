from __future__ import annotations

import io
import zipfile
from dataclasses import replace
from pathlib import Path

from social_archive.models import ConnectorRunRequest
from social_archive.registry import ConnectorRegistry


def _bundle(entries: dict[str, str]) -> bytes:
    output = io.BytesIO()
    with zipfile.ZipFile(output, "w") as archive:
        for name, value in entries.items():
            archive.writestr(name, value)
    return output.getvalue()


def test_stage1_generic_current_page_fixture_reaches_default_archive_levels(settings, service, store):
    result, captures = ConnectorRegistry(settings).run(
        "generic-web",
        ConnectorRunRequest(url="https://www.iana.org/domains/example"),
    )

    assert result.status == "success"
    assert result.scan_receipt["completeness"] == "complete"
    assert result.scan_receipt["scope"] == "item"
    assert len(captures) == 1
    response = service.capture(captures[0])
    assert response.accepted_levels == ["L0", "L1", "L3"]
    assert "L2" not in response.accepted_levels
    assert store.get_content(response.content_id) is not None
    assert store.get_job(response.job_ids[0])["job_type"] == "download_l3"


def test_stage1_social_archiver_fixture_is_preserved_and_idempotent(settings, service, store):
    payload = _bundle(
        {
            "SocialArchiver/reddit.md": (
                "---\n"
                "url: https://www.reddit.com/r/example/comments/fixture\n"
                "platform: reddit\n"
                "title: fixture export\n"
                "---\n"
                "fixture body"
            )
        }
    )

    first = service.import_social_archiver_bundle(
        payload,
        filename="social-archiver-fixture.zip",
        platform_hint="import",
        relation_type="saved",
        limit=100,
    )
    second = service.import_social_archiver_bundle(
        payload,
        filename="social-archiver-fixture.zip",
        platform_hint="import",
        relation_type="saved",
        limit=100,
    )

    assert first["bundle_sha256"] == second["bundle_sha256"]
    assert first["content_ids"] == second["content_ids"]
    assert first["job_ids"] == second["job_ids"]
    assert (settings.watch_root / first["bundle_path"]).is_file()
    content = store.get_content(first["content_ids"][0])
    assert content is not None
    assert len(content["relations"]) == 1
    assert len(content["artifacts"]) == 1
    assert len(store.list_library(platform="reddit")) == 1


def test_stage1_reddit_and_x_oauth_fixture_chains_normalize_captures(monkeypatch, settings, tmp_path):
    reddit_token = tmp_path / "reddit-token"
    x_token = tmp_path / "x-token"
    for token in (reddit_token, x_token):
        token.write_text("fixture-token", encoding="utf-8")
        token.chmod(0o600)
    monkeypatch.setenv("SOCIAL_ARCHIVE_REDDIT_USERNAME", "reddit-owner")
    monkeypatch.setenv("SOCIAL_ARCHIVE_REDDIT_OAUTH_TOKEN_FILE", str(reddit_token))
    monkeypatch.setenv("SOCIAL_ARCHIVE_X_API_ZERO_COST_CONFIRMED", "true")
    monkeypatch.setenv("SOCIAL_ARCHIVE_X_USER_ID", "x-owner")
    monkeypatch.setenv("SOCIAL_ARCHIVE_X_OAUTH_TOKEN_FILE", str(x_token))
    seen_urls: list[str] = []

    class Response:
        def __init__(self, payload):
            self.payload = payload

        def raise_for_status(self):
            return None

        def json(self):
            return self.payload

    class Client:
        def __init__(self, **kwargs):
            return None

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return None

        def get(self, url, **kwargs):
            seen_urls.append(url)
            if "oauth.reddit.com" in url:
                return Response(
                    {
                        "data": {
                            "children": [
                                {
                                    "kind": "t3",
                                    "data": {
                                        "id": "reddit-fixture",
                                        "permalink": "/r/example/comments/reddit-fixture/item/",
                                        "title": "Reddit fixture",
                                    },
                                }
                            ],
                            "after": None,
                        }
                    }
                )
            return Response({"data": [{"id": "x-fixture", "text": "X fixture"}], "meta": {}})

    monkeypatch.setattr("social_archive.connectors.oauth.httpx.Client", Client)
    registry = ConnectorRegistry(settings)
    reddit, reddit_captures = registry.run(
        "reddit",
        ConnectorRunRequest(relation_type="saved", source_account_id="reddit-owner", limit=3),
    )
    x, x_captures = registry.run(
        "x",
        ConnectorRunRequest(relation_type="bookmark", source_account_id="x-owner", limit=4),
    )

    assert reddit.status == "success"
    assert reddit.scan_receipt["completeness"] == "complete"
    assert len(reddit_captures) == 1
    assert reddit_captures[0].relation_type == "saved"
    assert str(reddit_captures[0].url) == "https://www.reddit.com/r/example/comments/reddit-fixture/item/"
    assert x.status == "success"
    assert x.scan_receipt["completeness"] == "complete"
    assert len(x_captures) == 1
    assert x_captures[0].relation_type == "bookmark"
    assert x_captures[0].external_content_id == "x-fixture"
    assert "https://oauth.reddit.com/user/reddit-owner/saved" in seen_urls
    assert "https://api.x.com/2/users/x-owner/bookmarks" in seen_urls


def test_stage1_instagram_sidecar_fixture_chain_normalizes_relative_output(monkeypatch, settings):
    sidecar_settings = replace(settings, cli_worker_url="http://cli-tools:5560", cli_worker_token_file=None)
    monkeypatch.delenv("SOCIAL_ARCHIVE_INSTAGRAM_SESSION_FILE", raising=False)
    monkeypatch.setenv("SOCIAL_ARCHIVE_INSTAGRAM_USERNAME", "instagram-owner")
    seen: dict[str, object] = {}

    class Response:
        def raise_for_status(self):
            return None

        def json(self):
            return {
                "status": "success",
                "run_id": "instagram-fixture",
                "artifacts": ["instagram-fixture/photo.jpg", "../../escape"],
                "observations": [
                    {
                        "id": "instagram-fixture",
                        "url": "https://www.instagram.com/p/instagram-fixture/",
                        "text": "Instagram fixture",
                    }
                ],
            }

    class Client:
        def __init__(self, **kwargs):
            seen["timeout"] = kwargs["timeout"]

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return None

        def post(self, url, **kwargs):
            seen["url"] = url
            seen["payload"] = kwargs["json"]
            seen["headers"] = kwargs["headers"]
            return Response()

    monkeypatch.setattr("social_archive.connectors.command.httpx.Client", Client)
    result, captures = ConnectorRegistry(sidecar_settings).run(
        "instagram",
        ConnectorRunRequest(source_account_id="instagram-owner", limit=4),
    )

    assert result.status == "success"
    assert result.scan_receipt["completeness"] == "partial"
    assert result.scan_receipt["scope"] == "account_relation"
    assert result.scan_receipt["execution_boundary"] == "isolated_http_sidecar"
    assert seen["url"] == "http://cli-tools:5560/v1/instagram/saved"
    assert seen["payload"] == {"username": "instagram-owner", "limit": 4}
    assert "session" not in seen["payload"]
    assert seen["headers"] == {}
    assert len(result.artifacts) == 1
    assert len(captures) == 1
    assert captures[0].relation_type == "saved"
    assert captures[0].external_content_id == "instagram-fixture"
