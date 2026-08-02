from __future__ import annotations

import secrets
from dataclasses import dataclass
from typing import Any

from .config import Settings
from .db import RuntimeStore
from .models import AccountConnectRequest, AccountSyncRequest, CaptureRequest, ConnectorRunRequest, SyncBatchRequest
from .registry import ConnectorRegistry
from .service import ArchiveService
from .utils import utcnow


PLATFORM_RELATIONS: dict[str, list[str]] = {
    "xiaohongshu": ["favorite", "like"],
    "douyin": ["favorite", "like"],
    "kuaishou": ["favorite", "like"],
    "bilibili": ["favorite", "watch_later", "history", "like"],
    "x": ["bookmark", "like"],
    "reddit": ["saved", "upvoted"],
    "instagram": ["saved"],
    "generic-web": ["bookmark", "manual_save"],
}

PLATFORM_LABELS = {
    "xiaohongshu": "小红书",
    "douyin": "抖音",
    "kuaishou": "快手",
    "bilibili": "B站",
    "x": "X",
    "reddit": "Reddit",
    "instagram": "Instagram",
    "generic-web": "通用网页",
}

# These platforms can be attempted by the server-side prebuilt adapters. Other
# platforms use the extension/isolated-worker batch protocol as the primary free
# path; the product never asks the owner to paste cookies or headers.
SERVER_ACCOUNT_CONNECTORS = {"x", "reddit", "instagram", "bilibili"}


@dataclass(frozen=True)
class ConnectStartResult:
    connection_ref: str
    platform: str
    auth_method: str
    state: str
    next_action_zh: str
    supported_relations: list[str]


