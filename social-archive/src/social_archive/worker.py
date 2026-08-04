
from __future__ import annotations

import os
import socket
import time
from pathlib import Path

import httpx

from .account_sync import AccountSyncCoordinator
from .config import Settings
from .connectors.command import CommandArtifactConnector
from .credentials import (
    CUSTODIAL_PLATFORMS,
    CredentialStore,
    CredentialUnavailable,
    CredentialVault,
)
from .db import RuntimeStore
from .destinations import DestinationError, DestinationRegistry, retry_after_seconds_from_error
from .downloader import DirectMediaDownloader
from .registry import ConnectorRegistry
from .service import ArchiveService
from .storage import ContentAddressedStore


def process_job(job: dict, settings: Settings, store: RuntimeStore) -> None:
    payload = job["payload"]
    if job["job_type"] == "account_sync":
        AccountSyncCoordinator(
            settings,
            store,
            ArchiveService(settings, store),
            ConnectorRegistry(settings),
        ).process_job(payload)
        return
    if job["job_type"] == "export_destination":
        # A queued job from a new capture is not a recovery grant.  Only a job
        # that has already failed at least once may cross a transient degraded
        # destination state; every first attempt still needs a connected Probe.
        DestinationRegistry(settings, store).export(
            payload["destination_id"],
            payload["content_id"],
            job_id=job["id"],
            allow_recovery=int(job.get("attempt_count", 0)) > 0,
        )
        return
    if job["job_type"] != "download_l3":
        raise ValueError(f"未知任务类型：{job['job_type']}")
    content_id = payload["content_id"]
    media_urls = payload.get("media_urls") or []
    cas = ContentAddressedStore(settings.staging_root / "objects")
    direct = DirectMediaDownloader(cas, settings.max_download_bytes)
    saved = 0
    errors: list[str] = []
    for url in media_urls:
        try:
            obj = direct.download(url)
            store.add_artifact(content_id=content_id, archive_level="L3", artifact_type="media", sha256=obj.sha256, byte_size=obj.byte_size, media_type=obj.media_type, local_path=str(obj.path))
            saved += 1
        except Exception as exc:  # noqa: BLE001 - worker isolates per artifact and reports a bounded message
            errors.append(f"direct:{exc.__class__.__name__}:{exc}")
    if not media_urls or saved == 0:
        platform = str(payload.get("platform", "generic")).lower()
        command = CommandArtifactConnector(platform, settings.staging_root, worker_url=settings.cli_worker_url, worker_token_file=settings.cli_worker_token_file, worker_output_root=settings.cli_output_root)

        def _capture(cookies_path: str | None) -> object:
            out = command.capture_url(payload["page_url"], tool="gallery-dl", cookies_path=cookies_path)
            if out.status != "success":
                out = command.capture_url(payload["page_url"], tool="yt-dlp", cookies_path=cookies_path)
            return out

        # ——— T06 的落点：把托管的平台会话真的交给工具 ———
        #
        # 在这段之前，凭据**存进去了却从来没有被用过**：
        # CredentialStore.materialize() 全仓只有测试在调，capture_url 的 argv
        # 里根本没有 --cookies。也就是说 Owner 就算上传了 X 的会话，
        # 服务端仍然按未登录去抓，只拿得到公开内容——
        # 而 T06 的验收恰恰是「能取到只有登录用户才看得到的内容」。
        # 不接这一段，那条验收**无论谁登录都不可能通过**。
        cookie_note: str | None = None
        user_id = store.owner_user_for_content(content_id) if platform in CUSTODIAL_PLATFORMS else None
        if user_id:
            vault = CredentialVault(
                recipient=settings.credential_age_recipient,
                identity_file=settings.credential_age_identity_file,
            )
            try:
                with CredentialStore(store, vault).materialize(user_id=user_id, platform=platform) as cookies:
                    result = _capture(str(cookies))
            except CredentialUnavailable as exc:
                # 没托管过这个平台的会话，或解不开。**照样按未登录抓一次**——
                # 公开内容还能救回来；但把原因记下来，不许静默降级
                # （INV-NO-SILENT-ZERO：0 条时说得出为什么）。
                cookie_note = f"credential:{exc}"
                result = _capture(None)
        else:
            result = _capture(None)
        for artifact in result.artifacts:
            source = Path(artifact["path"])
            if not source.exists():
                continue
            obj = cas.import_file(source)
            store.add_artifact(content_id=content_id, archive_level="L3", artifact_type="media", sha256=obj.sha256, byte_size=obj.byte_size, media_type=obj.media_type, local_path=str(obj.path))
            saved += 1
        errors.extend(e.get("message", "worker failed") for e in result.errors)
        if cookie_note:
            errors.append(cookie_note)
    if saved == 0:
        raise RuntimeError("L3 下载未产生对象；" + " | ".join(errors[-3:]))


def _retryable_destination_failure(exc: Exception) -> bool:
    if isinstance(exc, DestinationError):
        return exc.state == "degraded"
    if isinstance(exc, httpx.HTTPStatusError):
        return exc.response.status_code == 429 or exc.response.status_code >= 500
    return isinstance(exc, httpx.RequestError)


def _finish_failed_job(store: RuntimeStore, job: dict, exc: Exception) -> None:
    retryable = job.get("attempt_count", 0) < 3
    if job.get("job_type") == "export_destination":
        retryable = retryable and _retryable_destination_failure(exc)
    store.finish_job(
        job["id"],
        success=False,
        error_code=exc.__class__.__name__,
        error_message=str(exc)[:2000],
        retryable=retryable,
        retry_after_seconds=retry_after_seconds_from_error(exc),
    )


def run() -> None:
    settings = Settings.from_env()
    settings.ensure_directories()
    store = RuntimeStore(settings.runtime_db)
    store.initialize()
    owner = f"{socket.gethostname()}:{os.getpid()}"
    while True:
        job = store.claim_job(owner)
        if not job:
            time.sleep(settings.worker_poll_seconds)
            continue
        try:
            process_job(job, settings, store)
            store.finish_job(job["id"], success=True)
        except Exception as exc:  # noqa: BLE001 - top-level worker boundary
            _finish_failed_job(store, job, exc)


if __name__ == "__main__":
    run()
