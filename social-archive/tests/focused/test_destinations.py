
from pathlib import Path

from social_archive.destinations import DestinationRegistry
import pytest

from social_archive.destinations import DestinationError
from social_archive.models import CaptureRequest
from social_archive.worker import _finish_failed_job, process_job


def test_capture_enqueues_destination_exports(service, store):
    unprobed = service.capture(CaptureRequest(
        platform="generic_web",
        url="https://www.wikipedia.org/article",
        title="示例文章",
        text="正文",
        requested_levels=["L0", "L1"],
        destination_ids=["social_archive", "markdown"],
    ))
    assert unprobed.skipped_destination_ids == ["markdown"]
    assert not store.list_jobs(limit=20)

    registry = DestinationRegistry(service.settings, store)
    assert registry.probe("markdown")["authorized"] is True
    response = service.capture(CaptureRequest(
        platform="generic_web",
        url="https://www.wikipedia.org/article-after-probe",
        title="示例文章",
        text="正文",
        requested_levels=["L0", "L1"],
        destination_ids=["social_archive", "markdown"],
    ))
    jobs = store.list_jobs(limit=20)
    assert any(job["job_type"] == "export_destination" and job["connector_id"] == "markdown" for job in jobs)
    export_job = next(job for job in jobs if job["job_type"] == "export_destination")
    claimed = store.claim_job("test")
    assert claimed and claimed["id"] == export_job["id"]
    process_job(claimed, service.settings, store)
    store.finish_job(claimed["id"], success=True)
    exported = list((service.settings.export_root / "markdown").rglob("*.md"))
    assert len(exported) == 1
    assert "示例文章" in exported[0].read_text(encoding="utf-8")


def test_destination_status_is_explicit(settings, store):
    views = DestinationRegistry(settings, store).views()
    by_id = {item["destination_id"]: item for item in views}
    status = {destination_id: item["state"] for destination_id, item in by_id.items()}
    assert status["social_archive"] == "connected"
    assert status["markdown"] == "needs_user_action"
    assert by_id["markdown"]["authorized"] is False
    assert status["notion"] == "needs_user_action"
    assert status["obsidian"] == "needs_user_action"
    assert DestinationRegistry(settings, store).probe("markdown")["authorized"] is True


def test_worker_enforces_stage_gate_and_isolates_destination_failure(service, store):
    registry = DestinationRegistry(service.settings, store)
    assert registry.probe("markdown")["authorized"] is True
    captured = service.capture(CaptureRequest(
        platform="generic_web",
        url="https://www.wikipedia.org/isolated-destinations",
        title="独立目的地回执",
        text="主存储先提交。",
        requested_levels=["L0", "L1"],
        destination_ids=["social_archive", "markdown", "notion"],
    ))
    assert captured.skipped_destination_ids == ["notion"]
    canonical_before = store.get_content(captured.content_id)
    assert canonical_before is not None
    canonical_fields = {key: canonical_before[key] for key in ("id", "canonical_url", "title", "metadata_json")}

    markdown_job = store.claim_job("markdown-fixture")
    assert markdown_job and markdown_job["connector_id"] == "markdown"
    process_job(markdown_job, service.settings, store)
    store.finish_job(markdown_job["id"], success=True)

    # The database boundary cannot be bypassed by a stale or malicious queued
    # job: Notion has neither a successful Probe nor configuration, so it makes
    # no provider call, creates an auditable failed receipt, and cannot roll back
    # the Markdown success or the Canonical content.
    denied_job_id = store.enqueue_job(
        "export_destination",
        {"content_id": captured.content_id, "destination_id": "notion"},
        connector_id="notion",
    )
    denied_job = store.claim_job("notion-fixture")
    assert denied_job and denied_job["id"] == denied_job_id
    with pytest.raises(DestinationError) as exc_info:
        process_job(denied_job, service.settings, store)
    assert exc_info.value.code == "DESTINATION_NOT_CONFIGURED"
    _finish_failed_job(store, denied_job, exc_info.value)
    assert store.get_job(denied_job_id)["status"] == "failed"

    receipts = store.list_destination_receipts(content_id=captured.content_id)
    assert {(item["destination_id"], item["status"]) for item in receipts} == {
        ("markdown", "done"),
        ("notion", "failed"),
    }
    assert store.get_content(captured.content_id) is not None
    canonical_after = store.get_content(captured.content_id)
    assert canonical_after is not None
    assert {key: canonical_after[key] for key in canonical_fields} == canonical_fields


