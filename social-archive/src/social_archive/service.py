from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from .config import Settings
from .db import RuntimeStore
from .destinations import DestinationRegistry
from .models import CaptureRequest, CaptureResponse, MarkdownImportRequest
from .quota import QuotaGuard
from .storage import ContentAddressedStore
from .utils import json_bytes
from .connectors.markdown_watch import MarkdownWatchImporter
from .connectors.social_archiver_bundle import SocialArchiverBundleImporter


class ArchiveService:
    def __init__(self, settings: Settings, store: RuntimeStore):
        self.settings = settings
        self.store = store
        self.cas = ContentAddressedStore(settings.staging_root / "objects")
        self.quota = QuotaGuard(settings, store)
        self.markdown = MarkdownWatchImporter(settings.watch_root)
        self.social_archiver = SocialArchiverBundleImporter()

    def capture(self, request: CaptureRequest) -> CaptureResponse:
        requested = list(dict.fromkeys(request.requested_levels))
        accepted: list[str] = []
        paused: list[str] = []
        if "L2" in requested and not self.settings.l2_enabled:
            requested.remove("L2")
            paused.append("L2")
        decision = self.quota.evaluate_local_staging()
        if "L3" in requested and not decision.allow_l3:
            requested.remove("L3")
            paused.append("L3")
        content_id, relation_id, observation_id = self.store.capture(request)
        accepted.extend(level for level in requested if level in {"L0", "L1"})
        l1_payload = {
            "schema_version":"1.0","content_id":content_id,"platform":request.platform,
            "url":str(request.url),"title":request.title,"author_name":request.author_name,
            "text":request.text,"published_at":request.published_at,"relation_type":request.relation_type,
            "collection_key":request.collection_key,"raw_metadata":request.raw_metadata
        }
        l1_data = json_bytes(l1_payload)
        stored = self.cas.put_bytes(l1_data, suffix=".json", media_type="application/json")
        self.store.add_artifact(content_id=content_id, archive_level="L1", artifact_type="metadata_json", sha256=stored.sha256, byte_size=stored.byte_size, media_type=stored.media_type, local_path=str(stored.path))
        job_ids: list[str] = []
        if "L3" in requested:
            accepted.append("L3")
            media_urls = [str(url) for url in request.media_urls]
            payload = {"content_id":content_id,"platform":request.platform.lower(),"page_url":str(request.url),"media_urls":media_urls}
            job_ids.append(self.store.enqueue_job("download_l3", payload, connector_id=request.platform.lower()))
        skipped_destination_ids: list[str] = []
        destination_registry = DestinationRegistry(self.settings, self.store)
        for destination_id in request.destination_ids:
            if destination_id == "social_archive":
                continue
            # A requested target is not an authorization grant.  Capture commits
            # Canonical facts first, then only hands an export job to destinations
            # that have a successful active Probe (or confirmed prior export).
            if not destination_registry.is_export_authorized(destination_id):
                skipped_destination_ids.append(destination_id)
                continue
            job_ids.append(self.store.enqueue_job("export_destination", {"content_id": content_id, "destination_id": destination_id}, connector_id=destination_id))
        return CaptureResponse(
            content_id=content_id,
            relation_id=relation_id,
            observation_id=observation_id,
            job_ids=job_ids,
            skipped_destination_ids=skipped_destination_ids,
            accepted_levels=accepted,
            paused_levels=paused,
            detail_url=f"/item/{content_id}",
        )


    def attach_local_artifacts(self, content_id: str, artifacts: list[dict[str, Any]]) -> list[str]:
        if not self.store.get_content(content_id):
            raise ValueError("内容不存在，不能挂接下载文件")
        root = self.settings.staging_root.resolve()
        artifact_ids: list[str] = []
        for item in artifacts:
            raw_path = Path(str(item.get("path") or ""))
            if not raw_path.is_file() or raw_path.is_symlink():
                raise ValueError("Worker 只允许返回 staging 目录中的普通文件")
            source = raw_path.resolve(strict=True)
            try:
                source.relative_to(root)
            except ValueError as exc:
                raise ValueError("Worker 文件越过 staging 边界") from exc
            byte_size = source.stat().st_size
            if byte_size > self.settings.max_download_bytes:
                raise ValueError("Worker 文件超过单文件硬门")
            stored = self.cas.import_file(source)
            artifact_ids.append(self.store.add_artifact(
                content_id=content_id,
                archive_level="L3",
                artifact_type=str(item.get("type") or "downloaded_file"),
                sha256=stored.sha256,
                byte_size=stored.byte_size,
                media_type=stored.media_type,
                local_path=str(stored.path),
                status="staged",
            ))
        return artifact_ids

    def import_markdown(self, request: MarkdownImportRequest) -> dict[str, Any]:
        captures = self.markdown.scan(requested_root=request.root, platform_hint=request.platform_hint, relation_type=request.relation_type, limit=request.limit)
        responses = [self.capture(item) for item in captures]
        return {"imported":len(responses),"content_ids":[r.content_id for r in responses],"job_ids":[j for r in responses for j in r.job_ids]}


    def import_social_archiver_bundle(
        self,
        payload: bytes,
        *,
        filename: str,
        platform_hint: str,
        relation_type: str,
        limit: int,
    ) -> dict[str, Any]:
        digest = hashlib.sha256(payload).hexdigest()
        bundle_root = self.settings.watch_root / "social-archiver-bundles"
        bundle_root.mkdir(parents=True, exist_ok=True)
        bundle_path = bundle_root / f"{digest}.zip"
        if not bundle_path.exists():
            bundle_path.write_bytes(payload)
        captures = self.social_archiver.parse_zip(
            payload,
            bundle_name=filename,
            platform_hint=platform_hint,
            relation_type=relation_type,
            limit=limit,
        )
        responses = [self.capture(item) for item in captures]
        return {
            "imported": len(responses),
            "content_ids": [item.content_id for item in responses],
            "job_ids": [job for item in responses for job in item.job_ids],
            "bundle_sha256": digest,
            "bundle_path": str(bundle_path.relative_to(self.settings.watch_root)),
            "message_zh": f"已从 Social Archiver/Markdown ZIP 导入 {len(responses)} 条",
        }
