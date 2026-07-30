import subprocess
import sys
from pathlib import Path

from social_archive.db import RuntimeStore
from social_archive.models import CaptureRequest


def test_stage0_walking_skeleton(service, store, settings):
    response = service.capture(
        CaptureRequest(
            platform="generic-web",
            url="https://www.wikipedia.org/walk",
            title="Walking Skeleton",
            text="可检索文字",
            requested_levels=["L0", "L1", "L3"],
        )
    )

    # L0 is the canonical content record; L1 is staged metadata; L3 is a
    # durable download job.  These assertions bind the Stage 0 oracle rather
    # than merely proving that a library row exists.
    assert response.accepted_levels == ["L0", "L1", "L3"]
    assert response.paused_levels == []
    content = store.get_content(response.content_id)
    assert content is not None
    assert any(artifact["archive_level"] == "L1" for artifact in content["artifacts"])
    assert store.list_library(q="可检索文字")[0]["id"] == response.content_id
    assert len(response.job_ids) == 1
    assert store.get_job(response.job_ids[0])["status"] == "queued"

    # Restart recovery must retain both the searchable content and the queued
    # L3 work; completing it through the reopened store proves the task state
    # is not only process-local.
    reopened = RuntimeStore(settings.runtime_db)
    reopened.initialize()
    assert reopened.list_library(q="可检索文字")[0]["id"] == response.content_id
    recovered_job = reopened.claim_job("stage0-restart")
    assert recovered_job is not None
    assert recovered_job["id"] == response.job_ids[0]
    assert recovered_job["job_type"] == "download_l3"
    reopened.finish_job(recovered_job["id"], success=True)
    assert reopened.get_job(recovered_job["id"])["status"] == "done"


def test_stage0_doctor_compose_check_is_credential_free(tmp_path):
    compose_file = tmp_path / "compose.yaml"
    compose_file.write_text(
        "services:\n"
        "  core:\n"
        "    image: example/core\n"
        "    env_file:\n"
        "      - .env\n",
        encoding="utf-8",
    )
    validator = Path(__file__).parents[2] / "scripts" / "validate_compose.py"
    result = subprocess.run(
        [sys.executable, str(validator), str(compose_file)],
        cwd=tmp_path,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0
    assert "Owner 配置 .env 缺失，跳过 Docker Compose 渲染" in result.stdout
