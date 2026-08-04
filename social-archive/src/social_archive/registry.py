from __future__ import annotations

import os
import re
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

    # 已连接账号的 external_account_id 有可能是占位值而不是真身份。
    # 浏览器会话连接在拿不到真实账号名时写的是 `browser-session:{platform}`；
    # Chrome 书签那条固定写 `chrome-bookmarks`。这两种都不能当平台身份用。
    _PLACEHOLDER_ACCOUNT_IDS = frozenset({"chrome-bookmarks"})
    _PLACEHOLDER_ACCOUNT_PREFIXES = ("browser-session:",)
    # 每个平台对身份的形状要求不同，先验形状再用。形状不对就退回环境变量，
    # 而不是拿一个明显不对的值去请求平台——那会换来一个 404，
    # 而 404 的文案说的是"接口失败"，不是"我们不知道你是谁"。
    _IDENTITY_SHAPE = {
        "x": re.compile(r"\A[0-9]{1,32}\Z"),           # X API v2 用数字 user id
        "reddit": re.compile(r"\A[A-Za-z0-9_-]{3,20}\Z"),
        "instagram": re.compile(r"\A[A-Za-z0-9_.]{1,30}\Z"),
    }

    @classmethod
    def _account_identity(cls, connector_id: str, request: ConnectorRunRequest, env_name: str) -> str | None:
        """平台身份优先取**这次运行绑定的那个已连接账号**，环境变量只兜底。

        为什么这样改：`ConnectorRunRequest.source_account_id` 一直带着已连接账号的
        external_account_id 传进来，而这三个分支从来没看过它，一律去读环境变量。
        那四个环境变量在 .env.example、compose、部署脚本、文档里**一处都没有**
        （scripts/find_settings_with_no_way_to_set_them.py 抓到的），
        于是 Owner 把该做的都做对了——部署、登录、连接账号——这三个平台的
        服务端同步仍然一条都取不到，而没有任何文档告诉他还差什么。

        身份本来就该来自"你连的那个账号"，而不是一个部署时手填的变量。
        """
        external = str(getattr(request, "source_account_id", "") or "").strip()
        shape = cls._IDENTITY_SHAPE.get(connector_id)
        if (
            external
            and external not in cls._PLACEHOLDER_ACCOUNT_IDS
            and not external.startswith(cls._PLACEHOLDER_ACCOUNT_PREFIXES)
            and (shape is None or shape.fullmatch(external))
        ):
            return external
        return os.getenv(env_name)

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
            return RedditConnector(os.getenv("SOCIAL_ARCHIVE_REDDIT_USERNAME"), os.getenv("SOCIAL_ARCHIVE_REDDIT_USER_AGENT","SocialArchive/0.0.0.7"), self._secret("SOCIAL_ARCHIVE_REDDIT_OAUTH_TOKEN_FILE")).health()
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
        # **函数内导入是为了断开循环**：account_sync 需要 ConnectorRegistry，
        # 这里又需要它的能力声明。放到模块顶部会让 registry 变成
        # partially initialized module（实测：22 个测试集体 ImportError）。
        # 另一条路是把这两个常量挪进一个无依赖的小模块——但那样会出现
        # 两个名字指同一件事，而"两份必然漂开"是这一天反复吃过的亏。
        from .account_sync import NOT_SYNCABLE_YET, SYNCABLE_NOW

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
                    # 同上：稳定码 + 类名进 message，不要用类名当码
                    "error_code": "HEALTH_PROBE_FAILED",
                    "message_zh": "连接器状态检查失败；仍可使用保存当前页面。",
                    "detail": exc.__class__.__name__,
                }
            latency_ms = max(0, round((time.perf_counter() - started) * 1000))
            state = str(probe.get("state") or row.get("state") or "disabled")
            # **连接器的健康度不许比产品自己的能力声明更乐观。**
            #
            # 2026-08-05 生产实测，这份视图说：
            #     instagram  healthy  「可直接点击"读取/保存"。」
            #     bilibili   healthy  「可直接点击"读取/保存"。」
            #     tiktok     healthy  「可直接点击"读取/保存"。」
            # 而真跑一次：instagram → INSTAGRAM_SIDECAR_BLOCKED（session 是空的）、
            # bilibili → BILI_SIDECAR_BLOCKED。tiktok 甚至不在 PLATFORM_RELATIONS 里，
            # 界面上根本没有它。
            #
            # 根因：这三个的探针是 `self.command.health()`——它测的是
            # **「CLI sidecar 活着吗」**，不是「这个连接器干得成活吗」。
            # sidecar 活着，于是三个都报 healthy。
            #
            # 真正的前置条件（instagram 的 session、bilibili 的登录态）没法在
            # 状态探针里廉价地验——真验就得跑一次取数。所以这里换个判法：
            # **产品已经在 SYNCABLE_NOW 里声明过哪些平台现在同步得动**，
            # 连接器视图不得比那份声明更乐观。同一处真源，同一句中文。
            #
            # 这是同一种病的第四处：前三处是「立即同步」按钮、连接入口、
            # 目的地「自动导入」。
            # 已经是 blocked 的也要换文案：实测 x 那一条显示的是
            #     「状态代码：X_ZERO_COST_NOT_CONFIRMED。尚未配置真实账号或
            #      Worker；先使用保存当前页面，再按向导配置。」
            # ——把失败码摆给用户看，还叫他「按向导配置」，**而没有任何向导
            # 能打开那道零费用门**（那是 Owner 的花钱判断）。真实原因写在
            # NOT_SYNCABLE_YET 里，含「现在可以：…」那半句。
            if connector_id in NOT_SYNCABLE_YET:
                # **同一处境，只能有一个状态。** 修完第一版之后生产上是这样：
                #     bilibili / instagram   blocked_environment
                #     xiaohongshu/douyin/快手 degraded
                # 同样是「本版本读不了」，却分成两种。`degraded` 读起来像
                # 「暂时不行、待会儿再试」，而这件事重试多少次都一样。
                # 一律按 blocked_environment 呈现。
                state = "blocked_environment"
                probe = {
                    **probe,
                    "state": state,
                    "error_code": probe.get("error_code") or "PLATFORM_NOT_SYNCABLE_YET",
                    "message_zh": NOT_SYNCABLE_YET[connector_id],
                }
            elif state == "healthy" and connector_id not in SYNCABLE_NOW:
                # 不在任何一张表里的（例如 tiktok，它连 PLATFORM_RELATIONS 都不在）
                state = "blocked_environment"
                probe = {
                    **probe,
                    "state": state,
                    "error_code": probe.get("error_code") or "PLATFORM_NOT_SYNCABLE_YET",
                    "message_zh": "本版本还不能自动读取这个平台的内容。",
                }
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
                result = XConnector(self._account_identity("x", request, "SOCIAL_ARCHIVE_X_USER_ID"), self._secret("SOCIAL_ARCHIVE_X_OAUTH_TOKEN_FILE")).fetch(relation, request.limit, request.cursor)
        elif connector_id == "reddit":
            relation = "upvoted" if relation == "upvoted" else "saved"
            result = RedditConnector(self._account_identity("reddit", request, "SOCIAL_ARCHIVE_REDDIT_USERNAME"), os.getenv("SOCIAL_ARCHIVE_REDDIT_USER_AGENT","SocialArchive/0.0.0.7"), self._secret("SOCIAL_ARCHIVE_REDDIT_OAUTH_TOKEN_FILE")).fetch(relation, request.limit, request.cursor)
        elif connector_id == "instagram":
            session = Path(os.getenv("SOCIAL_ARCHIVE_INSTAGRAM_SESSION_FILE", ""))
            result = self.command.instagram_saved(session if session else None, self._account_identity("instagram", request, "SOCIAL_ARCHIVE_INSTAGRAM_USERNAME"), request.limit)
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
