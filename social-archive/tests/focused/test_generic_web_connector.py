import pytest
from social_archive.connectors.command import CommandArtifactConnector
from social_archive.connectors.base import ConnectorError
from social_archive.models import ConnectorRunRequest
from social_archive.registry import ConnectorRegistry

def test_command_connector_rejects_private_url(settings):
    c=CommandArtifactConnector('generic',settings.staging_root)
    with pytest.raises(ValueError):c.capture_url('http://127.0.0.1/a')

def test_bilibili_write_command_is_forbidden(settings):
    c=CommandArtifactConnector('bilibili',settings.staging_root)
    with pytest.raises(ConnectorError):c.bilibili_list('like')


def test_generic_web_public_url_can_be_saved_with_default_archive_levels(settings, service, store):
    result, captures = ConnectorRegistry(settings).run(
        "generic-web",
        ConnectorRunRequest(url="https://www.iana.org/domains/example"),
    )
    assert result.status == "success"
    assert result.scan_receipt["scope"] == "item"
    assert len(captures) == 1
    response = service.capture(captures[0])
    assert response.accepted_levels == ["L0", "L1", "L3"]
    assert store.get_content(response.content_id) is not None
    assert store.get_job(response.job_ids[0])["job_type"] == "download_l3"
