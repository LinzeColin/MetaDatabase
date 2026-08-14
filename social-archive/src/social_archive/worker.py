
from __future__ import annotations

import os
import socket
import time
from pathlib import Path

import httpx

from . import __version__
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
        raise MediaUnavailable(errors)


class MediaUnavailable(RuntimeError):
    """原始媒体文件没能取到。

    ## 为什么单独成一个异常

    2026-08-04 生产实测：193 条内容里 34 条没有 L3 原文件，对应 33 个失败任务
    （抖音 32、B站 1）。它们给用户看到的是

        JOB_FAILED  L3 下载未产生对象；WARNING: [Douyin] 7669577378074578239:
                    Failed to parse JSON: Expecting va…

    三处都不对：**码是通用的**（JOB_FAILED 说明不了任何事）、
    **正文是截断的英文工具输出**、**没有下一步**。

    而真相是可以说清楚的：抖音和 B 站都不让服务器直接取原文件
    （抖音返回的东西 yt-dlp 解不了，B 站回 HTTP 412 风控）。
    国内平台的 Cookie 按 INV-DOMESTIC-COOKIE-STAYS 一步都不离开浏览器，
    所以服务端**结构上**就拿不到——**重试多少次都一样**。

    要说给用户的是：内容本身已经保存好了（标题、链接、正文都在），
    少的只是那个原始视频文件。
    """

    def __init__(self, errors: list[str]) -> None:
        joined = " | ".join(errors[-3:])
        super().__init__("L3 下载未产生对象；" + joined)
        self.failure_code = self._classify(joined)
        self.retryable = self.failure_code == "MEDIA_TEMPORARILY_UNAVAILABLE"

    @staticmethod
    def _classify(detail: str) -> str:
        lowered = detail.lower()
        # 平台明确挡住了服务器：抖音的 JSON 解不了、B站的 412 风控。
        # **我们不绕**（L0 边界），所以这是结构性的，不是暂时的。
        if "failed to parse json" in lowered or "http error 412" in lowered or "http error 403" in lowered:
            return "MEDIA_BLOCKED_BY_PLATFORM"
        if "http error 429" in lowered or "timed out" in lowered or "timeout" in lowered:
            return "MEDIA_TEMPORARILY_UNAVAILABLE"
        # 工具不认这种内容形态，而不是平台把我们挡住了。
        # 实测那一条：`ERROR: Unsupported URL: https://www.douyin.com/note/…`
        # ——抖音的图文帖（note），yt-dlp 只认视频。
        # 对用户而言两者都是「没有原文件」，但原因不同：这条不是谁挡了谁。
        if "unsupported url" in lowered or "no video formats" in lowered:
            return "MEDIA_TYPE_UNSUPPORTED"
        return "MEDIA_NOT_RETRIEVED"


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
    # 异常自己带了失败码就用它的。**JOB_FAILED 只是兜底**——它说明不了
    # 任何事，而界面上「说不出原因」和「原因就在代码里」是两回事。
    code = getattr(exc, "failure_code", None) or "JOB_FAILED"
    if hasattr(exc, "retryable"):
        # 结构性失败不许再重试：平台挡住服务器这件事，重试多少次都一样。
        retryable = retryable and bool(exc.retryable)
    store.finish_job(
        job["id"],
        success=False,
        error_code=code,
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
    # 心跳节流：轮询默认 2 秒一次，每次都写库太吵。15 秒一次足够
    # 让「120 秒没动过就算挂了」这条判断有八次机会。
    last_beat = 0.0
    while True:
        now = time.monotonic()
        if now - last_beat >= 15:
            # **空转的那一轮也要写。** 只在有任务时写的话，
            # 「闲着但活着」和「死了」在数据上分不开。
            store.record_worker_heartbeat(owner, __version__)
            last_beat = now
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
