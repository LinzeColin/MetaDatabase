from __future__ import annotations

import base64
import errno
import hashlib
import json
import time
import urllib.parse
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

import httpx

from .config import Settings
from .db import RuntimeStore
from .utils import atomic_write, read_secret, safe_slug, sha256_bytes, utcnow


PRIVATE_DATABASE_REPOSITORY = "LinzeColin/Private-Database"
PRIVATE_DATABASE_AREA = "Private-MetaDatabase"
DESTINATION_IDS = (
    "social_archive",
    "markdown",
    "obsidian",
    "notion",
    "github",
    "karakeep",
    "linkwarden",
    "archivebox",
)
EXPORT_DESTINATION_IDS = frozenset(DESTINATION_IDS) - {"social_archive"}


def _git_blob_sha(data: bytes) -> str:
    """Return the Git blob SHA used by the Contents API for an exact payload."""
    return hashlib.sha1(b"blob %d\0" % len(data) + data).hexdigest()


@dataclass(frozen=True)
class DestinationView:
    destination_id: str
    display_name: str
    state: str
    enabled: bool
    configured: bool
    authorized: bool
    automatic: bool
    next_action_zh: str
    privacy_note_zh: str
    last_checked_at: str | None = None
    latency_ms: int | None = None
    capabilities: dict[str, Any] | None = None
    last_message_zh: str | None = None
    # **收到了多少条**。「连上了」不等于「收到了」——2026-08-04 实测，
    # github 与 obsidian 都是 connected +「最近一次自动导入成功。」，
    # 而各自只有 1 条回执，库里有 193 条。
    exported_count: int = 0
    content_total: int = 0

    def as_dict(self) -> dict[str, Any]:
        return {
            "destination_id": self.destination_id,
            "display_name": self.display_name,
            "state": self.state,
            "enabled": self.enabled,
            "configured": self.configured,
            "authorized": self.authorized,
            "exported_count": self.exported_count,
            "content_total": self.content_total,
            "coverage_zh": (
                "这里是主保存链路，全部内容都在。" if self.destination_id == "social_archive"
                else f"已送到这里 {self.exported_count} / {self.content_total} 条。"
                if self.content_total else "库里还没有内容。"
            ),
            "automatic": self.automatic,
            "next_action_zh": self.next_action_zh,
            "privacy_note_zh": self.privacy_note_zh,
            "last_checked_at": self.last_checked_at,
            "latency_ms": self.latency_ms,
            "capabilities": self.capabilities or {},
            "last_message_zh": self.last_message_zh,
        }


class DestinationError(RuntimeError):
    def __init__(self, message: str, *, state: str = "degraded", code: str = "DESTINATION_ERROR"):
        super().__init__(message)
        self.state = state
        self.code = code


def retry_after_seconds_from_error(exc: Exception) -> int | None:
    """Return a bounded Notion Retry-After delay for a retryable rate limit."""
    if not isinstance(exc, httpx.HTTPStatusError) or exc.response.status_code != 429:
        return None
    raw = exc.response.headers.get("Retry-After", "").strip()
    try:
        return min(max(int(raw), 1), 3600)
    except ValueError:
        return None


def _markdown(content: dict[str, Any]) -> str:
    title = str(content.get("title") or content.get("canonical_url") or content["id"])
    metadata = {
        "social_archive_id": content["id"],
        "platform": content.get("platform"),
        "url": content.get("canonical_url"),
        "author": content.get("author_name"),
        "published_at": content.get("published_at"),
        "relation_types": sorted({r.get("relation_type") for r in content.get("relations", []) if r.get("relation_type")}),
        "collections": sorted({r.get("collection_key") for r in content.get("relations", []) if r.get("collection_key")}),
    }
    lines = ["---"]
    lines.extend(f"{key}: {json.dumps(value, ensure_ascii=False)}" for key, value in metadata.items())
    lines.extend(["---", "", f"# {title}", "", f"原始链接：{content.get('canonical_url') or ''}", ""])
    body = str(content.get("body") or "")
    raw = content.get("metadata_json")
    if not body and raw:
        try:
            body = str(json.loads(raw).get("text") or "")
        except (ValueError, TypeError, AttributeError):
            body = ""
    if body:
        lines.extend([body, ""])
    lines.extend(["## 归档状态", ""])
    for artifact in content.get("artifacts", []):
        lines.append(f"- {artifact.get('archive_level')} · {artifact.get('artifact_type')} · {artifact.get('status')}")
    return "\n".join(lines).rstrip() + "\n"