class AccountSyncCoordinator:
    def __init__(
        self,
        settings: Settings,
        store: RuntimeStore,
        archive: ArchiveService,
        registry: ConnectorRegistry,
    ) -> None:
        self.settings = settings
        self.store = store
        self.archive = archive
        self.registry = registry

    @staticmethod
    def _relations(platform: str, requested: list[str] | None = None) -> list[str]:
        allowed = PLATFORM_RELATIONS.get(platform, [])
        if not requested:
            return list(allowed)
        return [item for item in dict.fromkeys(requested) if item in allowed]

    def connect_start(self, request: AccountConnectRequest) -> ConnectStartResult:
        platform = request.platform.strip().lower()
        if platform not in PLATFORM_RELATIONS:
            raise ValueError("当前平台不在本版本账号同步范围内")
        connection_ref = f"conn_{secrets.token_urlsafe(24)}"
        method = request.auth_method
        action = {
            "oauth": "将在平台官方授权页确认只读权限。",
            "qr": "请在弹出的平台登录窗口扫码；完成后自动返回。",
            "browser_session": "请在当前 Chrome 中登录该平台，然后点击“我已登录”。",
            "official_export": "请选择平台官方导出的数据文件；系统会自动识别。",
            "local_import": "请选择现有归档文件；系统会自动去重导入。",
            "chrome_bookmarks": "请授权读取 Chrome 书签；不会读取浏览历史。",
        }[method]
        # No credential is persisted here. The opaque ref is exchanged only after
        # a real environment verifies the login/session.
        return ConnectStartResult(
            connection_ref=connection_ref,
            platform=platform,
            auth_method=method,
            state="authorizing",
            next_action_zh=action,
            supported_relations=self._relations(platform, request.relation_types),
        )

    def complete_connection(
        self,
        *,
        platform: str,
        auth_method: str,
        connection_ref: str,
        external_account_id: str,
        display_name: str | None,
        auto_sync_enabled: bool,
        sync_interval_minutes: int,
        metadata: dict[str, Any],
        verified: bool,
    ) -> str:
        if not verified:
            raise ValueError("只有完成真实登录验证后才能标记账号已连接")
        if not connection_ref.startswith("conn_"):
            raise ValueError("连接凭据无效，请重新连接账号")
        if not 15 <= sync_interval_minutes <= 10080:
            raise ValueError("账号同步间隔必须在 15–10080 分钟")
        account_id = self.store.upsert_source_account(
            platform=platform,
            external_account_id=external_account_id,
            display_name=display_name,
            auth_method=auth_method,
            auth_handle_ref=connection_ref,
            connection_state="connected",
            auto_sync_enabled=auto_sync_enabled,
            sync_interval_minutes=sync_interval_minutes,
            metadata=metadata,
        )
        return account_id

    def start_sync(self, account_id: str, request: AccountSyncRequest) -> dict[str, Any]:
        account = self.store.get_source_account(account_id, include_handle=True)
        if not account:
            raise ValueError("账号不存在")
        if account["connection_state"] not in {"connected", "degraded"}:
            raise ValueError("账号尚未连接，请先完成授权")
        relations = self._relations(account["platform"], request.relation_types)
        if not relations:
            raise ValueError("该平台没有可同步的关系类型")
        mode = request.mode
        if mode == "incremental" and not account.get("last_sync_at"):
            mode = "first_full"
        run_id = self.store.create_sync_run(
            source_account_id=account_id,
            platform=account["platform"],
            mode=mode,
            relation_types=relations,
            trigger_type=request.trigger_type,
        )
        job_id = self.store.enqueue_job(
            "account_sync",
            {"sync_run_id": run_id, "account_id": account_id, "relations": relations, "mode": mode},
            connector_id=account["platform"],
        )
        return {
            "sync_run_id": run_id,
            "job_id": job_id,
            "status": "queued",
            "mode": mode,
            "relations": relations,
            "next_action_zh": "首次同步已开始；已完成内容会立即出现在资料库。" if mode == "first_full" else "增量同步已开始。",
        }

    def process_job(self, payload: dict[str, Any]) -> None:
        run_id = str(payload["sync_run_id"])
        account_id = str(payload["account_id"])
        run = self.store.get_sync_run(run_id)
        account = self.store.get_source_account(account_id, include_handle=True)
        if not run or not account:
            raise ValueError("同步运行或账号不存在")
        if run["status"] in {"cancelled", "completed", "partial", "failed"}:
            return
        if account["connection_state"] not in {"connected", "degraded"}:
            self.store.update_sync_run(run_id, status="blocked_environment", completeness="unknown", error_code="ACCOUNT_REAUTH_REQUIRED", error_message="账号需要重新连接")
            return

        platform = account["platform"]
        relations = list(run.get("relation_scope") or payload.get("relations") or PLATFORM_RELATIONS.get(platform, []))
        if platform not in SERVER_ACCOUNT_CONNECTORS:
            # The extension/isolated worker owns browser-session scanning. Keeping
            # the run in scanning state makes the next action explicit without
            # pretending a server-only connector succeeded.
            self.store.update_sync_run(
                run_id,
                status="scanning",
                completeness="unknown",
                evidence={"ingest_mode": "extension_or_isolated_worker", "waiting_for_batch": True},
            )
            return

        self.store.update_sync_run(run_id, status="discovering")
        imported_total = 0
        failed_total = 0
        discovered_total = 0
        partial = False
        blocked_environment = False
        last_failure_code: str | None = None
        max_items = self.settings.account_sync_max_items_per_run
        for relation in relations:
            current = self.store.get_sync_run(run_id)
            if current and current["status"] in {"paused", "cancelled"}:
                return
            self.store.update_sync_run(run_id, status="scanning")
            checkpoint = self.store.get_sync_checkpoint(
                source_account_id=account_id,
                relation_type=relation,
                collection_key="",
            )
            checkpoint_cursor = (checkpoint or {}).get("cursor") or {}
            cursor_key = "next_cursor"
            cursor_value = checkpoint_cursor.get(cursor_key)
            if not cursor_value:
                cursor_key = "next_token"
                cursor_value = checkpoint_cursor.get(cursor_key)
            cursor = str(cursor_value).strip() if cursor_value else None
            resumed_from_prior_run = bool(cursor)
            seen_cursors = {cursor} if cursor else set()
            observed_relation_ids: set[str] = set()
            known_anchor: str | None = None

            while True:
                current = self.store.get_sync_run(run_id)
                if current and current["status"] in {"paused", "cancelled"}:
                    return
                remaining = max_items - discovered_total
                if remaining <= 0:
                    partial = True
                    last_failure_code = "ACCOUNT_SYNC_ITEM_LIMIT_REACHED"
                    resume_cursor = {cursor_key: cursor} if cursor else {}
                    self.store.upsert_sync_checkpoint(
                        source_account_id=account_id,
                        relation_type=relation,
                        collection_key="",
                        cursor=resume_cursor,
                        known_anchor=known_anchor,
                        last_complete_sync_run_id=None,
                        complete=False,
                    )
                    self.store.update_sync_run(
                        run_id,
                        error_code=last_failure_code,
                        error_message="本次同步达到安全条目上限；已保留检查点。",
                        cursor={"relation": relation, **resume_cursor},
                    )
                    break

                request = ConnectorRunRequest(
                    relation_type=relation,  # type: ignore[arg-type]
                    limit=min(self.settings.account_sync_page_size, remaining),
                    source_account_id=account["external_account_id"],
                    cursor=cursor,
                    requested_levels=["L0", "L1", "L3"],
                    destination_ids=["social_archive", "markdown"],
                )
                result, captures = self.registry.run(platform, request)
                responses = []
                for capture in captures:
                    effective = capture.model_copy(update={
                        "source_account_id": account["external_account_id"],
                        "raw_metadata": {**capture.raw_metadata, "sync_run_id": run_id},
                    })
                    response = self.archive.capture(effective)
                    responses.append(response)
                    observed_relation_ids.add(response.relation_id)
                if known_anchor is None and captures:
                    known_anchor = captures[0].external_content_id

                receipt = dict(result.scan_receipt)
                receipt.setdefault("scope", "account_relation")
                receipt.setdefault("relation_type", relation)
                receipt.setdefault("source_account_id", account["external_account_id"])
                if cursor:
                    receipt.setdefault("cursor_start", cursor)
                page_discovered = max(int(receipt.get("item_count") or len(captures)), len(captures))
                discovered_total += page_discovered
                failed_total += len(result.errors)
                blocked_environment = blocked_environment or result.status == "blocked_environment"

                complete = receipt.get("completeness") == "complete"
                next_cursor_key = "next_cursor" if receipt.get("next_cursor") else "next_token"
                next_value = receipt.get(next_cursor_key)
                next_cursor = str(next_value).strip() if next_value else None
                if next_cursor:
                    cursor_key = next_cursor_key
                failure_code = str(receipt.get("failure_code") or (result.errors[0].get("code") if result.errors else "") or "") or None
                resume_cursor: dict[str, Any] = {}
                continue_paging = False

                if complete and resumed_from_prior_run:
                    # A cursor recovered from an earlier run proves continuation,
                    # not a complete current-run relation snapshot. Never close
                    # older relations until one fresh scan observes every page.
                    complete = False
                    partial = True
                    failure_code = f"{platform.upper().replace('-', '_')}_FRESH_FULL_SCAN_REQUIRED"
                    receipt["completeness"] = "partial"
                    receipt["failure_code"] = failure_code
                elif complete:
                    self.store.apply_complete_scan(
                        platform,
                        observed_relation_ids,
                        relation_type=relation,
                        source_account_id=account["external_account_id"],
                    )
                elif next_cursor and discovered_total < max_items and next_cursor not in seen_cursors:
                    resume_cursor = {cursor_key: next_cursor}
                    continue_paging = True
                else:
                    partial = True
                    if next_cursor:
                        if discovered_total >= max_items:
                            resume_cursor = {cursor_key: next_cursor}
                            failure_code = "ACCOUNT_SYNC_ITEM_LIMIT_REACHED"
                            receipt["failure_code"] = failure_code
                        elif next_cursor in seen_cursors:
                            resume_cursor = {cursor_key: cursor or next_cursor}
                            failure_code = f"{platform.upper().replace('-', '_')}_CURSOR_LOOP"
                            receipt["failure_code"] = failure_code
                    elif cursor:
                        resume_cursor = {cursor_key: cursor}

                if failure_code:
                    last_failure_code = failure_code
                self.store.record_scan_receipt(
                    platform,
                    result.run_id,
                    receipt,
                    source_account_id=account["external_account_id"],
                    relation_type=relation,
                )
                imported_total += len(responses)
                self.store.upsert_sync_checkpoint(
                    source_account_id=account_id,
                    relation_type=relation,
                    collection_key="",
                    cursor={} if complete else resume_cursor,
                    known_anchor=known_anchor,
                    last_complete_sync_run_id=run_id if complete else None,
                    complete=complete,
                )
                self.store.update_sync_run(
                    run_id,
                    discovered_delta=page_discovered,
                    imported_delta=len(responses),
                    failed_delta=len(result.errors),
                    error_code=failure_code,
                    error_message=(result.errors[0].get("message") if result.errors else None),
                    cursor={"relation": relation, **({} if complete else resume_cursor)},
                )
                if not continue_paging:
                    break
                cursor = next_cursor
                seen_cursors.add(cursor)
        final_status = "blocked_environment" if blocked_environment else ("partial" if partial or failed_total else "completed")
        self.store.update_sync_run(
            run_id,
            status=final_status,
            completeness="unknown" if final_status == "blocked_environment" else ("partial" if final_status == "partial" else "complete"),
            error_code=last_failure_code,
            evidence={"imported": imported_total, "failed": failed_total, "completed_at": utcnow()},
        )
        if final_status != "blocked_environment":
            self.store.set_source_account_state(account_id, "connected", verified=True)
        if final_status == "completed":
            with self.store.connection() as con:
                con.execute("UPDATE source_account SET last_sync_at=?,updated_at=? WHERE id=?", (utcnow(), utcnow(), account_id))

    def _finalize_relation_scope(
        self,
        *,
        sync_run_id: str,
        run: dict[str, Any],
        account: dict[str, Any],
        relation_type: str,
        completeness: str,
        failure_code: str | None,
        errors: list[dict[str, Any]],
    ) -> tuple[str, int]:
        """Close one relation only after an explicit relation-final marker.

        Page/collection batches never close the run. The observed relation IDs are
        accumulated across every chunk, so a final page cannot make earlier pages
        look deleted. A complete marker evaluates every previously known collection,
        including collections that became empty during this sync.
        """
        effective_completeness = completeness
        if errors and effective_completeness == "complete":
            effective_completeness = "partial"
        scope_status = {
            "complete": "complete",
            "partial": "partial",
            "failed": "failed",
            "unknown": "partial",
        }[effective_completeness]

        closed_candidates = 0
        if effective_completeness == "complete":
            collections = self.store.list_sync_seen_collections(
                sync_run_id=sync_run_id,
                relation_type=relation_type,
            )
            collections.update(self.store.list_existing_relation_collections(
                platform=account["platform"],
                external_account_id=account["external_account_id"],
                relation_type=relation_type,
            ))
            if not collections:
                collections.add("")
            for collection_key in collections:
                observed = self.store.list_sync_seen_relation_ids(
                    sync_run_id=sync_run_id,
                    relation_type=relation_type,
                    collection_key=collection_key,
                )
                closed_candidates += self.store.apply_complete_scan(
                    account["platform"],
                    observed,
                    relation_type=relation_type,
                    collection_key=collection_key,
                    source_account_id=account["external_account_id"],
                )

        self.store.upsert_sync_run_scope(
            sync_run_id=sync_run_id,
            relation_type=relation_type,
            collection_key="__relation__",
            status=scope_status,
            completeness=effective_completeness,
            failed_delta=len(errors),
        )
        self.store.upsert_sync_checkpoint(
            source_account_id=account["id"],
            relation_type=relation_type,
            collection_key="__relation__",
            cursor={},
            known_anchor=None,
            last_complete_sync_run_id=sync_run_id if effective_completeness == "complete" else None,
            complete=effective_completeness == "complete",
        )

        expected = list(run.get("relation_scope") or [])
        relation_scopes = {
            item["relation_type"]: item
            for item in self.store.list_sync_run_scopes(sync_run_id)
            if item["collection_key"] == "__relation__"
        }
        terminal = {"complete", "partial", "failed"}
        all_terminal = bool(expected) and all(
            relation_scopes.get(relation, {}).get("status") in terminal
            for relation in expected
        )
        if not all_terminal:
            self.store.update_sync_run(
                sync_run_id,
                status="scanning",
                completeness="unknown",
                error_code=failure_code,
                error_message=(errors[0].get("message") if errors else None),
                evidence={
                    "waiting_for_relations": [
                        relation for relation in expected
                        if relation_scopes.get(relation, {}).get("status") not in terminal
                    ],
                    "closed_candidate_count": closed_candidates,
                },
            )
            return "scanning", closed_candidates

        all_complete = all(
            relation_scopes.get(relation, {}).get("completeness") == "complete"
            for relation in expected
        )
        final_status = "completed" if all_complete else "partial"
        self.store.update_sync_run(
            sync_run_id,
            status=final_status,
            completeness="complete" if all_complete else "partial",
            error_code=failure_code,
            error_message=(errors[0].get("message") if errors else None),
            evidence={
                "relation_scopes": relation_scopes,
                "closed_candidate_count": closed_candidates,
                "completed_at": utcnow(),
            },
        )
        if final_status == "completed":
            with self.store.connection() as con:
                con.execute(
                    "UPDATE source_account SET last_sync_at=?,updated_at=?,last_error_code=NULL WHERE id=?",
                    (utcnow(), utcnow(), account["id"]),
                )
        return final_status, closed_candidates

    def ingest_batch(self, sync_run_id: str, batch: SyncBatchRequest) -> dict[str, Any]:
        run = self.store.get_sync_run(sync_run_id)
        if not run:
            raise ValueError("同步运行不存在")
        if run["status"] in {"cancelled", "completed"}:
            raise ValueError("当前同步运行不能再接收数据")
        account = self.store.get_source_account(run["source_account_id"], include_handle=True)
        if not account:
            raise ValueError("来源账号不存在")
        allowed = self._relations(account["platform"])
        if batch.relation_type not in allowed:
            raise ValueError("该关系类型不属于当前平台")

        self.store.update_sync_run(sync_run_id, status="normalizing")
        if batch.collection_name:
            self.store.upsert_platform_collection(
                source_account_id=account["id"],
                relation_type=batch.relation_type,
                name=batch.collection_name,
                external_collection_id=batch.external_collection_id,
                item_count=None,
                metadata={"sync_run_id": sync_run_id},
            )

        responses = []
        errors: list[dict[str, Any]] = []
        relation_ids_by_collection: dict[str, set[str]] = {}
        for index, item in enumerate(batch.items):
            if item.platform.lower() != account["platform"]:
                errors.append({"index": index, "code": "PLATFORM_MISMATCH", "message": "条目平台与来源账号不一致"})
                continue
            collection_key = batch.collection_key or item.collection_key or ""
            try:
                effective = item.model_copy(update={
                    "relation_type": batch.relation_type,
                    "collection_key": collection_key,
                    "source_account_id": account["external_account_id"],
                    "raw_metadata": {
                        **item.raw_metadata,
                        "sync_run_id": sync_run_id,
                        "batch_index": batch.batch_index,
                        "scope_type": batch.scope_type,
                    },
                })
                response = self.archive.capture(effective)
                responses.append(response)
                relation_ids_by_collection.setdefault(collection_key, set()).add(response.relation_id)
            except (ValueError, OSError) as exc:
                errors.append({"index": index, "code": exc.__class__.__name__, "message": str(exc)[:500]})

        if relation_ids_by_collection:
            self.store.record_sync_seen_relations(
                sync_run_id=sync_run_id,
                relation_type=batch.relation_type,
                relation_ids_by_collection=relation_ids_by_collection,
            )

        receipt = {
            "completeness": batch.completeness,
            "item_count": len(batch.items),
            "cursor_end": batch.cursor,
            "failure_code": batch.failure_code,
            "scope": "account_relation" if batch.scope_type == "relation" else "account_collection_batch",
            "scope_type": batch.scope_type,
            "batch_index": batch.batch_index,
            "batch_count": batch.batch_count,
            "relation_type": batch.relation_type,
            "collection_key": batch.collection_key,
            "source_account_id": account["external_account_id"],
            "started_at": run.get("started_at") or utcnow(),
        }
        self.store.record_scan_receipt(
            account["platform"],
            f"{sync_run_id}:{batch.relation_type}:{batch.scope_type}:{batch.collection_key}:{batch.batch_index}:{len(run.get('events') or [])}",
            receipt,
            source_account_id=account["external_account_id"],
            relation_type=batch.relation_type,
        )

        # Every data batch updates counters and a resumable collection checkpoint.
        if batch.scope_type == "collection":
            collection_scope = batch.collection_key or "__mixed__"
            collection_complete = batch.completeness == "complete" and not batch.has_more and bool(batch.collection_key)
            self.store.upsert_sync_run_scope(
                sync_run_id=sync_run_id,
                relation_type=batch.relation_type,
                collection_key=collection_scope,
                status="complete" if collection_complete and not errors else ("partial" if errors else "scanning"),
                completeness="complete" if collection_complete and not errors else ("partial" if errors else "unknown"),
                discovered_delta=len(batch.items),
                imported_delta=len(responses),
                failed_delta=len(errors),
            )
            closed_candidates = 0
            if collection_complete and not errors:
                observed = self.store.list_sync_seen_relation_ids(
                    sync_run_id=sync_run_id,
                    relation_type=batch.relation_type,
                    collection_key=batch.collection_key,
                )
                closed_candidates = self.store.apply_complete_scan(
                    account["platform"],
                    observed,
                    relation_type=batch.relation_type,
                    collection_key=batch.collection_key,
                    source_account_id=account["external_account_id"],
                )
            self.store.upsert_sync_checkpoint(
                source_account_id=account["id"],
                relation_type=batch.relation_type,
                collection_key=collection_scope,
                cursor=batch.cursor,
                known_anchor=batch.known_anchor,
                last_complete_sync_run_id=sync_run_id if collection_complete and not errors else None,
                complete=collection_complete and not errors,
            )
            self.store.update_sync_run(
                sync_run_id,
                status="scanning",
                completeness="unknown",
                discovered_delta=len(batch.items),
                imported_delta=len(responses),
                failed_delta=len(errors),
                cursor={
                    "relation_type": batch.relation_type,
                    "collection_key": collection_scope,
                    "batch_index": batch.batch_index,
                    **batch.cursor,
                },
                error_code=batch.failure_code,
                error_message=(errors[0].get("message") if errors else None),
                evidence={
                    "waiting_for_relation_final": True,
                    "has_more": batch.has_more,
                    "closed_candidate_count": closed_candidates,
                },
            )
            next_status = "scanning"
        else:
            next_status, closed_candidates = self._finalize_relation_scope(
                sync_run_id=sync_run_id,
                run=run,
                account=account,
                relation_type=batch.relation_type,
                completeness=batch.completeness,
                failure_code=batch.failure_code,
                errors=errors,
            )

        return {
            "sync_run_id": sync_run_id,
            "status": next_status,
            "scope_type": batch.scope_type,
            "accepted": len(responses),
            "failed": len(errors),
            "content_ids": [item.content_id for item in responses],
            "errors": errors,
            "has_more": batch.has_more,
            "next_action_zh": (
                "继续后台同步。" if batch.scope_type == "collection"
                else ("本次账号同步完成。" if next_status == "completed" else "该关系已结束，继续处理其余关系。" if next_status == "scanning" else "同步部分完成，可从断点继续。")
            ),
        }
