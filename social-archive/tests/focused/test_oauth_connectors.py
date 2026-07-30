from social_archive.connectors.oauth import RedditConnector, XConnector
from social_archive.models import ConnectorRunRequest
from social_archive.registry import ConnectorRegistry


def test_missing_oauth_is_environment_block(monkeypatch, settings):
    monkeypatch.delenv("SOCIAL_ARCHIVE_REDDIT_USERNAME", raising=False)
    monkeypatch.delenv("SOCIAL_ARCHIVE_REDDIT_OAUTH_TOKEN_FILE", raising=False)
    assert XConnector(None, lambda: None).fetch("bookmark").status == "blocked_environment"
    assert RedditConnector(None, "ua", lambda: None).fetch("saved").status == "blocked_environment"

    registry = ConnectorRegistry(settings)
    result, captures = registry.run("reddit", ConnectorRunRequest(relation_type="upvoted"))
    reddit_probe = registry._live_probe("reddit")
    assert result.status == "blocked_environment"
    assert result.errors[0]["code"] == "REDDIT_AUTH_MISSING"
    assert captures == []
    assert reddit_probe["state"] == "blocked_environment"

    fallback, fallback_captures = registry.run(
        "generic-web",
        ConnectorRunRequest(url="https://www.iana.org/domains/example"),
    )
    assert fallback.status == "success"
    assert len(fallback_captures) == 1