def test_worker_rejects_new_job_while_destination_is_degraded(service, store, monkeypatch):
    registry = DestinationRegistry(service.settings, store)
    assert registry.probe("markdown")["authorized"] is True
    store.upsert_destination_state(
        "markdown",
        state="degraded",
        enabled=True,
        error_code="TEMPORARY_OUTAGE",
        message_zh="临时不可用。",
    )
    assert registry.is_export_authorized("markdown", allow_recovery=True) is True

    captured = service.capture(CaptureRequest(
        platform="generic_web",
        url="https://www.wikipedia.org/degraded-new-job",
        title="新任务不得绕过降级门",
        text="正文",
        requested_levels=["L0", "L1"],
        destination_ids=["social_archive"],
    ))
    job_id = store.enqueue_job(
        "export_destination",
        {"content_id": captured.content_id, "destination_id": "markdown"},
        connector_id="markdown",
    )
    claimed = store.claim_job("new-degraded-job")
    assert claimed and claimed["id"] == job_id and claimed["attempt_count"] == 0

    def forbidden_write(*_args, **_kwargs):
        raise AssertionError("未完成 active Probe 的新 job 不得写入 Markdown")

    monkeypatch.setattr(DestinationRegistry, "_write_markdown", forbidden_write)
    with pytest.raises(DestinationError) as exc_info:
        process_job(claimed, service.settings, store)
    assert exc_info.value.code == "DESTINATION_PROBE_REQUIRED"
    _finish_failed_job(store, claimed, exc_info.value)
    assert store.get_job(job_id)["status"] == "failed"


def test_worker_retry_recovers_previously_authorized_degraded_destination(service, store, monkeypatch):
    registry = DestinationRegistry(service.settings, store)
    assert registry.probe("markdown")["authorized"] is True
    captured = service.capture(CaptureRequest(
        platform="generic_web",
        url="https://www.wikipedia.org/degraded-retry",
        title="已授权重试可以恢复",
        text="正文",
        requested_levels=["L0", "L1"],
        destination_ids=["social_archive", "markdown"],
    ))
    job_id = captured.job_ids[0]
    first = store.claim_job("degraded-first")
    assert first and first["id"] == job_id and first["attempt_count"] == 0

    real_write = DestinationRegistry._write_markdown
    attempts = {"count": 0}

    def flaky_write(self, content, markdown, root):
        attempts["count"] += 1
        if attempts["count"] == 1:
            raise DestinationError("临时 Markdown 写入失败。", state="degraded", code="TEMPORARY_MARKDOWN")
        return real_write(self, content, markdown, root)

    monkeypatch.setattr(DestinationRegistry, "_write_markdown", flaky_write)
    with pytest.raises(DestinationError) as exc_info:
        process_job(first, service.settings, store)
    assert exc_info.value.code == "TEMPORARY_MARKDOWN"
    _finish_failed_job(store, first, exc_info.value)
    assert store.get_job(job_id)["status"] == "retry"

    assert store.retry_job(job_id) is True
    retry = store.claim_job("degraded-retry")
    assert retry and retry["id"] == job_id and retry["attempt_count"] == 1
    process_job(retry, service.settings, store)
    store.finish_job(job_id, success=True)
    assert attempts["count"] == 2
    assert store.get_job(job_id)["status"] == "done"
    assert sorted(item["status"] for item in store.list_destination_receipts(content_id=captured.content_id)) == ["done", "failed"]
