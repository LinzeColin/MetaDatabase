from social_archive.connectors.base import ConnectorResult
from social_archive.models import ConnectorRunRequest, MarkdownImportRequest
from social_archive.registry import ConnectorRegistry


def test_x_official_api_is_blocked_until_zero_cost_is_explicit(monkeypatch, settings, service):
    monkeypatch.setenv("SOCIAL_ARCHIVE_X_API_ZERO_COST_CONFIRMED", "unknown")
    monkeypatch.setenv("SOCIAL_ARCHIVE_X_USER_ID", "configured-owner")
    monkeypatch.setenv("SOCIAL_ARCHIVE_X_OAUTH_TOKEN_FILE", "/configured-but-not-read.token")
    constructed: list[object] = []

    class ForbiddenXConnector:
        def __init__(self, *args, **kwargs):
            constructed.append((args, kwargs))
            raise AssertionError("zero-cost gate must block before constructing the official X client")

    monkeypatch.setattr("social_archive.registry.XConnector", ForbiddenXConnector)
    registry = ConnectorRegistry(settings)
    assert registry._live_probe("x") == {
        "state": "blocked_environment",
        "error_code": "X_ZERO_COST_NOT_CONFIRMED",
    }

    result, captures = registry.run("x", ConnectorRunRequest(relation_type="bookmark", limit=3))
    assert result.status == "blocked_environment"
    assert result.errors[0]["code"] == "X_ZERO_COST_NOT_CONFIRMED"
    assert result.scan_receipt["completeness"] == "unknown"
    assert captures == []
    assert constructed == []

    fallback, fallback_captures = registry.run(
        "generic-web",
        ConnectorRunRequest(url="https://www.iana.org/domains/example"),
    )
    assert fallback.status == "success"
    assert len(fallback_captures) == 1
    (settings.watch_root / "fallback.md").write_text("https://www.iana.org/domains/example", encoding="utf-8")
    imported = service.import_markdown(MarkdownImportRequest(platform_hint="import", relation_type="saved", limit=10))
    assert imported["imported"] == 1


def test_x_confirmed_zero_cost_gate_preserves_bookmark_and_like(monkeypatch, settings):
    monkeypatch.setenv("SOCIAL_ARCHIVE_X_API_ZERO_COST_CONFIRMED", "true")
    monkeypatch.setenv("SOCIAL_ARCHIVE_X_USER_ID", "owner")
    calls: list[tuple[str, int, str | None]] = []

    class FixtureXConnector:
        def __init__(self, *args, **kwargs):
            return None

        def fetch(self, relation, limit, cursor=None):
            calls.append((relation, limit, cursor))
            return ConnectorResult(
                "x",
                f"fixture-{relation}",
                "success",
                observations=[{"id": f"{relation}-1", "text": relation}],
                scan_receipt={"completeness": "complete", "item_count": 1},
            )

    monkeypatch.setattr("social_archive.registry.XConnector", FixtureXConnector)
    registry = ConnectorRegistry(settings)
    bookmark, bookmark_captures = registry.run("x", ConnectorRunRequest(relation_type="bookmark", limit=4))
    like, like_captures = registry.run("x", ConnectorRunRequest(relation_type="like", limit=5, cursor="like-page-2"))

    assert calls == [("bookmark", 4, None), ("like", 5, "like-page-2")]
    assert bookmark.scan_receipt["relation_type"] == "bookmark"
    assert like.scan_receipt["relation_type"] == "like"
    assert bookmark_captures[0].relation_type == "bookmark"
    assert like_captures[0].relation_type == "like"
    assert bookmark_captures[0].external_content_id == "bookmark-1"
    assert like_captures[0].external_content_id == "like-1"
