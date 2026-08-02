from __future__ import annotations

import os
import shutil
import time
from pathlib import Path
from typing import Any

from .config import Settings
from .connectors.base import ConnectorResult
from .connectors.command import CommandArtifactConnector
from .connectors.http_workers import OpenAPIURLWorkerConnector, XHSWorkerConnector
from .connectors.oauth import RedditConnector, XConnector
from .models import CaptureRequest, ConnectorRunRequest
from .utils import read_secret, utcnow

DISPLAY = {
    "generic-web":"通用网页","x":"X","reddit":"Reddit","instagram":"Instagram","tiktok":"TikTok",
    "xiaohongshu":"小红书","douyin":"抖音","kuaishou":"快手","bilibili":"哔哩哔哩"
}
DEFAULT_RELATION = {
    "generic-web":"manual_save","x":"bookmark","reddit":"saved","instagram":"saved","tiktok":"saved",
    "xiaohongshu":"saved","douyin":"saved","kuaishou":"saved","bilibili":"favorite"
}


class ConnectorRegistry:
    def __init__(self, settings: Settings):
        self.settings = settings
        self.command = CommandArtifactConnector("command-artifact", settings.staging_root, worker_url=settings.cli_worker_url, worker_token_file=settings.cli_worker_token_file, worker_output_root=settings.cli_output_root)
        vendor_root = Path(os.getenv("SOCIAL_ARCHIVE_VENDOR_OUTPUT_ROOT", str(settings.data_root / "vendor-output"))).resolve()
        vendor_root.mkdir(parents=True, exist_ok=True)
        self._connectors = {
            "xiaohongshu": XHSWorkerConnector(settings.xhs_worker_url, output_root=vendor_root / "xhs"),
            "kuaishou": OpenAPIURLWorkerConnector("kuaishou", "快手", settings.ks_worker_url, output_root=vendor_root / "kuaishou"),
            "douyin": OpenAPIURLWorkerConnector("douyin", "抖音", settings.douk_worker_url, output_root=vendor_root / "douk"),
        }

    @staticmethod
    def _secret(env_name: str):
        return lambda: read_secret(os.getenv(env_name))

    @staticmethod
    def _x_api_zero_cost_confirmed() -> bool:
        return os.getenv("SOCIAL_ARCHIVE_X_API_ZERO_COST_CONFIRMED", "false").strip().lower() in {"1", "true", "yes", "on"}

    @staticmethod
    def _x_zero_cost_block() -> ConnectorResult:
        return ConnectorResult(
            "x", "x-zero-cost-gate", "blocked_environment",
            scan_receipt={"completeness":"unknown", "item_count":0},
            errors=[{
                "code":"X_ZERO_COST_NOT_CONFIRMED",
                "message":"零费用门未确认，官方 X API 保持关闭。请使用浏览器扩展保存当前页或导入 Social Archiver/Markdown；只有确认该 API 权益绝不会收费后才可显式开启。",
                "retryable":False,
            }],
        )

    def _live_probe(self, connector_id: str) -> dict[str, Any]:
        if connector_id == "generic-web":
            return {"state":"healthy"}
        if connector_id == "x":
            if not self._x_api_zero_cost_confirmed():
                return {"state":"blocked_environment", "error_code":"X_ZERO_COST_NOT_CONFIRMED"}
            return XConnector(os.getenv("SOCIAL_ARCHIVE_X_USER_ID"), self._secret("SOCIAL_ARCHIVE_X_OAUTH_TOKEN_FILE")).health()
        if connector_id == "reddit":
            return RedditConnector(os.getenv("SOCIAL_ARCHIVE_REDDIT_USERNAME"), os.getenv("SOCIAL_ARCHIVE_REDDIT_USER_AGENT","SocialArchive/0.0.0.6"), self._secret("SOCIAL_ARCHIVE_REDDIT_OAUTH_TOKEN_FILE")).health()
        if connector_id == "instagram":
            probe = self.command.health()
            return probe if probe.get("state") == "healthy" else {"state":"blocked_environment", "error_code":probe.get("error_code", "CLI_SIDECAR_NOT_READY")}
        if connector_id == "tiktok":
            return self.command.health()
        if connector_id == "bilibili":
            return self.command.health()
        live = self._connectors.get(connector_id)
        return live.health() if live else {"state":"disabled"}

    def health_views(self, persisted: list[dict[str, Any]]) -> list[dict[str, Any]]:
        by_id = {row["connector_id"]:row for row in persisted}
        result=[]
        for connector_id, display in DISPLAY.items():
            row=by_id.get(connector_id, {})
            started = time.perf_counter()
            checked_at = utcnow()
            try:
                probe = self._live_probe(connector_id)
            except Exception as exc:  # Status rendering must fail closed, never crash on bad configuration.
                probe = {
                    "state": "degraded",
                    "error_code": f"HEALTH_{exc.__class__.__name__.upper()}",
                    "message_zh": "连接器状态检查失败；仍可使用保存当前页面。",
                }
            latency_ms = max(0, round((time.perf_counter() - started) * 1000))
            state = str(probe.get("state") or row.get("state") or "disabled")
            next_action = {
                "healthy":"可直接点击“读取/保存”。","degraded":"首选 Worker 不可用；仍可保存当前页面。运行诊断查看唯一修复动作。",
                "blocked_environment":"尚未配置真实账号或 Worker；先使用保存当前页面，再按向导配置。",
                "paused":"已因配额或安全门暂停；L0/L1 仍可用。","disabled":"该连接器当前关闭；通用保存不受影响。"
            }.get(state,"运行诊断。")
            error_code = probe.get("error_code") or (row.get("last_error_code") if state == row.get("state") else None)
            message = str(probe.get("message_zh") or "")
            if not message and state == row.get("state"):
                message = str(row.get("last_message_zh") or "")
            if not message:
                message = f"状态代码：{error_code}。{next_action}" if error_code else next_action
            result.append({
                "connector_id":connector_id,"display_name":display,"state":state,
                "policy_gate":row.get("policy_gate","pass"),"auth_gate":row.get("auth_gate","pass" if state=="healthy" else "unknown"),
                "technical_gate":row.get("technical_gate", "pass" if state=="healthy" else "unknown"),
                "last_success_at":row.get("last_success_at"),"last_error_code":error_code,
                "last_checked_at":checked_at,"latency_ms":latency_ms,"last_message_zh":message,
                "next_action_zh":next_action
            })
        return result

    def run(self, connector_id: str, request: ConnectorRunRequest) -> tuple[ConnectorResult, list[CaptureRequest]]:
        relation = request.relation_type or DEFAULT_RELATION.get(connector_id, "saved")
        url = str(request.url) if request.url else None
        if connector_id == "x":
            relation = "like" if relation == "like" else "bookmark"
            if not self._x_api_zero_cost_confirmed():
                result = self._x_zero_cost_block()
            else:
                result = XConnector(os.getenv("SOCIAL_ARCHIVE_X_USER_ID"), self._secret("SOCIAL_ARCHIVE_X_OAUTH_TOKEN_FILE")).fetch(relation, request.limit, request.cursor)
        elif connector_id == "reddit":
            relation = "upvoted" if relation == "upvoted" else "saved"
            result = RedditConnector(os.getenv("SOCIAL_ARCHIVE_REDDIT_USERNAME"), os.getenv("SOCIAL_ARCHIVE_REDDIT_USER_AGENT","SocialArchive/0.0.0.6"), self._secret("SOCIAL_ARCHIVE_REDDIT_OAUTH_TOKEN_FILE")).fetch(relation, request.limit, request.cursor)
        elif connector_id == "instagram":
            session = Path(os.getenv("SOCIAL_ARCHIVE_INSTAGRAM_SESSION_FILE", ""))
            result = self.command.instagram_saved(session if session else None, os.getenv("SOCIAL_ARCHIVE_INSTAGRAM_USERNAME"), request.limit)
            relation = "saved"
        elif connector_id == "tiktok":
            if not url:
                raise ValueError("TikTok 需要粘贴一个你本人可访问的链接。")
            result = self.command.capture_url(url, tool="gallery-dl")
        elif connector_id == "bilibili":
            subcommand = {"watch_later":"watch-later","history":"history"}.get(relation, "favorites")
            result = CommandArtifactConnector("bilibili", self.settings.staging_root, worker_url=self.settings.cli_worker_url, worker_token_file=self.settings.cli_worker_token_file, worker_output_root=self.settings.cli_output_root).bilibili_list(subcommand, ["--limit", str(request.limit)])
        elif connector_id in self._connectors:
            if not url:
                raise ValueError(f"{DISPLAY[connector_id]} 需要粘贴一个你本人可访问的链接；账户收藏列表由对应 Worker 的平台向导处理。")
            result = self._connectors[connector_id].capture({"url":url})
            if result.status not in {"success","partial"}:
                worker_errors = list(result.errors)
                for tool in ("gallery-dl", "yt-dlp"):
                    fallback = self.command.capture_url(url, tool=tool)
                    if fallback.status == "success":
                        fallback.connector_id = connector_id
                        fallback.scan_receipt["fallback_from_worker"] = True
                        fallback.errors = worker_errors
                        result = fallback
                        break
        elif connector_id == "generic-web":
            if not url:
                raise ValueError("通用网页需要粘贴链接。")
            result = ConnectorResult("generic-web", "manual", "success", observations=[{"url":url}], scan_receipt={"completeness":"complete","item_count":1,"scope":"item"})
            relation = "manual_save"
        else:
            raise ValueError("未知平台连接器。")

        account_scope = request.source_account_id or ""
        scope = "account_relation" if connector_id in {"x", "reddit", "instagram", "bilibili"} else "item"
        result.scan_receipt.setdefault("scope", scope)
        result.scan_receipt.setdefault("relation_type", relation)
        result.scan_receipt.setdefault("collection_key", request.collection_key)
        result.scan_receipt.setdefault("source_account_id", account_scope)
        captures = self._normalize(connector_id, relation, request, result)
        return result, captures

    def _normalize(self, connector_id: str, relation: str, request: ConnectorRunRequest, result: ConnectorResult) -> list[CaptureRequest]:
        captures: list[CaptureRequest] = []
        fallback_url = str(request.url) if request.url else None
        for obs in result.observations:
            if not isinstance(obs, dict):
                continue
            external_id = str(obs.get("id") or obs.get("name") or "") or None
            title = obs.get("title") or obs.get("full_text") or obs.get("text")
            text = obs.get("selftext") or obs.get("text") or obs.get("raw_text")
            author = obs.get("author_name") or obs.get("author") or obs.get("author_id")
            observed_url = obs.get("url") or obs.get("canonical_url")
            if connector_id == "x" and external_id:
                observed_url = f"https://x.com/i/web/status/{external_id}"
            elif connector_id == "reddit" and obs.get("permalink"):
                observed_url = f"https://www.reddit.com{obs['permalink']}"
            elif connector_id == "bilibili" and (obs.get("bvid") or obs.get("bv_id")):
                observed_url = f"https://www.bilibili.com/video/{obs.get('bvid') or obs.get('bv_id')}"
            observed_url = observed_url or fallback_url
            if not observed_url:
                continue
            media_urls: list[str] = []
            for key in ("media_url", "video_url", "download_url"):
                if obs.get(key):
                    media_urls.append(str(obs[key]))
            captures.append(CaptureRequest(
                platform=connector_id, url=str(observed_url), external_content_id=external_id,
                relation_type=relation, collection_key=request.collection_key, source_account_id=request.source_account_id,
                title=str(title)[:2048] if title is not None else None,
                author_name=str(author)[:1024] if author is not None else None,
                text=str(text)[:2_000_000] if text is not None else None,
                media_urls=media_urls, raw_metadata={"connector_run_id":result.run_id,"source_observation":obs},
                requested_levels=request.requested_levels, destination_ids=request.destination_ids,
            ))
        return captures