class DestinationRegistry:
    """E2N-style destination adapters with active probes, receipts and idempotent bindings.

    Secrets are read only from local 0600 files. A configured destination is never
    displayed as connected until a real write/read or provider probe succeeds.
    """

    def __init__(
        self,
        settings: Settings,
        store: RuntimeStore,
        *,
        client_factory: Callable[..., httpx.Client] | None = None,
    ):
        self.settings = settings
        self.store = store
        self._client_factory = client_factory or httpx.Client

    def _client(self, **kwargs: Any) -> httpx.Client:
        return self._client_factory(**kwargs)

    def _configured(self, destination_id: str) -> bool:
        if destination_id in {"social_archive", "markdown"}:
            return True
        if destination_id == "obsidian":
            return self._obsidian_configured()
        if destination_id == "notion":
            return self._notion_configured()
        if destination_id == "github":
            return self._github_configured()
        if destination_id == "karakeep":
            return bool(self.settings.karakeep_url and read_secret(self.settings.karakeep_token_file))
        if destination_id == "linkwarden":
            return bool(self.settings.linkwarden_url and read_secret(self.settings.linkwarden_token_file))
        if destination_id == "archivebox":
            return True
        return False

    @staticmethod
    def _display_name(destination_id: str) -> str:
        return {
            "social_archive": "Social Archive",
            "markdown": "Markdown 文件",
            "obsidian": "Obsidian",
            "notion": "Notion",
            "github": "GitHub 私有 Markdown",
            "karakeep": "Karakeep 阅读器",
            "linkwarden": "Linkwarden 阅读器",
            "archivebox": "ArchiveBox URL 队列",
        }.get(destination_id, destination_id)

    def _privacy_note(self, destination_id: str) -> str:
        return {
            "social_archive": "所有内容先进入私人档案馆；这是唯一主保存链路。",
            "markdown": f"自动写入 {self.settings.export_root / 'markdown'}，可随时迁移。",
            "obsidian": "优先直写用户选择的 Vault；REST 令牌只从 0600 Secret 读取。",
            "notion": "Integration Token 只从服务端 0600 Secret 读取，不返回扩展。",
            "github": "只允许私有仓库；Git 树存 Markdown/清单，L3 对象走加密副本。",
            "karakeep": "仅发送 URL 到独立 Karakeep；Social Archive 仍是唯一事实源。",
            "linkwarden": "仅发送 URL 到独立 Linkwarden；投影可删除和重建。",
            "archivebox": "只写入可重放 URL 队列；ArchiveBox 0.7.4 不作为权威数据库。",
        }.get(destination_id, "")

    def _default_next_action(self, destination_id: str, configured: bool, state: str) -> str:
        if destination_id == "social_archive":
            return "无需设置"
        if state == "connected":
            return "连接已实测，可自动导入"
        if destination_id == "markdown":
            return "点击“检查连接”确认本机 Markdown 写入和回读权限。"
        if configured:
            return "配置已保存；点击“检查连接”完成授权验证"
        return {
            "obsidian": "选择 Vault 文件夹，或配置 Local REST API 4.1.3 及以上版本。",
            "notion": "创建免费 Integration，共享目标数据源，再填写 Secret 与 data_source_id。",
            "github": "选择私有仓库并提供 Contents 读写的 Fine-grained Token。",
            "karakeep": "启动 Karakeep，在设置中生成 API Key 并保存到 0600 Secret。",
            "linkwarden": "启动 Linkwarden，在设置中生成 Token 并保存到 0600 Secret。",
            "archivebox": "点击“检查连接”确认本机可重放 URL 队列可写。",
        }.get(destination_id, "完成一次连接设置")

    @staticmethod
    def known_destination_ids() -> tuple[str, ...]:
        return DESTINATION_IDS

    def known_ids(self) -> frozenset[str]:
        """所有认得的目的地 id。接口层用它把「不存在」和「没授权」分开报。"""
        return frozenset(DESTINATION_IDS)

    def is_export_authorized(self, destination_id: str, *, allow_recovery: bool = False) -> bool:
        """Return whether a destination passed a current active authorization gate.

        Configuration alone is deliberately insufficient.  The persisted connected
        state must originate from a successful Probe or a confirmed export, and the
        live configuration must still be present when a job is about to leave the
        Canonical Store.
        """
        destination_id = destination_id.strip().lower()
        if destination_id == "social_archive":
            return True
        if destination_id not in EXPORT_DESTINATION_IDS:
            return False
        try:
            configured = self._configured(destination_id)
        except (ValueError, OSError, PermissionError):
            return False
        if not configured:
            return False
        states = {row["destination_id"]: row for row in self.store.destination_states()}
        row = states.get(destination_id)
        if not row or not row.get("enabled") or not row.get("last_checked_at"):
            return False
        if row.get("state") == "connected":
            return True
        # A transient provider failure changes health to degraded but does not
        # revoke the already-confirmed authorization. Existing failed jobs may
        # therefore recover; new captures still require a connected state.
        return bool(allow_recovery and row.get("state") == "degraded" and row.get("last_success_at"))

    def require_export_authorization(self, destination_id: str, *, allow_recovery: bool = False) -> None:
        """Fail closed before an asynchronous export can contact a destination."""
        destination_id = destination_id.strip().lower()
        if destination_id == "social_archive":
            return
        if destination_id not in EXPORT_DESTINATION_IDS:
            raise ValueError(f"未知目的地：{destination_id}")
        if self.is_export_authorized(destination_id, allow_recovery=allow_recovery):
            return
        states = {row["destination_id"]: row for row in self.store.destination_states()}
        persisted_state = str((states.get(destination_id) or {}).get("state") or "needs_user_action")
        state = persisted_state if persisted_state in {"expired", "blocked_policy"} else "needs_user_action"
        try:
            configured = self._configured(destination_id)
        except (ValueError, OSError, PermissionError):
            configured = False
        code = "DESTINATION_NOT_CONFIGURED" if not configured else "DESTINATION_PROBE_REQUIRED"
        raise DestinationError(
            "目的地尚未完成主动连接检查或授权已失效；请先点击“检查连接”。",
            state=state,
            code=code,
        )

    def views(self) -> list[dict[str, Any]]:
        persisted = {row["destination_id"]: row for row in self.store.destination_states()}
        # **「连上了」和「收到了多少」是两件事。** 见 db.destination_coverage 的说明。
        coverage = self.store.destination_coverage()
        total = self.store.content_total()
        result: list[dict[str, Any]] = []
        for destination_id in ("social_archive", "markdown", "notion", "obsidian", "github", "karakeep", "linkwarden", "archivebox"):
            configuration_error: str | None = None
            try:
                configured = self._configured(destination_id)
            except (ValueError, OSError, PermissionError) as exc:
                configured = False
                configuration_error = str(exc)
            local_always_ready = destination_id == "social_archive"
            row = persisted.get(destination_id) or {}
            state = str(row.get("state") or ("connected" if local_always_ready else "needs_user_action"))
            if not configured and not local_always_ready:
                state = "needs_user_action"
            authorized = self.is_export_authorized(destination_id)
            message = configuration_error or row.get("last_message_zh")
            next_action = str(message or self._default_next_action(destination_id, configured, state))
            exported = total if destination_id == "social_archive" else coverage.get(destination_id, 0)
            # **数字诚实了，下一步还在说「一切正常」。**
            #
            # 2026-08-04 那次修的是 coverage_zh，让它照实说「已送到 1 / 193 条」。
            # 但 next_action 没动。2026-08-05 生产实测，Owner 看到的是：
            #
            #   Obsidian    已送到 1 / 193 条    下一步：最近一次自动导入成功。
            #   ArchiveBox  已送到 0 / 193 条    下一步：连接检查通过，可以自动导入。
            #
            # 两句下一步单独看都是真的——最近那一次确实成功、连接确实通过——
            # **而它们把「192 条从来没到过这里」说成了「一切正常」**。
            # 他没有技术背景，读到「导入成功」就不会再往下想。
            #
            # 差额不是错误，是**投递只在新内容进来时发生**：他后来才连上的目的地，
            # 先前入库的内容不会自己追上去。所以这里不改状态、不报错，
            # 只把那个差额和它的成因摆到下一步里，并给出补投那条命令。
            if authorized and total and exported < total and destination_id != "social_archive":
                next_action = (
                    f"**还有 {total - exported} 条从来没送到这里。** "
                    "自动投递只在新内容进来时发生，先前入库的不会自己追上去。"
                    "要补投，在服务器上跑一次："
                    f"docker compose exec core-api python /app/scripts/backfill_destination.py "
                    f"--destination {destination_id} --apply"
                    f"（原本的状态：{next_action}）"
                )
            result.append(
                DestinationView(
                    destination_id=destination_id,
                    display_name=self._display_name(destination_id),
                    state=state,
                    enabled=local_always_ready or bool(row.get("enabled")) or configured,
                    configured=configured,
                    authorized=authorized,
                    automatic=authorized,
                    next_action_zh=next_action,
                    privacy_note_zh=self._privacy_note(destination_id),
                    last_checked_at=row.get("last_checked_at"),
                    latency_ms=row.get("latency_ms"),
                    capabilities=row.get("capabilities") or {},
                    last_message_zh=message,
                    exported_count=exported,
                    content_total=total,
                ).as_dict()
            )
        return result

    def probe(self, destination_id: str) -> dict[str, Any]:
        destination_id = destination_id.strip().lower()
        if destination_id not in DESTINATION_IDS:
            raise ValueError(f"未知目的地：{destination_id}")
        try:
            configured = self._configured(destination_id)
            configuration_error = None
        except (ValueError, OSError, PermissionError) as exc:
            configured = False
            configuration_error = str(exc)
        if not configured:
            message = configuration_error or self._default_next_action(destination_id, False, "needs_user_action")
            self.store.upsert_destination_state(
                destination_id,
                state="needs_user_action",
                enabled=False,
                error_code="INVALID_CONFIGURATION" if configuration_error else "NOT_CONFIGURED",
                last_checked_at=utcnow(),
                latency_ms=0,
                capabilities={},
                message_zh=message,
            )
            return self._view(destination_id)

        self.store.upsert_destination_state(
            destination_id,
            state="checking",
            enabled=True,
            message_zh="正在检查真实连接…",
        )
        started = time.perf_counter()
        checked_at = utcnow()
        try:
            if destination_id == "social_archive":
                capabilities = self._probe_social_archive()
            elif destination_id == "markdown":
                capabilities = self._probe_markdown()
            elif destination_id == "obsidian":
                capabilities = self._probe_obsidian()
            elif destination_id == "notion":
                capabilities = self._probe_notion()
            elif destination_id == "github":
                capabilities = self._probe_github()
            elif destination_id == "karakeep":
                capabilities = self._probe_karakeep()
            elif destination_id == "linkwarden":
                capabilities = self._probe_linkwarden()
            else:
                capabilities = self._probe_archivebox()
            latency_ms = max(0, round((time.perf_counter() - started) * 1000))
            message = "连接检查通过，可以自动导入。"
            self.store.upsert_destination_state(
                destination_id,
                state="connected",
                enabled=True,
                last_checked_at=checked_at,
                latency_ms=latency_ms,
                capabilities=capabilities,
                message_zh=message,
            )
        except DestinationError as exc:
            latency_ms = max(0, round((time.perf_counter() - started) * 1000))
            self.store.upsert_destination_state(
                destination_id,
                state=exc.state,
                enabled=True,
                error_code=exc.code,
                last_checked_at=checked_at,
                latency_ms=latency_ms,
                capabilities={},
                message_zh=str(exc),
            )
        except (ValueError, OSError, PermissionError, httpx.HTTPError) as exc:
            latency_ms = max(0, round((time.perf_counter() - started) * 1000))
            state, code, message = self._failure_details(exc)
            self.store.upsert_destination_state(
                destination_id,
                state=state,
                enabled=True,
                error_code=code,
                last_checked_at=checked_at,
                latency_ms=latency_ms,
                capabilities={},
                message_zh=message,
            )
        return self._view(destination_id)

    def _view(self, destination_id: str) -> dict[str, Any]:
        return next(item for item in self.views() if item["destination_id"] == destination_id)

    @staticmethod
    def _failure_details(exc: Exception) -> tuple[str, str, str]:
        if isinstance(exc, httpx.HTTPStatusError):
            status = exc.response.status_code
            if status in {401, 403}:
                return "expired", f"HTTP_{status}", "授权无效或权限不足；请重新授权后再检查。"
            if status == 404:
                return "needs_user_action", "HTTP_404", "目标不存在或尚未共享给当前授权。"
            return "degraded", f"HTTP_{status}", f"目的地返回 HTTP {status}；请检查服务状态。"
        if isinstance(exc, PermissionError):
            return "needs_user_action", "SECRET_OR_PATH_PERMISSION", str(exc)
        if isinstance(exc, ValueError):
            return "needs_user_action", "INVALID_CONFIGURATION", str(exc)
        # **不要拿 Python 类名当失败码。** 它对用户没有意义、泄漏实现，
        # 而且是个无限集合——文案词典永远追不上，于是界面只能说
        # 「我们没能记录下原因」，而原因就在异常里。
        # 生产实测：connector_state 里躺着 CONNECTORERROR，正是这么来的。
        # 类名留在 message 里给日志看，码用稳定的那个。
        return "degraded", "DESTINATION_PROBE_FAILED", f"连接失败（{exc.__class__.__name__}）：{exc}"

    @staticmethod
    def _is_item_scoped_failure(exc: Exception) -> bool:
        """这条错说的是**这一条内容**，还是**这个目的地**？

        2026-08-03T17:23 生产上：一条抖音长标题拼出的文件名超过了文件系统
        255 字节的上限，抛 `OSError [Errno 36] File name too long`。

        那条错走的是「目的地健康度」这条路，把整个 markdown 目的地降级；
        之后每一条新内容都被授权闸门挡下。结果：**193 条内容里 79 条
        再也没有导出过**，而界面给的原因是「请先点击『检查连接』」——
        指错了方向，照着做也修不好（下一个长标题会再炸一次）。

        目的地本身好得很：同一秒之前它刚成功写了 110 个文件。
        坏的是这一条内容的名字。

        **判据只放行 ENAMETOOLONG 这一种。** 其余的 OSError
        （权限、磁盘满、只读文件系统、IO 错误）确实意味着目的地不健康，
        必须继续降级——放宽这里等于把真正的故障藏起来。
        """
        return isinstance(exc, OSError) and exc.errno == errno.ENAMETOOLONG

    def _record_export_failure(
        self,
        *,
        destination_id: str,
        content_id: str,
        projection_sha256: str,
        attempted_at: str,
        job_id: str | None,
        exc: Exception,
    ) -> str:
        state, code, message = (
            (exc.state, exc.code, str(exc)) if isinstance(exc, DestinationError) else self._failure_details(exc)
        )
        # A Notion page may already be durably checkpointed when a later Block
        # call fails. Keep that confirmed identity on the failed receipt so a
        # recovery never has to infer it from an exception or create another Page.
        failed_binding = self.store.get_destination_binding(destination_id, content_id)
        retry_after_seconds = retry_after_seconds_from_error(exc)
        failure_evidence: dict[str, Any] = {"retryable": state == "degraded"}
        if retry_after_seconds is not None:
            failure_evidence["retry_after_seconds"] = retry_after_seconds
        receipt_id = self.store.record_destination_receipt(
            destination_id=destination_id,
            content_id=content_id,
            status="failed",
            projection_sha256=projection_sha256,
            attempted_at=attempted_at,
            message_zh=message,
            job_id=job_id,
            remote_id=(failed_binding or {}).get("remote_id"),
            remote_path=(failed_binding or {}).get("remote_path"),
            error_code=code,
            evidence=failure_evidence,
        )
        # **单条内容的问题不改目的地的健康度。** 见 _is_item_scoped_failure。
        if not self._is_item_scoped_failure(exc):
            self.store.upsert_destination_state(
                destination_id,
                state=state,
                enabled=True,
                error_code=code,
                last_checked_at=utcnow(),
                message_zh=message,
            )
        return receipt_id

    def export(
        self,
        destination_id: str,
        content_id: str,
        *,
        job_id: str | None = None,
        allow_recovery: bool = False,
    ) -> dict[str, Any]:
        content = self.store.get_content(content_id)
        if not content:
            raise ValueError("内容不存在")
        destination_id = destination_id.lower()
        if destination_id == "social_archive":
            return {"destination_id": destination_id, "status": "done", "content_id": content_id}
        if destination_id not in EXPORT_DESTINATION_IDS:
            raise ValueError(f"未知目的地：{destination_id}")

        markdown = _markdown(content)
        projection_sha256 = sha256_bytes(markdown.encode("utf-8"))
        binding = self.store.get_destination_binding(destination_id, content_id)
        attempted_at = utcnow()
        try:
            self.require_export_authorization(destination_id, allow_recovery=allow_recovery)
        except (DestinationError, ValueError, OSError, PermissionError, httpx.HTTPError) as exc:
            receipt_id = self._record_export_failure(
                destination_id=destination_id,
                content_id=content_id,
                projection_sha256=projection_sha256,
                attempted_at=attempted_at,
                job_id=job_id,
                exc=exc,
            )
            setattr(exc, "receipt_id", receipt_id)
            raise
        # GitHub is the durable Private-Database destination.  Its remote state
        # must be reconciled on every attempt: a local binding alone cannot
        # prove that the repository is still private or that the file remains
        # present.  Other projection-only destinations can use their local
        # binding as their idempotency boundary.
        if destination_id != "github" and binding and binding.get("projection_sha256") == projection_sha256:
            receipt_id = self.store.record_destination_receipt(
                destination_id=destination_id,
                content_id=content_id,
                status="noop",
                projection_sha256=projection_sha256,
                attempted_at=attempted_at,
                message_zh="内容未变化，未重复写入。",
                job_id=job_id,
                remote_id=binding.get("remote_id"),
                remote_path=binding.get("remote_path"),
                evidence={"idempotent": True},
            )
            return {
                "destination_id": destination_id,
                "status": "noop",
                "content_id": content_id,
                "receipt_id": receipt_id,
                "remote_id": binding.get("remote_id"),
                "path": binding.get("remote_path"),
            }

        try:
            if destination_id == "markdown":
                result = self._write_markdown(content, markdown, self.settings.export_root / "markdown")
            elif destination_id == "obsidian":
                result = self._export_obsidian(content, markdown)
            elif destination_id == "notion":
                result = self._export_notion(content, markdown, binding)
            elif destination_id == "github":
                result = self._export_github(content, markdown)
            elif destination_id == "karakeep":
                result = self._export_karakeep(content)
            elif destination_id == "linkwarden":
                result = self._export_linkwarden(content)
            else:
                result = self._export_archivebox(content)
            remote_id = result.get("remote_id") or result.get("commit_sha")
            remote_path = result.get("path") or result.get("remote_path")
            metadata = result.get("binding_metadata") or {}
            provider_status = str(result.get("status") or "done")
            if provider_status not in {"done", "noop"}:
                raise DestinationError(
                    f"目的地返回了未知完成状态：{provider_status}",
                    code="DESTINATION_INVALID_COMPLETION_STATUS",
                )
            self.store.upsert_destination_binding(
                destination_id=destination_id,
                content_id=content_id,
                projection_sha256=projection_sha256,
                remote_id=remote_id,
                remote_path=remote_path,
                metadata=metadata,
            )
            receipt_id = self.store.record_destination_receipt(
                destination_id=destination_id,
                content_id=content_id,
                status=provider_status,
                projection_sha256=projection_sha256,
                attempted_at=attempted_at,
                message_zh="内容未变化，未重复写入。" if provider_status == "noop" else "导入完成。",
                job_id=job_id,
                remote_id=remote_id,
                remote_path=remote_path,
                evidence={"idempotent_binding": True, "provider_status": provider_status},
            )
            self.store.upsert_destination_state(
                destination_id,
                state="connected",
                enabled=True,
                last_checked_at=utcnow(),
                message_zh="最近一次自动导入成功。",
            )
            return {**result, "receipt_id": receipt_id, "projection_sha256": projection_sha256}
        except (DestinationError, ValueError, OSError, PermissionError, httpx.HTTPError) as exc:
            receipt_id = self._record_export_failure(
                destination_id=destination_id,
                content_id=content_id,
                projection_sha256=projection_sha256,
                attempted_at=attempted_at,
                job_id=job_id,
                exc=exc,
            )
            setattr(exc, "receipt_id", receipt_id)
            raise

    def _probe_social_archive(self) -> dict[str, Any]:
        with self.store.connection() as con:
            con.execute("SELECT 1").fetchone()
        return {"canonical_store": True, "write": True}

    def _probe_markdown(self) -> dict[str, Any]:
        root = self.settings.export_root / "markdown"
        path = root / ".social-archive-write-probe"
        atomic_write(path, b"social-archive-probe\n")
        if path.read_bytes() != b"social-archive-probe\n":
            raise DestinationError("Markdown 写入后回读不一致。", code="MARKDOWN_READBACK_MISMATCH")
        path.unlink(missing_ok=True)
        return {"write": True, "readback": True, "root": str(root)}

    def _write_markdown(self, content: dict[str, Any], markdown: str, root: Path) -> dict[str, Any]:
        platform = safe_slug(str(content.get("platform") or "unknown"))
        title = safe_slug(str(content.get("title") or content["id"]), content["id"])
        path = root / platform / f"{title}-{content['id'][-8:]}.md"
        atomic_write(path, markdown.encode("utf-8"))
        if path.read_text(encoding="utf-8") != markdown:
            raise DestinationError("Markdown 写入后回读不一致。", code="MARKDOWN_READBACK_MISMATCH")
        return {"destination_id": "markdown", "status": "done", "path": str(path), "content_id": content["id"]}

    def _obsidian_configured(self) -> bool:
        if self.settings.obsidian_vault_root:
            return True
        return bool(self.settings.obsidian_rest_url and read_secret(self.settings.obsidian_rest_token_file))

    def _notion_configured(self) -> bool:
        return bool(
            (self.settings.notion_data_source_id or self.settings.notion_database_id)
            and read_secret(self.settings.notion_token_file)
        )

    def _github_configured(self) -> bool:
        return bool(self.settings.github_repository and read_secret(self.settings.github_token_file))

    def _github_repository(self) -> str:
        repository = (self.settings.github_repository or "").strip()
        if not repository or "/" not in repository:
            raise ValueError("GitHub Private-Database 尚未配置")
        if repository != PRIVATE_DATABASE_REPOSITORY:
            raise DestinationError(
                f"GitHub Markdown 目的地只能写入 {PRIVATE_DATABASE_REPOSITORY}。",
                state="blocked_policy",
                code="GITHUB_PRIVATE_DATABASE_TARGET_MISMATCH",
            )
        return repository

    def _obsidian_verify(self) -> str | bool:
        return self.settings.obsidian_rest_ca_file or True

    @staticmethod
    def _version_tuple(value: str) -> tuple[int, int, int] | None:
        parts = value.strip().lstrip("v").split(".")
        if len(parts) < 3:
            return None
        try:
            return tuple(int(part.split("-")[0]) for part in parts[:3])  # type: ignore[return-value]
        except ValueError:
            return None

    def _probe_obsidian(self) -> dict[str, Any]:
        if self.settings.obsidian_vault_root:
            root = self.settings.obsidian_vault_root / "Social Archive"
            path = root / ".social-archive-write-probe.md"
            atomic_write(path, b"Social Archive probe\n")
            if path.read_bytes() != b"Social Archive probe\n":
                raise DestinationError("Obsidian Vault 写入后回读不一致。", code="OBSIDIAN_READBACK_MISMATCH")
            path.unlink(missing_ok=True)
            return {"mode": "vault", "write": True, "readback": True, "root": str(root)}
        if not self.settings.obsidian_rest_url:
            raise ValueError("Obsidian 尚未配置")
        token = read_secret(self.settings.obsidian_rest_token_file)
        if not token:
            raise ValueError("Obsidian REST Token 缺失")
        headers = {"Authorization": f"Bearer {token}"}
        base = self.settings.obsidian_rest_url.rstrip("/")
        with self._client(timeout=15.0, verify=self._obsidian_verify()) as client:
            root_response = client.get(base + "/", headers=headers)
            root_response.raise_for_status()
            vault_response = client.get(base + "/vault/", headers=headers)
            vault_response.raise_for_status()
        version = ""
        try:
            payload = root_response.json()
            version = str(
                (payload.get("versions") or {}).get("self")
                or payload.get("service_version")
                or payload.get("version")
                or ""
            )
        except (ValueError, AttributeError):
            payload = {}
        parsed = self._version_tuple(version) if version else None
        if parsed and parsed < (4, 1, 3):
            raise DestinationError(
                "Obsidian Local REST API 版本低于 4.1.3；请先升级以修复已知路径穿越漏洞。",
                state="blocked_policy",
                code="OBSIDIAN_UNSAFE_VERSION",
            )
        return {
            "mode": "rest",
            "authenticated": True,
            "vault_read": True,
            "service_version": version or "unreported",
            "minimum_safe_version": "4.1.3",
        }

    def _export_obsidian(self, content: dict[str, Any], markdown: str) -> dict[str, Any]:
        if self.settings.obsidian_vault_root:
            result = self._write_markdown(content, markdown, self.settings.obsidian_vault_root / "Social Archive")
            result["destination_id"] = "obsidian"
            return result
        if not self.settings.obsidian_rest_url:
            raise ValueError("Obsidian 尚未连接")
        token = read_secret(self.settings.obsidian_rest_token_file)
        if not token:
            raise ValueError("Obsidian REST Token 缺失")
        path = f"Social Archive/{safe_slug(str(content.get('platform') or 'unknown'))}/{safe_slug(str(content.get('title') or content['id']))}-{content['id'][-8:]}.md"
        encoded_path = urllib.parse.quote(path, safe="/")
        headers = {"Authorization": f"Bearer {token}", "Content-Type": "text/markdown; charset=utf-8"}
        with self._client(timeout=30.0, verify=self._obsidian_verify()) as client:
            response = client.put(
                self.settings.obsidian_rest_url.rstrip("/") + "/vault/" + encoded_path,
                headers=headers,
                content=markdown.encode("utf-8"),
            )
            response.raise_for_status()
        return {"destination_id": "obsidian", "status": "done", "path": path, "content_id": content["id"]}

    def _notion_headers(self) -> dict[str, str]:
        token = read_secret(self.settings.notion_token_file)
        if not token:
            raise ValueError("Notion Token 缺失")
        return {
            "Authorization": f"Bearer {token}",
            "Notion-Version": self.settings.notion_api_version,
            "Content-Type": "application/json",
        }

    def _resolve_notion_target(self, client: httpx.Client) -> tuple[str, dict[str, Any]]:
        headers = self._notion_headers()
        data_source_id = self.settings.notion_data_source_id
        if not data_source_id:
            database_id = self.settings.notion_database_id
            if not database_id:
                raise ValueError("Notion data_source_id 或 database_id 未配置")
            response = client.get(f"https://api.notion.com/v1/databases/{database_id}", headers=headers)
            response.raise_for_status()
            data_sources = response.json().get("data_sources") or []
            if len(data_sources) != 1:
                raise DestinationError(
                    "目标数据库必须只有一个可写数据源，或显式配置 SOCIAL_ARCHIVE_NOTION_DATA_SOURCE_ID。",
                    state="needs_user_action",
                    code="NOTION_DATA_SOURCE_AMBIGUOUS",
                )
            data_source_id = str(data_sources[0].get("id") or "")
        if not data_source_id:
            raise DestinationError("未发现可写 Notion 数据源。", state="needs_user_action", code="NOTION_DATA_SOURCE_MISSING")
        response = client.get(f"https://api.notion.com/v1/data_sources/{data_source_id}", headers=headers)
        response.raise_for_status()
        return data_source_id, response.json()

    def _probe_notion(self) -> dict[str, Any]:
        with self._client(timeout=20.0) as client:
            data_source_id, data_source = self._resolve_notion_target(client)
        properties = data_source.get("properties") or {}
        title_name = next((name for name, value in properties.items() if value.get("type") == "title"), None)
        if not title_name:
            raise DestinationError(
                "Notion 数据源缺少标题属性，无法创建页面。",
                state="needs_user_action",
                code="NOTION_TITLE_PROPERTY_MISSING",
            )
        return {
            "api_version": self.settings.notion_api_version,
            "data_source_id": data_source_id,
            "title_property": title_name,
            "write_model": "data_source_id",
        }

    @staticmethod
    def _notion_rich_text(value: str) -> list[dict[str, Any]]:
        return [{"type": "text", "text": {"content": value[:2000]}}]

    def _notion_properties(
        self,
        content: dict[str, Any],
        data_source: dict[str, Any],
        projection_sha256: str,
    ) -> dict[str, Any]:
        definitions = data_source.get("properties") or {}
        title_name = next((name for name, value in definitions.items() if value.get("type") == "title"), None)
        if not title_name:
            raise DestinationError(
                "Notion 数据源缺少标题属性。",
                state="needs_user_action",
                code="NOTION_TITLE_PROPERTY_MISSING",
            )
        title = str(content.get("title") or content.get("canonical_url") or content["id"])[:2000]
        result: dict[str, Any] = {title_name: {"title": self._notion_rich_text(title)}}
        candidates = {
            "Source": ("url", content.get("canonical_url")),
            "Platform": ("rich_text", str(content.get("platform") or "")),
            "Social Archive ID": ("rich_text", content["id"]),
            "Projection SHA256": ("rich_text", projection_sha256),
        }
        for name, (expected_type, value) in candidates.items():
            definition = definitions.get(name) or {}
            actual_type = definition.get("type")
            if actual_type == "url" and expected_type == "url":
                result[name] = {"url": value}
            elif actual_type == "rich_text":
                result[name] = {"rich_text": self._notion_rich_text(str(value or ""))}
            elif name == "Platform" and actual_type == "select" and value:
                result[name] = {"select": {"name": str(value)[:100]}}
        return result

    @staticmethod
    def _notion_chunks(markdown: str) -> list[str]:
        maximum_chars = 1800 * 100
        if len(markdown) > maximum_chars:
            markdown = markdown[: maximum_chars - 80] + "\n\n[正文过长；完整版本保存在 Social Archive、Markdown 与 L3 对象中。]\n"
        return [markdown[index : index + 1800] for index in range(0, len(markdown), 1800)] or [""]

    def _notion_block(self, chunk: str) -> dict[str, Any]:
        return {
            "object": "block",
            "type": "code",
            "code": {"language": "plain text", "rich_text": self._notion_rich_text(chunk)},
        }

    def _checkpoint_notion_binding(
        self,
        *,
        content_id: str,
        page_id: str,
        page_url: str | None,
        data_source_id: str,
        projection_sha256: str,
        block_ids: list[str],
    ) -> None:
        """Persist provider-confirmed progress before another mutable API call."""
        self.store.upsert_destination_binding(
            destination_id="notion",
            content_id=content_id,
            projection_sha256=f"pending:{projection_sha256}",
            remote_id=page_id,
            remote_path=page_url,
            metadata={
                "notion_block_ids": list(block_ids),
                "data_source_id": data_source_id,
                "api_version": self.settings.notion_api_version,
                "notion_sync_state": "pending",
            },
        )

    def _append_notion_blocks(
        self,
        client: httpx.Client,
        page_id: str,
        chunks: list[str],
        *,
        known_block_ids: list[str] | None = None,
        checkpoint: Callable[[list[str]], None] | None = None,
    ) -> list[str]:
        headers = self._notion_headers()
        ids = list(known_block_ids or [])
        for offset in range(0, len(chunks), 100):
            batch = chunks[offset : offset + 100]
            response = client.patch(
                f"https://api.notion.com/v1/blocks/{page_id}/children",
                headers=headers,
                json={"children": [self._notion_block(chunk) for chunk in batch]},
            )
            response.raise_for_status()
            batch_ids = [str(item.get("id")) for item in response.json().get("results", []) if item.get("id")]
            if len(batch_ids) != len(batch) or len(set(batch_ids)) != len(batch_ids):
                raise DestinationError(
                    "Notion Append Block 回执缺少或重复 Block ID，拒绝确认写入。",
                    code="NOTION_BLOCK_RECEIPT_INVALID",
                )
            ids.extend(batch_ids)
            if checkpoint:
                checkpoint(list(ids))
        return ids

    def _sync_notion_blocks(
        self,
        client: httpx.Client,
        page_id: str,
        chunks: list[str],
        existing_ids: list[str],
        *,
        checkpoint: Callable[[list[str]], None] | None = None,
    ) -> list[str]:
        headers = self._notion_headers()
        current_ids = list(existing_ids)
        shared = min(len(chunks), len(existing_ids))
        for index in range(shared):
            block_id = existing_ids[index]
            response = client.patch(
                f"https://api.notion.com/v1/blocks/{block_id}",
                headers=headers,
                json={"code": self._notion_block(chunks[index])["code"]},
            )
            response.raise_for_status()
        for block_id in list(current_ids[len(chunks) :]):
            response = client.delete(f"https://api.notion.com/v1/blocks/{block_id}", headers=headers)
            response.raise_for_status()
            current_ids.remove(block_id)
            if checkpoint:
                checkpoint(list(current_ids))
        if len(chunks) > len(existing_ids):
            return self._append_notion_blocks(
                client,
                page_id,
                chunks[len(existing_ids) :],
                known_block_ids=current_ids,
                checkpoint=checkpoint,
            )
        return current_ids

    def _export_notion(
        self,
        content: dict[str, Any],
        markdown: str,
        binding: dict[str, Any] | None,
    ) -> dict[str, Any]:
        projection_sha256 = sha256_bytes(markdown.encode("utf-8"))
        headers = self._notion_headers()
        chunks = self._notion_chunks(markdown)
        with self._client(timeout=30.0) as client:
            data_source_id, data_source = self._resolve_notion_target(client)
            properties = self._notion_properties(content, data_source, projection_sha256)
            page_id = str((binding or {}).get("remote_id") or "")
            metadata = dict((binding or {}).get("metadata") or {})
            page_url = str((binding or {}).get("remote_path") or "") or None

            def checkpoint(block_ids: list[str]) -> None:
                self._checkpoint_notion_binding(
                    content_id=content["id"],
                    page_id=page_id,
                    page_url=page_url,
                    data_source_id=data_source_id,
                    projection_sha256=projection_sha256,
                    block_ids=block_ids,
                )

            if page_id:
                response = client.patch(
                    f"https://api.notion.com/v1/pages/{page_id}",
                    headers=headers,
                    json={"properties": properties},
                )
                response.raise_for_status()
                page = response.json()
                page_url = str(page.get("url") or page_url or "") or None
                checkpoint([str(value) for value in metadata.get("notion_block_ids") or []])
                block_ids = self._sync_notion_blocks(
                    client,
                    page_id,
                    chunks,
                    [str(value) for value in metadata.get("notion_block_ids") or []],
                    checkpoint=checkpoint,
                )
            else:
                response = client.post(
                    "https://api.notion.com/v1/pages",
                    headers=headers,
                    json={
                        "parent": {"type": "data_source_id", "data_source_id": data_source_id},
                        "properties": properties,
                    },
                )
                response.raise_for_status()
                page = response.json()
                page_id = str(page.get("id") or "")
                if not page_id:
                    raise DestinationError("Notion 未返回页面 ID。", code="NOTION_PAGE_ID_MISSING")
                page_url = str(page.get("url") or "") or None
                checkpoint([])
                block_ids = self._append_notion_blocks(client, page_id, chunks, checkpoint=checkpoint)
        return {
            "destination_id": "notion",
            "status": "done",
            "remote_id": page_id,
            "remote_path": page_url,
            "content_id": content["id"],
            "binding_metadata": {
                "notion_block_ids": block_ids,
                "data_source_id": data_source_id,
                "api_version": self.settings.notion_api_version,
                "notion_sync_state": "complete",
            },
        }

    @staticmethod
    def _reader_entity(payload: Any) -> dict[str, Any]:
        if not isinstance(payload, dict):
            return {}
        for key in ("bookmark", "response", "data"):
            value = payload.get(key)
            if isinstance(value, dict):
                return value
        return payload

    @staticmethod
    def _bearer_secret(path: str | None, label: str) -> dict[str, str]:
        token = read_secret(path)
        if not token:
            raise ValueError(f"{label} API Token 缺失")
        return {"Authorization": f"Bearer {token}", "Accept": "application/json"}

    def _probe_karakeep(self) -> dict[str, Any]:
        base = self.settings.karakeep_url
        if not base:
            raise ValueError("Karakeep 地址尚未配置")
        with self._client(timeout=15.0) as client:
            response = client.get(
                f"{base}/api/v1/bookmarks",
                headers=self._bearer_secret(self.settings.karakeep_token_file, "Karakeep"),
                params={"limit": 1},
            )
            response.raise_for_status()
        return {"api_version": "v0.32.0", "read": True, "write": True, "canonical": False}

    def _export_karakeep(self, content: dict[str, Any]) -> dict[str, Any]:
        base = self.settings.karakeep_url
        url = str(content.get("canonical_url") or "")
        if not base or not url:
            raise ValueError("Karakeep 地址或内容 URL 缺失")
        with self._client(timeout=20.0) as client:
            response = client.post(
                f"{base}/api/v1/bookmarks",
                headers={**self._bearer_secret(self.settings.karakeep_token_file, "Karakeep"), "Content-Type": "application/json"},
                json={"type": "link", "url": url},
            )
            response.raise_for_status()
            entity = self._reader_entity(response.json())
        remote_id = str(entity.get("id") or entity.get("bookmarkId") or "") or None
        return {
            "destination_id": "karakeep",
            "status": "done",
            "remote_id": remote_id,
            "remote_path": base,
            "content_id": content["id"],
            "binding_metadata": {"api": "/api/v1/bookmarks", "projection_only": True},
        }

    def _probe_linkwarden(self) -> dict[str, Any]:
        base = self.settings.linkwarden_url
        if not base:
            raise ValueError("Linkwarden 地址尚未配置")
        with self._client(timeout=15.0) as client:
            response = client.get(
                f"{base}/api/v1/links",
                headers=self._bearer_secret(self.settings.linkwarden_token_file, "Linkwarden"),
                params={"take": 1},
            )
            response.raise_for_status()
        return {"api_version": "v2.16.0", "read": True, "write": True, "canonical": False}

    def _export_linkwarden(self, content: dict[str, Any]) -> dict[str, Any]:
        base = self.settings.linkwarden_url
        url = str(content.get("canonical_url") or "")
        if not base or not url:
            raise ValueError("Linkwarden 地址或内容 URL 缺失")
        with self._client(timeout=20.0) as client:
            response = client.post(
                f"{base}/api/v1/links",
                headers={**self._bearer_secret(self.settings.linkwarden_token_file, "Linkwarden"), "Content-Type": "application/json"},
                json={"url": url},
            )
            response.raise_for_status()
            entity = self._reader_entity(response.json())
        remote_id = str(entity.get("id") or "") or None
        return {
            "destination_id": "linkwarden",
            "status": "done",
            "remote_id": remote_id,
            "remote_path": base,
            "content_id": content["id"],
            "binding_metadata": {"api": "/api/v1/links", "projection_only": True},
        }

    def _archivebox_queue(self) -> Path:
        return self.settings.export_root / "readers" / "archivebox-urls.txt"

    def _probe_archivebox(self) -> dict[str, Any]:
        path = self._archivebox_queue()
        path.parent.mkdir(parents=True, exist_ok=True)
        existing = path.read_bytes() if path.exists() else b""
        atomic_write(path, existing)
        if path.read_bytes() != existing:
            raise DestinationError("ArchiveBox URL 队列回读不一致。", code="ARCHIVEBOX_QUEUE_READBACK_MISMATCH")
        return {"write": True, "readback": True, "mode": "url_queue", "canonical": False, "path": str(path)}

    def _export_archivebox(self, content: dict[str, Any]) -> dict[str, Any]:
        url = str(content.get("canonical_url") or "").strip()
        if not url:
            raise ValueError("内容 URL 缺失，不能写入 ArchiveBox 队列")
        path = self._archivebox_queue()
        existing = path.read_text(encoding="utf-8").splitlines() if path.exists() else []
        urls = list(dict.fromkeys([*existing, url]))
        atomic_write(path, ("\n".join(urls) + "\n").encode("utf-8"))
        return {
            "destination_id": "archivebox",
            "status": "done",
            "remote_id": content["id"],
            "path": str(path),
            "content_id": content["id"],
            "binding_metadata": {"mode": "url_queue", "projection_only": True},
        }

    def _github_headers(self) -> dict[str, str]:
        token = read_secret(self.settings.github_token_file)
        if not token:
            raise ValueError("GitHub Token 缺失")
        return {
            "Authorization": f"Bearer {token}",
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
        }

    def _probe_github_with_client(self, client: httpx.Client) -> dict[str, Any]:
        repository = self._github_repository()
        response = client.get(f"https://api.github.com/repos/{repository}", headers=self._github_headers())
        response.raise_for_status()
        payload = response.json()
        if payload.get("private") is not True:
            raise DestinationError(
                "为避免私人收藏泄露，GitHub 目的地必须是 Private Repository。",
                state="blocked_policy",
                code="GITHUB_REPOSITORY_NOT_PRIVATE",
            )
        default_branch = str(payload.get("default_branch") or self.settings.github_markdown_branch)
        return {
            "repository": repository,
            "private": True,
            "default_branch": default_branch,
            "contents_read": True,
        }

    def _probe_github(self) -> dict[str, Any]:
        with self._client(timeout=20.0) as client:
            return self._probe_github_with_client(client)

    def _export_github(self, content: dict[str, Any], markdown: str) -> dict[str, Any]:
        repository = self._github_repository()
        platform = safe_slug(str(content.get("platform") or "unknown"))
        title = safe_slug(str(content.get("title") or content["id"]), content["id"])
        path = f"{PRIVATE_DATABASE_AREA}/SocialArchive/markdown/{platform}/{title}-{content['id'][-8:]}.md"
        api = f"https://api.github.com/repos/{repository}/contents/{urllib.parse.quote(path, safe='/')}"
        headers = self._github_headers()
        markdown_bytes = markdown.encode("utf-8")
        expected_blob_sha = _git_blob_sha(markdown_bytes)
        with self._client(timeout=30.0) as client:
            metadata = self._probe_github_with_client(client)
            branch = (self.settings.github_markdown_branch or metadata["default_branch"]).strip()
            if not branch:
                raise DestinationError("GitHub 默认分支为空，拒绝写入。", code="GITHUB_BRANCH_MISSING")
            existing = client.get(api, headers=headers, params={"ref": branch})
            if existing.status_code not in {200, 404}:
                existing.raise_for_status()
            existing_payload = existing.json() if existing.status_code == 200 else {}
            sha = existing_payload.get("sha") if existing.status_code == 200 else None
            if existing.status_code == 200 and not isinstance(sha, str):
                raise DestinationError(
                    "GitHub Contents API 未返回现有文件 SHA，拒绝覆盖。",
                    code="GITHUB_CONTENT_SHA_MISSING",
                )
            if sha == expected_blob_sha:
                return {
                    "destination_id": "github",
                    "status": "noop",
                    "path": path,
                    "remote_id": sha,
                    "content_id": content["id"],
                    "binding_metadata": {
                        "repository": repository,
                        "branch": branch,
                        "area": PRIVATE_DATABASE_AREA,
                        "private": True,
                        "reconciled": True,
                    },
                }
            payload: dict[str, Any] = {
                "message": f"Social Archive: {content['id']}",
                "content": base64.b64encode(markdown_bytes).decode("ascii"),
                "branch": branch,
            }
            if sha:
                payload["sha"] = sha
            response = client.put(api, headers=headers, json=payload)
            response.raise_for_status()
            body = response.json()
            commit_sha = body.get("commit", {}).get("sha")
            content_sha = body.get("content", {}).get("sha")
            returned_path = body.get("content", {}).get("path")
            if not isinstance(content_sha, str) or not isinstance(commit_sha, str) or returned_path != path:
                raise DestinationError(
                    "GitHub Contents API 回执不完整或路径不一致，拒绝确认写入。",
                    code="GITHUB_CONTENTS_RECEIPT_INVALID",
                )
        return {
            "destination_id": "github",
            "status": "done",
            "path": path,
            "remote_id": content_sha or commit_sha,
            "commit_sha": commit_sha,
            "content_id": content["id"],
            "binding_metadata": {
                "repository": repository,
                "branch": branch,
                "area": PRIVATE_DATABASE_AREA,
                "private": True,
                "reconciled": True,
            },
        }
