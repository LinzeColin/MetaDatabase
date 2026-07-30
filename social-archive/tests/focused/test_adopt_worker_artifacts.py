from pathlib import Path
import pytest
from social_archive.models import CaptureRequest


def test_worker_file_is_adopted_into_l3_cas(service, store, settings):
    response = service.capture(CaptureRequest(
        platform="douyin", url="https://www.douyin.com/video/1", relation_type="saved",
        requested_levels=["L0","L1"],
    ))
    downloaded = settings.staging_root / "runs/run-1/video.mp4"
    downloaded.parent.mkdir(parents=True, exist_ok=True)
    downloaded.write_bytes(b"media-bytes")
    ids = service.attach_local_artifacts(response.content_id, [{"path":str(downloaded),"type":"vendor_download"}])
    detail = store.get_content(response.content_id)
    assert len(ids) == 1
    assert any(item["archive_level"] == "L3" and Path(item["local_path"]).is_file() for item in detail["artifacts"])


def test_worker_file_outside_staging_is_rejected(service, settings, tmp_path):
    response = service.capture(CaptureRequest(
        platform="generic-web", url="https://www.wikipedia.org/1", requested_levels=["L0","L1"],
    ))
    outside = tmp_path / "outside.bin"
    outside.write_bytes(b"x")
    with pytest.raises(ValueError, match="staging"):
        service.attach_local_artifacts(response.content_id, [{"path":str(outside)}])
