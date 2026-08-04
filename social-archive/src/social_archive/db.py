from __future__ import annotations

import json
import re
import secrets
import sqlite3
from contextlib import contextmanager
from datetime import UTC, datetime, timedelta
from importlib.resources import files
from pathlib import Path
from typing import Any, Iterator

from .models import CaptureRequest
from .utils import canonicalize_url, json_bytes, sha256_bytes, stable_id, utcnow


_CJK_HAN_RE = re.compile(r"[\u3400-\u4dbf\u4e00-\u9fff\uf900-\ufaff]")
_CJK_HAN_RUN_RE = re.compile(r"[\u3400-\u4dbf\u4e00-\u9fff\uf900-\ufaff]+")


def _literal_fts_query(value: str) -> str | None:
    """Turn non-CJK user text into literal FTS terms instead of accepting operators."""
    tokens = re.findall(r"\w+", _CJK_HAN_RUN_RE.sub(" ", value), flags=re.UNICODE)
    if not tokens:
        return None
    return " AND ".join(f'"{token}"' for token in tokens)


def _cjk_substrings(value: str) -> list[str]:
    """Return literal Han runs for a substring fallback.

    SQLite's unicode61 tokenizer indexes a contiguous Han phrase as one token.
    A person searching a prefix inside that phrase must still be able to find it.
    """
    return list(dict.fromkeys(_CJK_HAN_RUN_RE.findall(value)))


def _like_pattern(value: str) -> str:
    return "%" + value.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_") + "%"


class RuntimeStore:
    def __init__(self, path: Path):
        self.path = path
        self.path.parent.mkdir(parents=True, exist_ok=True)

    @contextmanager
    def connection(self) -> Iterator[sqlite3.Connection]:
        con = sqlite3.connect(self.path, timeout=30, isolation_level=None)
        con.row_factory = sqlite3.Row
        con.execute("PRAGMA foreign_keys=ON")
        con.execute("PRAGMA busy_timeout=30000")
        try:
            yield con
        finally:
            con.close()

    def initialize(self) -> None:
        schema = files("social_archive").joinpath("sql/runtime_schema.sql").read_text(encoding="utf-8")
        account_additions = {
            "connection_state": "TEXT NOT NULL DEFAULT 'disconnected'",
            "auth_method": "TEXT",
            "auth_handle_ref": "TEXT",
            "auto_sync_enabled": "INTEGER NOT NULL DEFAULT 1",
            "sync_interval_minutes": "INTEGER NOT NULL DEFAULT 360",
            "last_verified_at": "TEXT",
            "last_sync_at": "TEXT",
            "last_error_code": "TEXT",
            "metadata_json": "TEXT NOT NULL DEFAULT '{}'",
        }
        content_additions = {
            "summary": "TEXT",
            "language": "TEXT",
            "media_count": "INTEGER NOT NULL DEFAULT 0",
            "last_synced_at": "TEXT",
        }
        relation_additions = {
            "relation_observed_at": "TEXT",
            "external_relation_id": "TEXT",
            "source_order": "INTEGER",
            "last_sync_run_id": "TEXT",
        }
        with self.connection() as con:
            # The schema adds an index over connection_state.  Upgrade an
            # existing pre-v0.0.0.6 source_account before executescript reaches
            # that index; a fresh database has no table yet and is created with
            # the full definition below.
            account_columns = {row[1] for row in con.execute("PRAGMA table_info(source_account)").fetchall()}
            for name, declaration in account_additions.items():
                if account_columns and name not in account_columns:
                    con.execute(f"ALTER TABLE source_account ADD COLUMN {name} {declaration}")
            # These columns are indexed by the current schema, so legacy rows
            # must gain them before executescript creates the indexes.
            content_columns = {row[1] for row in con.execute("PRAGMA table_info(content)").fetchall()}
            for name, declaration in content_additions.items():
                if content_columns and name not in content_columns:
                    con.execute(f"ALTER TABLE content ADD COLUMN {name} {declaration}")
            relation_columns = {row[1] for row in con.execute("PRAGMA table_info(user_relation)").fetchall()}
            for name, declaration in relation_additions.items():
                if relation_columns and name not in relation_columns:
                    con.execute(f"ALTER TABLE user_relation ADD COLUMN {name} {declaration}")
            # v0.0.0.7 / T01 多租户。这四张表的 user_id 被下面的租户索引引用，
            # 所以必须在 executescript 之前就位，否则 CREATE INDEX 会因缺列而失败。
            self._add_tenant_columns(con)
            con.executescript(schema)
            # 回填必须在建表之后（users 表要先存在），且在任何读取之前。
            self._backfill_owner_tenancy(con)
            con.execute(
                "UPDATE user_relation SET relation_observed_at=COALESCE(relation_observed_at,first_observed_at)"
            )
            # Additive migration for pre-v0.0.0.4 runtime databases. SQLite remains
            # rebuildable, but preserving an existing queue avoids unnecessary loss.
            columns = {row[1] for row in con.execute("PRAGMA table_info(object_replica)").fetchall()}
            if "original_sha256" not in columns:
                con.execute("ALTER TABLE object_replica ADD COLUMN original_sha256 TEXT")
            if "encryption" not in columns:
                con.execute("ALTER TABLE object_replica ADD COLUMN encryption TEXT")
            destination_columns = {row[1] for row in con.execute("PRAGMA table_info(destination_state)").fetchall()}
            destination_additions = {
                "last_checked_at": "TEXT",
                "latency_ms": "INTEGER",
                "capabilities_json": "TEXT NOT NULL DEFAULT '{}'",
                "last_message_zh": "TEXT",
            }
            for name, declaration in destination_additions.items():
                if name not in destination_columns:
                    con.execute(f"ALTER TABLE destination_state ADD COLUMN {name} {declaration}")
            connector_columns = {row[1] for row in con.execute("PRAGMA table_info(connector_state)").fetchall()}
            connector_additions = {
                "last_checked_at": "TEXT",
                "latency_ms": "INTEGER",
                "last_message_zh": "TEXT",
            }
            for name, declaration in connector_additions.items():
                if name not in connector_columns:
                    con.execute(f"ALTER TABLE connector_state ADD COLUMN {name} {declaration}")

    # ── 多租户（v0.0.0.7 / T01）──────────────────────────────────────

    #: 只有 Owner 一个用户时的确定性 id。确定性是有意的——迁移可以重复跑，
    #: 回滚脚本也需要一个不必猜的目标。
    OWNER_USER_ID = stable_id("usr", "owner")

    #: 带 user_id 的表。content 与 artifact **有意不在此列**：它们是内容寻址、
    #: 全局去重的，两个用户收藏同一条内容时只有一行，user_id 只能记"谁先到"，
    #: 那是假隔离。真正的所有权边是 user_relation。
    TENANT_TABLES = ("source_account", "user_relation", "platform_collection", "sync_run")

    #: 身份／凭据类的表也带 user_id，但它们**不经 for_user 收敛**——
    #: 它们不是"内容"，是"这个人是谁 / 他授权了什么"，读取路径本来就按会话直查。
    #: 它们建表时 user_id 就是 NOT NULL，结构上不可能为空。
    #:
    #: 但 T01 的 Oracle 原文是「**各表** user_id 为空 = 0」——审计必须把它们也数进去，
    #: 否则审计报的是"我数过的那几张表没问题"，而不是"没问题"。
    #: T05 加 platform_credential 时就漏了：8 张表带 user_id，审计只覆盖 4 张。
    IDENTITY_TABLES = ("oauth_identity", "session", "extension_token", "platform_credential")

    #: 审计面 = 内容租户表 + 身份凭据表。新增任何带 user_id 的表都必须进这两者之一，
    #: 有 test_every_user_id_table_is_audited 盯着。
    AUDITED_TABLES = TENANT_TABLES + IDENTITY_TABLES

    def _add_tenant_columns(self, con: sqlite3.Connection) -> None:
        """幂等地给既有表加 user_id。新库这些表还不存在，跳过即可。"""
        for table in self.TENANT_TABLES:
            columns = {row[1] for row in con.execute(f"PRAGMA table_info({table})").fetchall()}
            if columns and "user_id" not in columns:
                con.execute(f"ALTER TABLE {table} ADD COLUMN user_id TEXT REFERENCES users(id)")

    def _backfill_owner_tenancy(self, con: sqlite3.Connection) -> None:
        """把既有数据全部归属给 Owner。

        本版本只有 Owner 一个用户，所以"归属"是无歧义的。这一步必须做到
        **一行不剩**——T01 的验收就是"不存在 user_id 为空的业务行"。

        只有在确实存在待回填的行时才建 Owner 行，避免给一个全新的空库
        凭空塞一个用户。
        """
        pending = sum(
            con.execute(f"SELECT COUNT(*) FROM {table} WHERE user_id IS NULL OR user_id=''").fetchone()[0]
            for table in self.TENANT_TABLES
        )
        if not pending:
            return
        con.execute(
            "INSERT OR IGNORE INTO users(id, display_name, created_at, is_owner) VALUES(?,?,?,1)",
            (self.OWNER_USER_ID, "Owner", utcnow()),
        )
        for table in self.TENANT_TABLES:
            con.execute(
                f"UPDATE {table} SET user_id=? WHERE user_id IS NULL OR user_id=''",
                (self.OWNER_USER_ID,),
            )

    def _ensure_owner_user(self, con: sqlite3.Connection, now: str) -> str:
        """保证 Owner 行存在并返回其 id。

        写入路径必须能拿到一个真实存在的 user_id：user_id 上有外键，指向
        不存在的行会直接违反约束。这一步幂等，重复调用不产生第二行。
        """
        con.execute(
            "INSERT OR IGNORE INTO users(id, display_name, created_at, is_owner) VALUES(?,?,?,1)",
            (self.OWNER_USER_ID, "Owner", now),
        )
        return self.OWNER_USER_ID

    def tenancy_audit(self) -> dict[str, Any]:
        """T01 的 Oracle：每张带 user_id 的表还剩几行没有归属。全部为 0 才算迁移完成。

        覆盖面是 AUDITED_TABLES（内容租户表 + 身份凭据表），不是只有 TENANT_TABLES。
        少数一张，审计报的就是"我数过的那几张没问题"而不是"没问题"——
        这台机器已经在别处吃过这个亏。

        `uncovered_tables` 是审计对自己的检查：库里任何带 user_id 却不在
        AUDITED_TABLES 里的表都会被列出来。它非空就说明审计面漏了。
        """
        with self.connection() as con:
            present = {
                row[0] for row in con.execute(
                    "SELECT name FROM sqlite_master WHERE type='table'"
                ).fetchall()
            }
            audited = [table for table in self.AUDITED_TABLES if table in present]
            uncovered = sorted(
                name for name in present
                if name not in self.AUDITED_TABLES
                and any(
                    column[1] == "user_id"
                    for column in con.execute(f"PRAGMA table_info({name})").fetchall()
                )
            )
            return {
                "orphan_rows": {
                    table: con.execute(
                        f"SELECT COUNT(*) FROM {table} WHERE user_id IS NULL OR user_id=''"
                    ).fetchone()[0]
                    for table in audited
                },
                "total_rows": {
                    table: con.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
                    for table in audited
                },
                "audited_tables": audited,
                "uncovered_tables": uncovered,
                "users": con.execute("SELECT COUNT(*) FROM users").fetchone()[0],
            }

    def for_user(self, user_id: str) -> "TenantScope":
        """取得一个按 user_id 收敛的读取视图。

        面向用户的读取一律走这里。裸 RuntimeStore 的同名方法保留给 worker 与
        运维路径（它们本来就要跨用户看作业队列），但**不得**被 API 层直接调用。
        """
        if not user_id:
            raise ValueError("user_id 不能为空——空 user_id 会退化成全库读取")
        return TenantScope(self, user_id)

    # ── 登录会话与身份（v0.0.0.7 / T02）──────────────────────────────

    def upsert_oauth_identity(
        self, *, provider: str, subject: str, display_name: str | None
    ) -> str:
        """按 (provider, subject) 找人；第一次见到就建用户。返回 user_id。

        用 provider 侧的稳定 subject 而不是邮箱做主键：邮箱可以改，改了就会变成
        另一个人，历史数据全部失联。
        """
        if provider not in {"google", "github"}:
            raise ValueError(f"未知的登录方式 {provider}")
        if not subject:
            raise ValueError("provider 未返回 subject，拒绝建立身份")
        now = utcnow()
        identity_id = stable_id("oid", provider, subject)
        with self.connection() as con:
            row = con.execute(
                "SELECT user_id FROM oauth_identity WHERE provider=? AND subject=?",
                (provider, subject),
            ).fetchone()
            if row:
                return str(row["user_id"])
            # 本版本站点仍在 Cloudflare Access 后面，只有 Owner 进得来，
            # 所以第一个登录的人就是 Owner；T01 迁移建的那行也用同一个 id。
            existing_owner = con.execute("SELECT id FROM users WHERE is_owner=1").fetchone()
            if existing_owner:
                user_id = str(existing_owner["id"])
            else:
                user_id = self.OWNER_USER_ID
                con.execute(
                    "INSERT OR IGNORE INTO users(id,display_name,created_at,is_owner) VALUES(?,?,?,1)",
                    (user_id, display_name or "Owner", now),
                )
            if display_name:
                con.execute(
                    "UPDATE users SET display_name=COALESCE(display_name,?) WHERE id=?",
                    (display_name, user_id),
                )
            con.execute(
                "INSERT INTO oauth_identity(id,user_id,provider,subject,created_at) VALUES(?,?,?,?,?)",
                (identity_id, user_id, provider, subject, now),
            )
            return user_id

    def create_session(self, *, user_id: str, ttl_seconds: int = 60 * 60 * 24 * 30) -> str:
        """签发会话。返回的 id 就是 Cookie 里放的值——不用 JWT，撤销更简单。"""
        session_id = secrets.token_urlsafe(32)
        now = datetime.now(UTC)
        with self.connection() as con:
            con.execute(
                "INSERT INTO session(id,user_id,created_at,expires_at) VALUES(?,?,?,?)",
                (
                    session_id,
                    user_id,
                    now.isoformat(),
                    (now + timedelta(seconds=ttl_seconds)).isoformat(),
                ),
            )
        return session_id

    def resolve_session(self, session_id: str) -> str | None:
        """会话 → user_id。过期或已撤销一律返回 None。

        过期判断放在 SQL 里而不是取出来再比：少一次"忘了比"的机会。
        """
        if not session_id:
            return None
        with self.connection() as con:
            row = con.execute(
                """SELECT user_id FROM session
                   WHERE id=? AND revoked_at IS NULL AND expires_at > ?""",
                (session_id, datetime.now(UTC).isoformat()),
            ).fetchone()
        return str(row["user_id"]) if row else None

    def revoke_session(self, session_id: str) -> bool:
        with self.connection() as con:
            cur = con.execute(
                "UPDATE session SET revoked_at=? WHERE id=? AND revoked_at IS NULL",
                (utcnow(), session_id),
            )
        return cur.rowcount > 0

    # ── 扩展令牌（v0.0.0.7 / T03）────────────────────────────────────
    #
    # 取代旧的一次性码。它在真实使用中连续失败三次（CONFLICT_ORDER 已废止它）：
    # 十分钟有效期 + 手抄验证码本身就是技术门槛，与 INV-ZERO-BARRIER 直接冲突。
    #
    # 长期、可撤销、绑 user_id。明文只在签发那一刻返回一次，库里只留哈希——
    # 库被读走也冒充不了扩展。

    @staticmethod
    def _hash_extension_token(plaintext: str) -> str:
        return sha256_bytes(plaintext.encode("utf-8"))

    def issue_extension_token(self, *, user_id: str) -> str:
        """签发一枚新令牌并**撤销该用户此前所有令牌**。

        为什么顺手撤旧的：用户重装扩展时会再点一次连接，旧令牌就此失联却仍然有效——
        那是一枚永远没人用、也永远没人撤的活令牌。一次一枚，语义干净。
        """
        plaintext = secrets.token_urlsafe(32)
        now = utcnow()
        with self.connection() as con:
            con.execute(
                "UPDATE extension_token SET revoked_at=? WHERE user_id=? AND revoked_at IS NULL",
                (now, user_id),
            )
            con.execute(
                "INSERT INTO extension_token(id,user_id,token_hash,created_at) VALUES(?,?,?,?)",
                (stable_id("ext", user_id, now, plaintext), user_id,
                 self._hash_extension_token(plaintext), now),
            )
        return plaintext

    def resolve_extension_token(self, plaintext: str) -> str | None:
        """令牌 → user_id。已撤销的返回 None。

        按哈希查而不是取出来逐个比：库里本来就没有明文可比。
        """
        if not plaintext:
            return None
        with self.connection() as con:
            row = con.execute(
                "SELECT user_id FROM extension_token WHERE token_hash=? AND revoked_at IS NULL",
                (self._hash_extension_token(plaintext),),
            ).fetchone()
        return str(row["user_id"]) if row else None

    def revoke_extension_tokens(self, user_id: str) -> int:
        """一键撤销。撤销后扩展上行应当立刻拿到 401（T03 Oracle）。"""
        with self.connection() as con:
            cur = con.execute(
                "UPDATE extension_token SET revoked_at=? WHERE user_id=? AND revoked_at IS NULL",
                (utcnow(), user_id),
            )
        return cur.rowcount

    def revoke_all_sessions(self, user_id: str) -> int:
        """撤销某人全部会话。设备丢了、或怀疑泄漏时用。"""
        with self.connection() as con:
            cur = con.execute(
                "UPDATE session SET revoked_at=? WHERE user_id=? AND revoked_at IS NULL",
                (utcnow(), user_id),
            )
        return cur.rowcount

    def capture(self, request: CaptureRequest) -> tuple[str, str, str]:
        now = utcnow()
        relation_time = request.relation_observed_at or now
        canonical_url = canonicalize_url(str(request.url))
        platform = request.platform.lower()
        content_id = stable_id("cnt", platform, request.external_content_id or canonical_url)
        account_id = stable_id("acct", platform, request.source_account_id) if request.source_account_id else None
        relation_id = stable_id("rel", account_id or "owner", content_id, request.relation_type, request.collection_key)
        payload = request.model_dump(mode="json")
        payload_bytes = json_bytes(payload)
        observation_id = stable_id("obs", platform, sha256_bytes(payload_bytes))
        metadata_json = json.dumps(request.raw_metadata, ensure_ascii=False, sort_keys=True)
        summary = (request.text or "").strip()[:1000] or None
        keywords = list(dict.fromkeys(item.strip() for item in request.keywords if item and item.strip()))[:32]
        topic = (request.topic or "未分类").strip()[:256] or "未分类"
        with self.connection() as con:
            con.execute("BEGIN IMMEDIATE")
            con.execute(
                """INSERT INTO content(id,platform,external_content_id,canonical_url,title,author_name,published_at,first_observed_at,last_observed_at,metadata_json,summary,language,media_count,last_synced_at)
                   VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)
                   ON CONFLICT(id) DO UPDATE SET
                     title=COALESCE(excluded.title,content.title),
                     author_name=COALESCE(excluded.author_name,content.author_name),
                     published_at=COALESCE(excluded.published_at,content.published_at),
                     last_observed_at=excluded.last_observed_at,
                     metadata_json=excluded.metadata_json,
                     summary=COALESCE(excluded.summary,content.summary),
                     language=COALESCE(excluded.language,content.language),
                     media_count=MAX(content.media_count,excluded.media_count),
                     last_synced_at=excluded.last_synced_at""",
                (content_id, platform, request.external_content_id, canonical_url, request.title, request.author_name, request.published_at, now, now, metadata_json, summary, request.language, len(request.media_urls), now),
            )
            # 归属：本版本只有 Owner 一个用户，故写入路径统一落 OWNER_USER_ID。
            # T02 接上登录后，这里改成从会话取真实 user_id——这是那一步唯一要动的地方。
            owner = self._ensure_owner_user(con, now)
            if request.source_account_id:
                con.execute(
                    """INSERT INTO source_account(id,user_id,platform,external_account_id,created_at,updated_at)
                       VALUES(?,?,?,?,?,?)
                       ON CONFLICT(id) DO UPDATE SET platform=excluded.platform,external_account_id=excluded.external_account_id,updated_at=excluded.updated_at""",
                    (account_id, owner, platform, request.source_account_id, now, now),
                )
            con.execute(
                """INSERT INTO user_relation(id,user_id,source_account_id,content_id,relation_type,collection_key,status,first_observed_at,last_observed_at,relation_observed_at,missing_complete_scan_count,last_sync_run_id)
                   VALUES(?,?,?,?,?,?,'active',?,?,?,?,?)
                   ON CONFLICT(id) DO UPDATE SET
                     status='active',
                     last_observed_at=excluded.last_observed_at,
                     relation_observed_at=COALESCE(excluded.relation_observed_at,user_relation.relation_observed_at),
                     missing_complete_scan_count=0,
                     last_sync_run_id=COALESCE(excluded.last_sync_run_id,user_relation.last_sync_run_id),
                     closed_at=NULL""",
                (relation_id, owner, account_id, content_id, request.relation_type, request.collection_key, now, now, relation_time, 0, str(request.raw_metadata.get("sync_run_id") or "") or None),
            )
            con.execute(
                "INSERT OR IGNORE INTO observation(id,connector_id,content_id,observed_at,payload_json,payload_sha256) VALUES(?,?,?,?,?,?)",
                (observation_id, f"capture:{platform}", content_id, now, payload_bytes.decode("utf-8"), sha256_bytes(payload_bytes)),
            )
            con.execute(
                """INSERT INTO content_classification(content_id,topic,keywords_json,confidence,source,updated_at)
                   VALUES(?,?,?,?,?,?)
                   ON CONFLICT(content_id) DO UPDATE SET
                     topic=CASE WHEN excluded.topic!='未分类' THEN excluded.topic ELSE content_classification.topic END,
                     keywords_json=CASE WHEN excluded.keywords_json!='[]' THEN excluded.keywords_json ELSE content_classification.keywords_json END,
                     confidence=MAX(content_classification.confidence,excluded.confidence),
                     source=CASE WHEN excluded.topic!='未分类' OR excluded.keywords_json!='[]' THEN excluded.source ELSE content_classification.source END,
                     updated_at=excluded.updated_at""",
                (content_id, topic, json.dumps(keywords, ensure_ascii=False), 1.0 if request.topic or keywords else 0.0, str(request.raw_metadata.get("classification_source") or "connector"), now),
            )
            stored_content = con.execute(
                "SELECT title,author_name FROM content WHERE id=?",
                (content_id,),
            ).fetchone()
            previous_fts = con.execute(
                "SELECT body FROM content_fts WHERE content_id=?",
                (content_id,),
            ).fetchone()
            body = request.text if request.text is not None else (str(previous_fts["body"]) if previous_fts else "")
            collection_rows = con.execute(
                """SELECT DISTINCT collection_key FROM user_relation
                   WHERE content_id=? AND collection_key<>'' ORDER BY collection_key""",
                (content_id,),
            ).fetchall()
            fts_tags = " ".join([*(str(row["collection_key"]) for row in collection_rows), topic, *keywords])
            con.execute("DELETE FROM content_fts WHERE content_id=?", (content_id,))
            con.execute(
                "INSERT INTO content_fts(content_id,title,author_name,body,tags) VALUES(?,?,?,?,?)",
                (content_id, str(stored_content["title"] or ""), str(stored_content["author_name"] or ""), body, fts_tags),
            )
            con.execute("COMMIT")
        return content_id, relation_id, observation_id

    def add_artifact(self, *, content_id: str, archive_level: str, artifact_type: str, sha256: str, byte_size: int, media_type: str | None, local_path: str | None, status: str = "staged") -> str:
        artifact_id = stable_id("art", content_id, artifact_type, sha256)
        with self.connection() as con:
            con.execute(
                """INSERT INTO artifact(id,content_id,archive_level,artifact_type,sha256,byte_size,media_type,local_path,created_at,status)
                   VALUES(?,?,?,?,?,?,?,?,?,?) ON CONFLICT(id) DO UPDATE SET status=excluded.status,local_path=COALESCE(excluded.local_path,artifact.local_path)""",
                (artifact_id, content_id, archive_level, artifact_type, sha256, byte_size, media_type, local_path, utcnow(), status),
            )
        return artifact_id

    def destination_coverage(self) -> dict[str, int]:
        """每个目的地**真的收到过多少条内容**。

        为什么要有它：2026-08-04 实测，github 与 obsidian 的状态都是
        `connected` + 「最近一次自动导入成功。」，而它们各自只有 **1 条**回执
        ——库里有 193 条。默认导出集是 `["social_archive", "markdown"]`
        （扩展的 DEFAULT_CONFIG 与 account_sync 两处都是），所以那两个目的地
        从来就没有自动收到过东西。

        界面说「连接成功、自动导入」，而实际是 1/193。**这不是谎，是没说全。**
        把「收到了多少条」摆出来，比任何措辞都直接。
        """
        with self.connection() as con:
            rows = con.execute(
                """SELECT destination_id, COUNT(DISTINCT content_id) AS n
                   FROM destination_receipt WHERE status IN ('done','noop')
                   GROUP BY destination_id"""
            ).fetchall()
        return {row["destination_id"]: int(row["n"]) for row in rows}

    def content_total(self) -> int:
        with self.connection() as con:
            return int(con.execute("SELECT COUNT(*) FROM content").fetchone()[0])

    def enqueue_job(self, job_type: str, payload: dict[str, Any], connector_id: str | None = None) -> str:
        payload_raw = json.dumps(payload, ensure_ascii=False, sort_keys=True)
        job_id = stable_id("job", job_type, connector_id, sha256_bytes(payload_raw.encode("utf-8")))
        now = utcnow()
        with self.connection() as con:
            con.execute(
                """INSERT OR IGNORE INTO job(id,job_type,connector_id,payload_json,status,attempt_count,not_before,created_at,updated_at)
                   VALUES(?,?,?,?,'queued',0,?,?,?)""",
                (job_id, job_type, connector_id, payload_raw, now, now, now),
            )
            # **失败过的活儿，要能被重新请求。**
            #
            # job_id 是 (job_type, connector_id, payload) 的稳定哈希，配 INSERT OR IGNORE
            # ——对**还没跑完**的活儿这是对的：同一件事不该排两次。
            # 但一条 status='failed' 的记录会把这件事**永久钉死**：之后每一次
            # enqueue 都被 IGNORE 掉，接口照样返回 job_id 和 202，界面照样说
            # 「已加入队列」，而**没有任何东西会跑**。
            #
            # 2026-08-04 实测：markdown 导出修好之后我重排 83 条，79 条跑了，
            # 剩下 4 条纹丝不动——它们在 2026-08-03T17:23 失败过，job 表里那一行
            # 从那时起就没再动过。接口返回的是那 4 个旧 id。
            #
            # 只复活 failed。queued/running/retry 不动（本来就要跑），
            # done 也不动——把已完成的活儿因为一次重复入队就重跑，
            # 是另一种意外，得由调用方明确要求。
            con.execute(
                """UPDATE job SET status='queued', not_before=?, lease_owner=NULL,
                       lease_expires_at=NULL, updated_at=?
                   WHERE id=? AND status='failed'""",
                (now, now, job_id),
            )
        return job_id

    def claim_job(self, owner: str, lease_seconds: int = 120) -> dict[str, Any] | None:
        with self.connection() as con:
            con.execute("BEGIN IMMEDIATE")
            row = con.execute(
                """SELECT * FROM job WHERE status IN ('queued','retry') AND not_before <= strftime('%Y-%m-%dT%H:%M:%fZ','now')
                   AND (lease_expires_at IS NULL OR lease_expires_at < strftime('%Y-%m-%dT%H:%M:%fZ','now')) ORDER BY created_at LIMIT 1"""
            ).fetchone()
            if row is None:
                con.execute("COMMIT")
                return None
            con.execute(
                """UPDATE job SET status='running',lease_owner=?,lease_expires_at=strftime('%Y-%m-%dT%H:%M:%fZ','now',?),attempt_count=attempt_count+1,updated_at=? WHERE id=?""",
                (owner, f"+{lease_seconds} seconds", utcnow(), row["id"]),
            )
            con.execute("COMMIT")
            result = dict(row)
            result["payload"] = json.loads(result.pop("payload_json"))
            return result

    def finish_job(
        self,
        job_id: str,
        *,
        success: bool,
        error_code: str | None = None,
        error_message: str | None = None,
        retryable: bool = False,
        retry_after_seconds: int | None = None,
    ) -> None:
        status = "done" if success else ("retry" if retryable else "failed")
        requested_delay = 60 if retry_after_seconds is None else retry_after_seconds
        delay_seconds = min(max(int(requested_delay), 1), 3600)
        with self.connection() as con:
            con.execute(
                """UPDATE job SET status=?,updated_at=?,lease_owner=NULL,lease_expires_at=NULL,last_error_code=?,last_error_message=?,
                   not_before=CASE WHEN ?='retry' THEN strftime('%Y-%m-%dT%H:%M:%fZ','now',?) ELSE not_before END WHERE id=?""",
                (status, utcnow(), error_code, error_message, status, f"+{delay_seconds} seconds", job_id),
            )

    def retry_job(self, job_id: str) -> bool:
        """Move a terminal/retryable job back to the queue without changing its identity."""
        with self.connection() as con:
            row = con.execute("SELECT status FROM job WHERE id=?", (job_id,)).fetchone()
            if row is None or row["status"] in {"running", "done"}:
                return False
            con.execute(
                """UPDATE job SET status='queued',not_before=?,lease_owner=NULL,lease_expires_at=NULL,
                   last_error_code=NULL,last_error_message=NULL,updated_at=? WHERE id=?""",
                (utcnow(), utcnow(), job_id),
            )
            return True

    def get_job(self, job_id: str) -> dict[str, Any] | None:
        with self.connection() as con:
            row = con.execute("SELECT id,job_type,connector_id,status,attempt_count,created_at,updated_at,last_error_code,last_error_message FROM job WHERE id=?", (job_id,)).fetchone()
            return dict(row) if row else None

    def list_jobs(self, *, limit: int = 100, status: str | None = None) -> list[dict[str, Any]]:
        clauses = ["1=1"]
        args: list[Any] = []
        if status:
            clauses.append("status=?")
            args.append(status)
        args.append(min(max(limit, 1), 500))
        with self.connection() as con:
            rows = con.execute(
                f"""SELECT id,job_type,connector_id,status,attempt_count,created_at,updated_at,last_error_code,last_error_message
                    FROM job WHERE {' AND '.join(clauses)} ORDER BY updated_at DESC LIMIT ?""",
                args,
            ).fetchall()
            return [dict(row) for row in rows]

    def upsert_destination_state(
        self,
        destination_id: str,
        *,
        state: str,
        enabled: bool,
        error_code: str | None = None,
        last_checked_at: str | None = None,
        latency_ms: int | None = None,
        capabilities: dict[str, Any] | None = None,
        message_zh: str | None = None,
    ) -> None:
        now = utcnow()
        success_at = now if state == "connected" else None
        failure_at = now if state in {"degraded", "expired", "blocked_policy"} else None
        capabilities_json = json.dumps(capabilities or {}, ensure_ascii=False, sort_keys=True)
        with self.connection() as con:
            con.execute(
                """INSERT INTO destination_state(
                     destination_id,state,enabled,last_success_at,last_failure_at,last_error_code,
                     last_checked_at,latency_ms,capabilities_json,last_message_zh,updated_at
                   ) VALUES(?,?,?,?,?,?,?,?,?,?,?)
                   ON CONFLICT(destination_id) DO UPDATE SET
                     state=excluded.state,enabled=excluded.enabled,
                     last_success_at=COALESCE(excluded.last_success_at,destination_state.last_success_at),
                     last_failure_at=COALESCE(excluded.last_failure_at,destination_state.last_failure_at),
                     last_error_code=excluded.last_error_code,
                     last_checked_at=COALESCE(excluded.last_checked_at,destination_state.last_checked_at),
                     latency_ms=COALESCE(excluded.latency_ms,destination_state.latency_ms),
                     capabilities_json=COALESCE(excluded.capabilities_json,destination_state.capabilities_json),
                     last_message_zh=COALESCE(excluded.last_message_zh,destination_state.last_message_zh),
                     updated_at=excluded.updated_at""",
                (
                    destination_id,
                    state,
                    1 if enabled else 0,
                    success_at,
                    failure_at,
                    error_code,
                    last_checked_at,
                    latency_ms,
                    capabilities_json,
                    message_zh,
                    now,
                ),
            )

    def destination_states(self) -> list[dict[str, Any]]:
        with self.connection() as con:
            rows = [dict(row) for row in con.execute("SELECT * FROM destination_state ORDER BY destination_id").fetchall()]
        for row in rows:
            raw = row.pop("capabilities_json", "{}") or "{}"
            try:
                row["capabilities"] = json.loads(raw)
            except (TypeError, ValueError):
                row["capabilities"] = {}
        return rows

    def get_destination_binding(self, destination_id: str, content_id: str) -> dict[str, Any] | None:
        with self.connection() as con:
            row = con.execute(
                "SELECT * FROM destination_binding WHERE destination_id=? AND content_id=?",
                (destination_id, content_id),
            ).fetchone()
        if not row:
            return None
        result = dict(row)
        try:
            result["metadata"] = json.loads(result.pop("metadata_json") or "{}")
        except (TypeError, ValueError):
            result["metadata"] = {}
        return result

    def upsert_destination_binding(
        self,
        *,
        destination_id: str,
        content_id: str,
        projection_sha256: str,
        remote_id: str | None = None,
        remote_path: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> str:
        binding_id = stable_id("dstbind", destination_id, content_id)
        with self.connection() as con:
            con.execute(
                """INSERT INTO destination_binding(
                     id,destination_id,content_id,remote_id,remote_path,projection_sha256,last_export_at,metadata_json
                   ) VALUES(?,?,?,?,?,?,?,?)
                   ON CONFLICT(destination_id,content_id) DO UPDATE SET
                     remote_id=COALESCE(excluded.remote_id,destination_binding.remote_id),
                     remote_path=COALESCE(excluded.remote_path,destination_binding.remote_path),
                     projection_sha256=excluded.projection_sha256,last_export_at=excluded.last_export_at,
                     metadata_json=excluded.metadata_json""",
                (
                    binding_id,
                    destination_id,
                    content_id,
                    remote_id,
                    remote_path,
                    projection_sha256,
                    utcnow(),
                    json.dumps(metadata or {}, ensure_ascii=False, sort_keys=True),
                ),
            )
        return binding_id

    def record_destination_receipt(
        self,
        *,
        destination_id: str,
        content_id: str,
        status: str,
        projection_sha256: str,
        attempted_at: str,
        message_zh: str,
        job_id: str | None = None,
        remote_id: str | None = None,
        remote_path: str | None = None,
        error_code: str | None = None,
        evidence: dict[str, Any] | None = None,
    ) -> str:
        finished_at = utcnow()
        receipt_id = stable_id(
            "dstreceipt", destination_id, content_id, job_id or attempted_at, status, projection_sha256
        )
        with self.connection() as con:
            con.execute(
                """INSERT INTO destination_receipt(
                     id,job_id,destination_id,content_id,status,projection_sha256,remote_id,remote_path,
                     attempted_at,finished_at,error_code,message_zh,evidence_json
                   ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)
                   ON CONFLICT(id) DO UPDATE SET
                     status=excluded.status,remote_id=excluded.remote_id,remote_path=excluded.remote_path,
                     finished_at=excluded.finished_at,error_code=excluded.error_code,
                     message_zh=excluded.message_zh,evidence_json=excluded.evidence_json""",
                (
                    receipt_id,
                    job_id,
                    destination_id,
                    content_id,
                    status,
                    projection_sha256,
                    remote_id,
                    remote_path,
                    attempted_at,
                    finished_at,
                    error_code,
                    message_zh,
                    json.dumps(evidence or {}, ensure_ascii=False, sort_keys=True),
                ),
            )
        return receipt_id

    def list_destination_receipts(
        self,
        *,
        limit: int = 100,
        destination_id: str | None = None,
        content_id: str | None = None,
        status: str | None = None,
    ) -> list[dict[str, Any]]:
        clauses = ["1=1"]
        args: list[Any] = []
        if destination_id:
            clauses.append("destination_id=?")
            args.append(destination_id)
        if content_id:
            clauses.append("content_id=?")
            args.append(content_id)
        if status:
            clauses.append("status=?")
            args.append(status)
        args.append(min(max(limit, 1), 500))
        with self.connection() as con:
            rows = [dict(row) for row in con.execute(
                f"SELECT * FROM destination_receipt WHERE {' AND '.join(clauses)} ORDER BY finished_at DESC LIMIT ?",
                args,
            ).fetchall()]
        for row in rows:
            try:
                row["evidence"] = json.loads(row.pop("evidence_json") or "{}")
            except (TypeError, ValueError):
                row["evidence"] = {}
        return rows

    def get_destination_receipt(self, receipt_id: str) -> dict[str, Any] | None:
        with self.connection() as con:
            row = con.execute("SELECT * FROM destination_receipt WHERE id=?", (receipt_id,)).fetchone()
        if not row:
            return None
        result = dict(row)
        try:
            result["evidence"] = json.loads(result.pop("evidence_json") or "{}")
        except (TypeError, ValueError):
            result["evidence"] = {}
        return result

    def list_library(
        self,
        *,
        q: str | None = None,
        platform: str | None = None,
        relation: str | None = None,
        collection: str | None = None,
        observed_from: str | None = None,
        observed_to: str | None = None,
        limit: int = 100,
        offset: int = 0,
        user_id: str | None = None,
    ) -> list[dict[str, Any]]:
        clauses = ["1=1"]
        where_args: list[Any] = []
        if platform:
            clauses.append("c.platform=?")
            where_args.append(platform.lower())
        if q:
            literal_query = _literal_fts_query(q)
            cjk_terms = _cjk_substrings(q)
            if literal_query:
                clauses.append("c.id IN (SELECT content_id FROM content_fts WHERE content_fts MATCH ?)")
                where_args.append(literal_query)
            for term in cjk_terms:
                pattern = _like_pattern(term)
                clauses.append(
                    """c.id IN (SELECT content_id FROM content_fts
                       WHERE title LIKE ? ESCAPE '\\' OR author_name LIKE ? ESCAPE '\\'
                          OR body LIKE ? ESCAPE '\\' OR tags LIKE ? ESCAPE '\\')"""
                )
                where_args.extend([pattern, pattern, pattern, pattern])
            if not literal_query and not cjk_terms:
                clauses.append("0=1")
        relation_clauses: list[str] = []
        relation_args: list[Any] = []
        # 租户过滤必须建在这里，不能在外层 content 上：它决定"用哪条关系去 join"，
        # 于是别人的内容根本连不进结果集，而 LIMIT/OFFSET 语义仍然正确。
        # 放外层再过滤会让一页返回不足 limit 条，翻页就错了。
        if user_id:
            relation_clauses.append("r2.user_id=?")
            relation_args.append(user_id)
        if relation:
            relation_clauses.append("r2.relation_type=?")
            relation_args.append(relation)
        if collection:
            relation_clauses.append("r2.collection_key=?")
            relation_args.append(collection)
        if observed_from:
            relation_clauses.append("r2.last_observed_at>=?")
            relation_args.append(observed_from)
        if observed_to:
            relation_clauses.append("r2.last_observed_at<=?")
            relation_args.append(observed_to)
        relation_clause = "".join(f" AND {clause}" for clause in relation_clauses)
        args = relation_args + where_args + [min(max(limit, 1), 500), max(offset, 0)]
        sql = f"""SELECT c.*,r.relation_type,r.collection_key,r.status AS relation_status,
                 (SELECT COUNT(*) FROM artifact a WHERE a.content_id=c.id) artifact_count,
                 (SELECT COUNT(*) FROM object_replica o JOIN artifact a2 ON a2.id=o.artifact_id WHERE a2.content_id=c.id AND o.status='verified') verified_replica_count
                 FROM content c JOIN user_relation r ON r.id=(
                   SELECT r2.id FROM user_relation r2
                   WHERE r2.content_id=c.id{relation_clause}
                   ORDER BY CASE WHEN r2.status='active' THEN 0 ELSE 1 END, r2.last_observed_at DESC, r2.id ASC
                   LIMIT 1
                 )
                 WHERE {' AND '.join(clauses)} ORDER BY c.last_observed_at DESC LIMIT ? OFFSET ?"""
        with self.connection() as con:
            return [dict(row) for row in con.execute(sql, args).fetchall()]

    _TABLE_SORT_COLUMNS = {
        "time": "relation_time",
        "platform": "platform",
        "topic": "topic",
        "keywords": "keywords_json",
        "content": "title",
        "link": "canonical_url",
        "relation": "primary_relation",
        "author": "author_name",
        "collection": "primary_collection",
        "media": "media_count",
        "archive": "archive_status",
        "published": "published_at",
        "account": "account_name",
        "synced": "last_synced_at",
    }

    def list_library_table(
        self,
        *,
        q: str | None = None,
        platform: str | None = None,
        relation: str | None = None,
        topic: str | None = None,
        collection: str | None = None,
        archive_status: str | None = None,
        after: str | None = None,
        observed_from: str | None = None,
        observed_to: str | None = None,
        sort_by: str = "time",
        sort_dir: str = "desc",
        limit: int = 100,
        offset: int = 0,
        user_id: str | None = None,
    ) -> dict[str, Any]:
        clauses = ["r.status='active'"]
        args: list[Any] = []
        # 租户过滤加在关系表 r 上（这张表就是所有权边），facet 统计与分页共用同一组
        # clauses，所以计数和翻页会一起被收敛到本用户，不会出现"总数是全库、页是自己"的错位。
        if user_id:
            clauses.append("r.user_id=?")
            args.append(user_id)
        if platform:
            clauses.append("c.platform=?")
            args.append(platform.lower())
        if relation:
            clauses.append("r.relation_type=?")
            args.append(relation)
        if topic:
            clauses.append("COALESCE(cc.topic,'未分类')=?")
            args.append(topic)
        if collection:
            clauses.append("r.collection_key=?")
            args.append(collection)
        for boundary in (after, observed_from):
            if boundary:
                clauses.append("COALESCE(r.relation_observed_at,r.first_observed_at)>=?")
                args.append(boundary)
        if observed_to:
            clauses.append("COALESCE(r.relation_observed_at,r.first_observed_at)<=?")
            args.append(observed_to)
        if q:
            literal_query = _literal_fts_query(q)
            cjk_terms = _cjk_substrings(q)
            if literal_query:
                clauses.append("c.id IN (SELECT content_id FROM content_fts WHERE content_fts MATCH ?)")
                args.append(literal_query)
            for term in cjk_terms:
                pattern = _like_pattern(term)
                clauses.append(
                    """c.id IN (SELECT content_id FROM content_fts
                       WHERE title LIKE ? ESCAPE '\\' OR author_name LIKE ? ESCAPE '\\'
                          OR body LIKE ? ESCAPE '\\' OR tags LIKE ? ESCAPE '\\')"""
                )
                args.extend([pattern, pattern, pattern, pattern])
            if not literal_query and not cjk_terms:
                clauses.append("0=1")
        where = " AND ".join(clauses)
        direction = "ASC" if sort_dir.lower() == "asc" else "DESC"
        order_column = self._TABLE_SORT_COLUMNS.get(sort_by, "relation_time")
        safe_limit = min(max(limit, 1), 500)
        safe_offset = max(offset, 0)
        base = f"""WITH relation_rows AS (
            SELECT c.id,c.platform,c.external_content_id,c.canonical_url,c.title,c.author_name,c.published_at,
                   c.summary,c.language,c.media_count,c.last_synced_at,c.last_observed_at,
                   r.id AS relation_id,r.relation_type AS primary_relation,r.collection_key AS primary_collection,
                   COALESCE(r.relation_observed_at,r.first_observed_at) AS relation_time,
                   COALESCE(sa.display_name,sa.external_account_id,'') AS account_name,
                   COALESCE(cc.topic,'未分类') AS topic,COALESCE(cc.keywords_json,'[]') AS keywords_json,
                   COALESCE(cc.confidence,0) AS classification_confidence,COALESCE(cc.source,'local_rules') AS classification_source,
                   (SELECT COUNT(*) FROM artifact a WHERE a.content_id=c.id) AS artifact_count,
                   CASE
                     WHEN EXISTS(SELECT 1 FROM artifact a WHERE a.content_id=c.id AND a.status='complete') THEN '完整'
                     WHEN EXISTS(SELECT 1 FROM artifact a WHERE a.content_id=c.id AND a.status IN ('staged','ready')) THEN '处理中'
                     ELSE '仅元数据'
                   END AS archive_status,
                   (SELECT COUNT(*) FROM destination_receipt dr WHERE dr.content_id=c.id AND dr.status='done') AS export_done_count,
                   (SELECT GROUP_CONCAT(dr.destination_id) FROM destination_receipt dr WHERE dr.content_id=c.id AND dr.status='done') AS export_destination_ids,
                   ROW_NUMBER() OVER (PARTITION BY c.id ORDER BY COALESCE(r.relation_observed_at,r.first_observed_at) DESC,r.id) AS row_rank,
                   GROUP_CONCAT(r.relation_type) OVER (PARTITION BY c.id) AS relation_types,
                   GROUP_CONCAT(NULLIF(r.collection_key,'')) OVER (PARTITION BY c.id) AS collection_names
            FROM content c
            JOIN user_relation r ON r.content_id=c.id
            LEFT JOIN source_account sa ON sa.id=r.source_account_id
            LEFT JOIN content_classification cc ON cc.content_id=c.id
            WHERE {where}
        )
        SELECT * FROM relation_rows WHERE row_rank=1"""
        archive_clause = ""
        query_args = list(args)
        if archive_status:
            archive_clause = " AND archive_status=?"
            query_args.append(archive_status)
        count_sql = f"SELECT COUNT(*) AS total FROM ({base}) WHERE 1=1{archive_clause}"
        query_sql = f"SELECT * FROM ({base}) WHERE 1=1{archive_clause} ORDER BY {order_column} {direction}, id ASC LIMIT ? OFFSET ?"
        with self.connection() as con:
            total = int(con.execute(count_sql, query_args).fetchone()["total"])
            rows = [dict(row) for row in con.execute(query_sql, [*query_args, safe_limit, safe_offset]).fetchall()]
            platform_rows = con.execute(
                f"""SELECT c.platform,COUNT(DISTINCT c.id) AS count
                    FROM content c JOIN user_relation r ON r.content_id=c.id
                    LEFT JOIN content_classification cc ON cc.content_id=c.id
                    WHERE {where} GROUP BY c.platform ORDER BY count DESC""",
                args,
            ).fetchall()
            topic_rows = con.execute(
                f"""SELECT COALESCE(cc.topic,'未分类') AS topic,COUNT(DISTINCT c.id) AS count
                    FROM content c JOIN user_relation r ON r.content_id=c.id
                    LEFT JOIN content_classification cc ON cc.content_id=c.id
                    WHERE {where} GROUP BY COALESCE(cc.topic,'未分类') ORDER BY count DESC LIMIT 100""",
                args,
            ).fetchall()
        for row in rows:
            try:
                row["keywords"] = json.loads(row.pop("keywords_json") or "[]")
            except (TypeError, ValueError):
                row["keywords"] = []
            row["relations"] = list(dict.fromkeys(item for item in (row.pop("relation_types") or "").split(",") if item))
            row["collections"] = list(dict.fromkeys(item for item in (row.pop("collection_names") or "").split(",") if item))
            row["export_destinations"] = list(dict.fromkeys(item for item in (row.pop("export_destination_ids") or "").split(",") if item))
        return {
            "items": rows,
            "total": total,
            "limit": safe_limit,
            "offset": safe_offset,
            "sort_by": sort_by if sort_by in self._TABLE_SORT_COLUMNS else "time",
            "sort_dir": direction.lower(),
            "facets": {
                "platforms": [dict(row) for row in platform_rows],
                "topics": [dict(row) for row in topic_rows],
            },
        }

    def content_bodies(self, content_ids: list[str]) -> dict[str, str]:
        """Read export text from FTS without widening the library API payload."""
        identifiers = list(dict.fromkeys(str(content_id) for content_id in content_ids if content_id))
        result: dict[str, str] = {}
        with self.connection() as con:
            for start in range(0, len(identifiers), 500):
                batch = identifiers[start : start + 500]
                if not batch:
                    continue
                placeholders = ",".join("?" for _ in batch)
                rows = con.execute(
                    f"SELECT content_id,body FROM content_fts WHERE content_id IN ({placeholders})",
                    batch,
                ).fetchall()
                result.update({str(row["content_id"]): str(row["body"] or "") for row in rows})
        return result

    def get_content(self, content_id: str) -> dict[str, Any] | None:
        with self.connection() as con:
            content = con.execute("SELECT * FROM content WHERE id=?", (content_id,)).fetchone()
            if not content:
                return None
            result = dict(content)
            body = con.execute(
                "SELECT body FROM content_fts WHERE content_id=?",
                (content_id,),
            ).fetchone()
            result["body"] = str(body["body"] or "") if body else ""
            result["relations"] = [dict(r) for r in con.execute(
                """SELECT * FROM user_relation WHERE content_id=?
                   ORDER BY last_observed_at DESC, first_observed_at DESC, id ASC""",
                (content_id,),
            ).fetchall()]
            result["artifacts"] = [dict(a) for a in con.execute("SELECT * FROM artifact WHERE content_id=?", (content_id,)).fetchall()]
            bindings = [dict(row) for row in con.execute(
                "SELECT * FROM destination_binding WHERE content_id=? ORDER BY destination_id", (content_id,)
            ).fetchall()]
            for binding in bindings:
                try:
                    binding["metadata"] = json.loads(binding.pop("metadata_json") or "{}")
                except (TypeError, ValueError):
                    binding["metadata"] = {}
            receipts = [dict(row) for row in con.execute(
                "SELECT * FROM destination_receipt WHERE content_id=? ORDER BY finished_at DESC LIMIT 100", (content_id,)
            ).fetchall()]
            for receipt in receipts:
                try:
                    receipt["evidence"] = json.loads(receipt.pop("evidence_json") or "{}")
                except (TypeError, ValueError):
                    receipt["evidence"] = {}
            result["destination_bindings"] = bindings
            result["export_receipts"] = receipts
            result["object_replicas"] = [dict(row) for row in con.execute(
                """SELECT r.* FROM object_replica r
                   JOIN artifact a ON a.id=r.artifact_id
                   WHERE a.content_id=?
                   ORDER BY a.created_at ASC,a.id ASC,r.store_id ASC""",
                (content_id,),
            ).fetchall()]
            return result

    def list_completed_content_bundles(self, *, limit: int = 100) -> list[dict[str, Any]]:
        """Return only content whose every archived artifact has all three receipts.

        ``artifact.status='complete'`` is set exclusively by the shared replica
        completion gate, so this method cannot elevate a partially replicated
        capture into a durable business fact.
        """
        with self.connection() as con:
            rows = con.execute(
                """SELECT c.id
                   FROM content c
                   JOIN artifact a ON a.content_id=c.id
                   GROUP BY c.id
                   HAVING COUNT(a.id)>0
                      AND SUM(CASE WHEN a.status='complete' THEN 0 ELSE 1 END)=0
                   ORDER BY MAX(c.last_observed_at) ASC,c.id ASC
                   LIMIT ?""",
                (min(max(limit, 1), 1000),),
            ).fetchall()
        return [bundle for row in rows if (bundle := self.get_content(str(row["id"]))) is not None]

    def get_outbox_event(
        self,
        *,
        event_type: str,
        aggregate_id: str,
        payload_sha256: str,
    ) -> dict[str, Any] | None:
        with self.connection() as con:
            row = con.execute(
                """SELECT * FROM outbox
                   WHERE event_type=? AND aggregate_id=? AND payload_sha256=?""",
                (event_type, aggregate_id, payload_sha256),
            ).fetchone()
        if not row:
            return None
        result = dict(row)
        result["payload"] = json.loads(str(result.pop("payload_json")))
        return result

    def ensure_outbox_event(self, *, event_type: str, aggregate_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        """Create one content-addressed durable-delivery event without replacing history."""
        payload_raw = json_bytes(payload).decode("utf-8")
        payload_sha256 = sha256_bytes(payload_raw.encode("utf-8"))
        event_id = stable_id("outbox", event_type, aggregate_id, payload_sha256)
        now = utcnow()
        with self.connection() as con:
            con.execute(
                """INSERT OR IGNORE INTO outbox(
                     id,event_type,aggregate_id,payload_json,payload_sha256,status,attempt_count,not_before,created_at
                   ) VALUES(?,?,?,?,?,'pending',0,?,?)""",
                (event_id, event_type, aggregate_id, payload_raw, payload_sha256, now, now),
            )
        event = self.get_outbox_event(
            event_type=event_type,
            aggregate_id=aggregate_id,
            payload_sha256=payload_sha256,
        )
        if event is None:  # pragma: no cover - SQLite insert/read failure boundary
            raise RuntimeError("Outbox 事件写入后不可读取")
        return event

    def mark_outbox_delivered(self, event_id: str) -> None:
        with self.connection() as con:
            con.execute(
                """UPDATE outbox
                   SET status='delivered',attempt_count=attempt_count+1,delivered_at=?,last_error_code=NULL
                   WHERE id=?""",
                (utcnow(), event_id),
            )

    def mark_outbox_failed(self, event_id: str, error_code: str) -> None:
        with self.connection() as con:
            con.execute(
                """UPDATE outbox
                   SET status='pending',attempt_count=attempt_count+1,last_error_code=?
                   WHERE id=?""",
                (error_code[:160], event_id),
            )

    def upsert_connector_state(
        self,
        connector_id: str,
        *,
        state: str,
        policy_gate: str,
        auth_gate: str,
        technical_gate: str,
        error_code: str | None = None,
        last_checked_at: str | None = None,
        latency_ms: int | None = None,
        message_zh: str | None = None,
    ) -> None:
        now = utcnow()
        success_at = now if state == "healthy" else None
        failure_at = now if state in {"degraded", "blocked_environment", "paused", "disabled"} else None
        with self.connection() as con:
            con.execute(
                """INSERT INTO connector_state(
                     connector_id,state,policy_gate,auth_gate,technical_gate,last_success_at,last_failure_at,
                     last_error_code,last_checked_at,latency_ms,last_message_zh,updated_at
                   ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?)
                   ON CONFLICT(connector_id) DO UPDATE SET
                     state=excluded.state,policy_gate=excluded.policy_gate,auth_gate=excluded.auth_gate,
                     technical_gate=excluded.technical_gate,
                     last_success_at=COALESCE(excluded.last_success_at,connector_state.last_success_at),
                     last_failure_at=COALESCE(excluded.last_failure_at,connector_state.last_failure_at),
                     last_error_code=excluded.last_error_code,last_checked_at=excluded.last_checked_at,
                     latency_ms=excluded.latency_ms,last_message_zh=excluded.last_message_zh,updated_at=excluded.updated_at""",
                (
                    connector_id,
                    state,
                    policy_gate,
                    auth_gate,
                    technical_gate,
                    success_at,
                    failure_at,
                    error_code,
                    last_checked_at or now,
                    latency_ms,
                    message_zh,
                    now,
                ),
            )

    def connector_states(self) -> list[dict[str, Any]]:
        with self.connection() as con:
            return [dict(row) for row in con.execute("SELECT * FROM connector_state ORDER BY connector_id").fetchall()]

    def quota_states(self) -> list[dict[str, Any]]:
        with self.connection() as con:
            return [dict(row) for row in con.execute("SELECT * FROM quota_state ORDER BY store_id").fetchall()]

    def set_quota_state(self, store_id: str, measured: int, soft: int, hard: int, action: str) -> None:
        with self.connection() as con:
            con.execute(
                """INSERT INTO quota_state(store_id,measured_bytes,soft_limit_bytes,hard_limit_bytes,action,measured_at)
                   VALUES(?,?,?,?,?,?) ON CONFLICT(store_id) DO UPDATE SET measured_bytes=excluded.measured_bytes,soft_limit_bytes=excluded.soft_limit_bytes,hard_limit_bytes=excluded.hard_limit_bytes,action=excluded.action,measured_at=excluded.measured_at""",
                (store_id, measured, soft, hard, action, utcnow()),
            )


    def record_scan_receipt(
        self,
        connector_id: str,
        run_id: str,
        receipt: dict[str, Any],
        *,
        source_account_id: str | None,
        relation_type: str,
    ) -> str:
        """Persist every scan attempt, including partial, failed and blocked runs."""
        now = utcnow()
        account_id = stable_id("acct", connector_id.strip().lower(), source_account_id) if source_account_id else None
        raw = json.dumps(receipt, ensure_ascii=False, sort_keys=True)
        receipt_id = stable_id("scan", connector_id, run_id)
        completeness = str(receipt.get("completeness") or "unknown")
        if completeness not in {"complete", "partial", "failed", "unknown"}:
            completeness = "unknown"
        item_count = max(0, int(receipt.get("item_count") or 0))
        cursor_start = receipt.get("cursor_start")
        cursor_end = receipt.get("cursor_end") or receipt.get("next_token") or receipt.get("next_cursor")
        failure_code = receipt.get("failure_code")
        with self.connection() as con:
            if source_account_id:
                con.execute(
                    """INSERT INTO source_account(id,user_id,platform,external_account_id,created_at,updated_at)
                       VALUES(?,?,?,?,?,?)
                       ON CONFLICT(id) DO UPDATE SET platform=excluded.platform,external_account_id=excluded.external_account_id,updated_at=excluded.updated_at""",
                    (account_id, self._ensure_owner_user(con, now), connector_id.strip().lower(), source_account_id, now, now),
                )
            con.execute(
                """INSERT INTO scan_receipt(id,connector_id,source_account_id,relation_type,started_at,completed_at,completeness,item_count,cursor_start,cursor_end,failure_code,evidence_sha256)
                   VALUES(?,?,?,?,?,?,?,?,?,?,?,?)
                   ON CONFLICT(id) DO UPDATE SET completed_at=excluded.completed_at,completeness=excluded.completeness,item_count=excluded.item_count,cursor_end=excluded.cursor_end,failure_code=excluded.failure_code,evidence_sha256=excluded.evidence_sha256""",
                (
                    receipt_id,
                    connector_id,
                    account_id,
                    relation_type,
                    str(receipt.get("started_at") or now),
                    now,
                    completeness,
                    item_count,
                    str(cursor_start) if cursor_start is not None else None,
                    str(cursor_end) if cursor_end is not None else None,
                    str(failure_code) if failure_code else None,
                    sha256_bytes(raw.encode("utf-8")),
                ),
            )
        return receipt_id

    def apply_complete_scan(
        self,
        connector_id: str,
        observed_relation_ids: set[str],
        *,
        relation_type: str,
        collection_key: str = "",
        source_account_id: str | None = None,
    ) -> int:
        """Close only the exact scanned relation scope after two complete absences."""
        changed = 0
        platform = connector_id.strip().lower()
        account_scope = stable_id("acct", platform, source_account_id) if source_account_id else ""
        with self.connection() as con:
            con.execute("BEGIN IMMEDIATE")
            rows = con.execute(
                """SELECT r.id,r.missing_complete_scan_count
                   FROM user_relation r
                   JOIN content c ON c.id=r.content_id
                   WHERE r.status='active'
                     AND c.platform=?
                     AND r.relation_type=?
                     AND r.collection_key=?
                     AND COALESCE(r.source_account_id,'')=?""",
                (platform, relation_type, collection_key, account_scope),
            ).fetchall()
            now = utcnow()
            for row in rows:
                if row["id"] in observed_relation_ids:
                    con.execute(
                        "UPDATE user_relation SET missing_complete_scan_count=0,last_observed_at=? WHERE id=?",
                        (now, row["id"]),
                    )
                    continue
                count = int(row["missing_complete_scan_count"]) + 1
                if count >= 2:
                    con.execute(
                        "UPDATE user_relation SET missing_complete_scan_count=?,status='closed',closed_at=? WHERE id=?",
                        (count, now, row["id"]),
                    )
                else:
                    con.execute(
                        "UPDATE user_relation SET missing_complete_scan_count=? WHERE id=?",
                        (count, row["id"]),
                    )
                changed += 1
            con.execute("COMMIT")
        return changed

    # Account-mirror state belongs to the rebuildable runtime journal.  The
    # methods below intentionally expose opaque handle references only to the
    # coordinator, never to public account-list responses.
    def upsert_source_account(
        self,
        *,
        platform: str,
        external_account_id: str,
        display_name: str | None,
        auth_method: str,
        auth_handle_ref: str | None,
        connection_state: str,
        auto_sync_enabled: bool = True,
        sync_interval_minutes: int = 360,
        metadata: dict[str, Any] | None = None,
    ) -> str:
        now = utcnow()
        normalized_platform = platform.strip().lower()
        account_id = stable_id("acct", normalized_platform, external_account_id)
        with self.connection() as con:
            con.execute(
                """INSERT INTO source_account(
                       id,user_id,platform,external_account_id,display_name,auth_ref,
                       connection_state,auth_method,auth_handle_ref,auto_sync_enabled,
                       sync_interval_minutes,last_verified_at,metadata_json,created_at,updated_at
                   ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
                   ON CONFLICT(id) DO UPDATE SET
                     platform=excluded.platform,
                     external_account_id=excluded.external_account_id,
                     display_name=COALESCE(excluded.display_name,source_account.display_name),
                     auth_method=excluded.auth_method,
                     auth_handle_ref=COALESCE(excluded.auth_handle_ref,source_account.auth_handle_ref),
                     connection_state=excluded.connection_state,
                     auto_sync_enabled=excluded.auto_sync_enabled,
                     sync_interval_minutes=excluded.sync_interval_minutes,
                     last_verified_at=CASE WHEN excluded.connection_state='connected' THEN excluded.last_verified_at ELSE source_account.last_verified_at END,
                     metadata_json=excluded.metadata_json,
                     updated_at=excluded.updated_at""",
                (
                    account_id,
                    self._ensure_owner_user(con, now),
                    normalized_platform,
                    external_account_id,
                    display_name,
                    None,
                    connection_state,
                    auth_method,
                    auth_handle_ref,
                    1 if auto_sync_enabled else 0,
                    sync_interval_minutes,
                    now if connection_state == "connected" else None,
                    json.dumps(metadata or {}, ensure_ascii=False, sort_keys=True),
                    now,
                    now,
                ),
            )
        return account_id

    @staticmethod
    def _decode_json_field(row: dict[str, Any], field: str, fallback: Any) -> None:
        try:
            row[field.removesuffix("_json")] = json.loads(row.pop(field) or fallback)
        except (TypeError, ValueError):
            row[field.removesuffix("_json")] = json.loads(fallback)

    def list_source_accounts(self) -> list[dict[str, Any]]:
        with self.connection() as con:
            rows = con.execute(
                """SELECT sa.*,
                          (SELECT COUNT(DISTINCT r.content_id)
                           FROM user_relation r
                           WHERE r.source_account_id=sa.id AND r.status='active') AS content_count,
                          (SELECT COUNT(*) FROM platform_collection pc
                           WHERE pc.source_account_id=sa.id AND pc.status='active') AS collection_count,
                          (SELECT id FROM sync_run sr WHERE sr.source_account_id=sa.id
                           ORDER BY sr.updated_at DESC LIMIT 1) AS latest_sync_run_id,
                          (SELECT status FROM sync_run sr WHERE sr.source_account_id=sa.id
                           ORDER BY sr.updated_at DESC LIMIT 1) AS latest_sync_status
                   FROM source_account sa
                   ORDER BY sa.platform,COALESCE(sa.display_name,sa.external_account_id),sa.id"""
            ).fetchall()
        result: list[dict[str, Any]] = []
        for row in rows:
            item = dict(row)
            self._decode_json_field(item, "metadata_json", "{}")
            item["auto_sync_enabled"] = bool(item.get("auto_sync_enabled"))
            item.pop("auth_ref", None)
            item.pop("auth_handle_ref", None)
            result.append(item)
        return result

    def get_source_account(self, account_id: str, *, include_handle: bool = False) -> dict[str, Any] | None:
        with self.connection() as con:
            row = con.execute("SELECT * FROM source_account WHERE id=?", (account_id,)).fetchone()
        if not row:
            return None
        item = dict(row)
        self._decode_json_field(item, "metadata_json", "{}")
        item["auto_sync_enabled"] = bool(item.get("auto_sync_enabled"))
        if not include_handle:
            item.pop("auth_ref", None)
            item.pop("auth_handle_ref", None)
        return item

    def set_source_account_state(
        self,
        account_id: str,
        state: str,
        *,
        error_code: str | None = None,
        verified: bool = False,
    ) -> bool:
        now = utcnow()
        with self.connection() as con:
            cur = con.execute(
                """UPDATE source_account
                   SET connection_state=?,last_error_code=?,updated_at=?,
                       last_verified_at=CASE WHEN ? THEN ? ELSE last_verified_at END
                   WHERE id=?""",
                (state, error_code, now, 1 if verified else 0, now, account_id),
            )
        return cur.rowcount == 1

    def disconnect_source_account(self, account_id: str) -> dict[str, Any]:
        """断开一个已连接的账号（v0.0.0.7 / INV-REVERSIBLE）。

        ## 为什么需要它

        清点不变量守卫时发现 INV-REVERSIBLE 只有一个（回滚脚本）。顺着把路由表
        按「加了什么就要能撤什么」比一遍，缺口很直接：

            POST /extension-token           ↔  DELETE /extension-token        ✓
            PUT  /v1/credentials/{platform} ↔  DELETE /v1/credentials/{…}     ✓
            登录                             ↔  登出                           ✓
            **POST /v1/accounts/connect/…   ↔  （没有）**

        连一个账号一次点击，断开做不到。而连上之后它每 6 小时自己跑一次
        （auto_sync_enabled + sync_interval_minutes 默认 360），
        **用户没有任何办法让它停下来。**

        ## 只断连接，不删内容

        归档的意义就是东西留下来。断开做四件事，一件都不多：

          1. connection_state → disconnected，auto_sync_enabled → 0（不再自己跑）
          2. 清掉 auth_ref / auth_handle_ref（不再持有连接凭证的引用）
          3. 把还在跑的 sync_run 落到 cancelled（否则界面上永远转圈）
          4. 如实报出**保留了多少条内容**——用户要知道断开不等于清空

        平台凭据（Cookie 托管）的撤销是**另一件事**，走
        DELETE /v1/credentials/{platform}，由调用方按用户意愿分别决定。
        两件事合并会让「我只是不想它再自动跑了」变成「我的登录状态也没了」。
        """
        now = utcnow()
        with self.connection() as con:
            row = con.execute(
                "SELECT platform,connection_state FROM source_account WHERE id=?", (account_id,)
            ).fetchone()
            if row is None:
                return {"found": False}
            already = str(row["connection_state"]) == "disconnected"
            con.execute(
                """UPDATE source_account
                   SET connection_state='disconnected', auto_sync_enabled=0,
                       auth_ref=NULL, auth_handle_ref=NULL, last_error_code=NULL, updated_at=?
                   WHERE id=?""",
                (now, account_id),
            )
            cancelled = con.execute(
                """UPDATE sync_run SET status='cancelled', updated_at=?,
                          last_error_code='ACCOUNT_DISCONNECTED',
                          last_error_message='账号已断开连接，这次同步已停止。'
                   WHERE source_account_id=?
                     AND status NOT IN ('completed','partial','cancelled','failed','blocked_environment')""",
                (now, account_id),
            ).rowcount
            kept = int(con.execute(
                "SELECT COUNT(DISTINCT content_id) FROM user_relation "
                "WHERE source_account_id=? AND status='active'", (account_id,)
            ).fetchone()[0])
        return {
            "found": True,
            "platform": str(row["platform"]),
            "already_disconnected": already,
            "cancelled_runs": int(cancelled),
            "kept_content_count": kept,
        }

    def upsert_platform_collection(
        self,
        *,
        source_account_id: str,
        relation_type: str,
        name: str,
        external_collection_id: str | None = None,
        item_count: int | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> str:
        now = utcnow()
        external = external_collection_id or name
        collection_id = stable_id("col", source_account_id, relation_type, external)
        with self.connection() as con:
            con.execute(
                # user_id 继承自所属 source_account——收藏夹属于谁，取决于账号属于谁，
                # 不是取决于"当前是谁在跑"。用子查询而不是传参，写入路径就没有传错的机会。
                """INSERT INTO platform_collection(
                       id,user_id,source_account_id,external_collection_id,relation_type,name,item_count,
                       status,first_observed_at,last_observed_at,metadata_json
                   ) VALUES(?,(SELECT user_id FROM source_account WHERE id=?),?,?,?,?,?,'active',?,?,?)
                   ON CONFLICT(id) DO UPDATE SET
                     name=excluded.name,
                     item_count=COALESCE(excluded.item_count,platform_collection.item_count),
                     status='active',last_observed_at=excluded.last_observed_at,
                     metadata_json=excluded.metadata_json""",
                (
                    collection_id,
                    source_account_id,  # 供上面的 user_id 子查询使用
                    source_account_id,
                    external_collection_id,
                    relation_type,
                    name,
                    item_count,
                    now,
                    now,
                    json.dumps(metadata or {}, ensure_ascii=False, sort_keys=True),
                ),
            )
        return collection_id

    def create_sync_run(
        self,
        *,
        source_account_id: str,
        platform: str,
        mode: str,
        relation_types: list[str],
        trigger_type: str,
    ) -> str:
        now = utcnow()
        run_id = stable_id("sync", source_account_id, mode, trigger_type, now)
        normalized_relations = list(dict.fromkeys(relation_types))
        with self.connection() as con:
            con.execute(
                # 同上：同步运行归属于账号的主人。
                """INSERT INTO sync_run(
                       id,user_id,source_account_id,platform,mode,trigger_type,status,relation_scope_json,updated_at
                   ) VALUES(?,(SELECT user_id FROM source_account WHERE id=?),?,?,?,?,'queued',?,?)""",
                (
                    run_id,
                    source_account_id,  # 供上面的 user_id 子查询使用
                    source_account_id,
                    platform.strip().lower(),
                    mode,
                    trigger_type,
                    json.dumps(normalized_relations, ensure_ascii=False),
                    now,
                ),
            )
            for relation_type in normalized_relations:
                con.execute(
                    """INSERT OR IGNORE INTO sync_run_scope(
                           sync_run_id,relation_type,collection_key,status,completeness,updated_at
                       ) VALUES(?,?,?,'pending','unknown',?)""",
                    (run_id, relation_type, "__relation__", now),
                )
        self.append_sync_event(run_id, "queued", {"mode": mode, "relations": normalized_relations})
        return run_id

    def append_sync_event(self, sync_run_id: str, event_type: str, payload: dict[str, Any] | None = None) -> str:
        with self.connection() as con:
            row = con.execute(
                "SELECT COALESCE(MAX(sequence_no),0)+1 AS next_no FROM sync_run_event WHERE sync_run_id=?",
                (sync_run_id,),
            ).fetchone()
            sequence_no = int(row["next_no"])
            event_id = stable_id("sync_event", sync_run_id, sequence_no, event_type)
            con.execute(
                """INSERT INTO sync_run_event(id,sync_run_id,event_type,sequence_no,payload_json,created_at)
                   VALUES(?,?,?,?,?,?)""",
                (event_id, sync_run_id, event_type, sequence_no, json.dumps(payload or {}, ensure_ascii=False, sort_keys=True), utcnow()),
            )
        return event_id

    def provenance_audit(self) -> dict[str, int | list[str]]:
        """INV-TRUTH-TRACEABLE 的库层落点：**每条内容都答得出「怎么进来的」。**

        这条不变量此前**一个判据都没有**——清点各不变量的守卫时发现
        TRUTH-TRACEABLE / REAL-USABLE / HONEST-EVIDENCE 三条只活在文档里。

        溯源断掉的样子不是报错，是「库里有一条东西，没人说得清它从哪来」。
        那和静默的零是同一种病的另一面：**数据在，出处没了。**

        实测生产（2026-08-04）：193 条内容 193 条有观察记录，0 条孤儿制品。
        也就是说这条不变量当时是成立的——但没有任何东西在盯着它。

        每一项都是**必须为 0**。非 0 不代表数据错，代表**溯源链断了**。
        """
        checks = {
            # 内容进来时必定伴随一条 observation（capture 路径写的）
            "content_without_observation":
                "SELECT COUNT(*) FROM content WHERE id NOT IN (SELECT content_id FROM observation)",
            # 制品必须挂在某条内容上
            "artifact_without_content":
                "SELECT COUNT(*) FROM artifact WHERE content_id NOT IN (SELECT id FROM content)",
            # 关系（谁收藏了什么）必须指得到内容
            "relation_without_content":
                "SELECT COUNT(*) FROM user_relation WHERE content_id NOT IN (SELECT id FROM content)",
            # 观察记录反过来也不能指向不存在的内容
            "observation_without_content":
                "SELECT COUNT(*) FROM observation WHERE content_id NOT IN (SELECT id FROM content)",
        }
        out: dict[str, int | list[str]] = {}
        with self.connection() as con:
            for name, sql in checks.items():
                out[name] = int(con.execute(sql).fetchone()[0])
            out["content_total"] = int(con.execute("SELECT COUNT(*) FROM content").fetchone()[0])
        out["broken"] = sorted(k for k, v in out.items() if k in checks and int(v) > 0)
        return out

    def privacy_facts(self) -> dict[str, Any]:
        """把「隐私边界」从一句自称改成一次测量（v0.0.0.7）。

        `/v1/extension/bootstrap` 此前回的是三个写死的字面量：

            "cookie_custody": False, "password_custody": False,
            "user_triggered_capture_only": True

        其中 `cookie_custody: False` 从 T05/T06 起就是**假的**——产品确实在
        托管西方三源的登录状态（加密后落库）。一个自称是隐私边界的字段说了假话，
        比没有这个字段更糟：读它的人会据此以为不存在这件事。

        而且它被一条判据逐字钉住（test_extension_api 断言整个字典），
        **错的事实由绿灯守着**，是本轮遇到过最糟的形状。

        所以这里全部改成算出来的：
          · 密码：扫 sqlite_master 里有没有 password 形状的列。**不是"我们不存"，
            是"库里现在没有这种列"**——能出示的出示，只能自述的别写成事实。
          · 自动同步：数有多少个账号开着定时同步。这直接反驳了
            "user_triggered_capture_only"——连接过的账号会按周期自己跑。
        """
        password_shaped = re.compile(r"(?i)\b(password|passwd|pwd)\b")
        columns: list[str] = []
        auto_sync = 0
        with self.connection() as con:
            for row in con.execute(
                "SELECT name, sql FROM sqlite_master WHERE type='table' AND sql IS NOT NULL"
            ):
                for line in str(row["sql"]).splitlines():
                    field = line.strip().split(" ", 1)[0].strip(",()\"'`")
                    if field and password_shaped.fullmatch(field):
                        columns.append(f"{row['name']}.{field}")
            try:
                auto_sync = int(con.execute(
                    "SELECT COUNT(*) FROM source_account "
                    "WHERE auto_sync_enabled=1 AND connection_state IN ('connected','degraded')"
                ).fetchone()[0])
            except sqlite3.Error:
                auto_sync = 0
        return {"password_shaped_columns": sorted(columns), "auto_sync_accounts": auto_sync}

    def owner_user_for_content(self, content_id: str) -> str | None:
        """这条内容是谁的。用于取用他自己托管的平台会话。

        走 user_relation 而不是 content：**所有权边在关系上，不在内容上**
        （同一条内容可以被不同的人各自收藏，内容本身没有主人）。
        这一点在 TENANT_TABLES 的注释里已经写明。
        """
        with self.connection() as con:
            row = con.execute(
                "SELECT user_id FROM user_relation WHERE content_id=? AND user_id IS NOT NULL "
                "ORDER BY first_observed_at LIMIT 1",
                (str(content_id),),
            ).fetchone()
        return str(row["user_id"]) if row and row["user_id"] else None

    def stalled_active_runs(
        self, *, stale_after_seconds: int = 1800, limit: int = 200
    ) -> list[dict[str, object]]:
        """卡在非终态不动的同步运行（v0.0.0.7 / T04）。

        `unexplained_zero_runs` 只看**终态**（partial/failed/blocked_environment）。
        但真正让用户看到「点了同步永远在转」的，恰恰是**永远到不了终态**的运行
        ——它不在那三种状态里，所以那个审计一条都抓不到。

        实测抓到过两种成因，都不是设想出来的：

          1. 同步范围里混进了枚举不出来的关系类型（manual_save），
             那一路永远等不到终批，run 永远停在 scanning。
          2. MV3 的 service worker 被杀在半路，队列条目已被摘走，
             没有任何东西会再推进它，run 永远停在 queued。

        两条都修了，这个审计是**兜底**：将来再冒出第三种成因，
        它至少能被看见，而不是又变成一次没人说得清的转圈。
        """
        cutoff = int(max(0, stale_after_seconds))
        with self.connection() as con:
            rows = con.execute(
                """SELECT id,platform,status,imported_count,updated_at,started_at
                     FROM sync_run
                    WHERE status NOT IN
                          ('completed','partial','failed','cancelled','blocked_environment')
                      AND updated_at IS NOT NULL
                      AND CAST((julianday('now') - julianday(updated_at)) * 86400 AS INTEGER) > ?
                    ORDER BY updated_at ASC LIMIT ?""",
                (cutoff, int(limit)),
            ).fetchall()
        return [dict(row) for row in rows]

    def unexplained_zero_runs(self, *, limit: int = 200) -> list[dict[str, object]]:
        """INV-NO-SILENT-ZERO 的库层审计（v0.0.0.7 / T14）。

        找出「已经跑到终态、一条都没进来、却没有任何失败码」的同步运行。
        这正是 v0.0.0.6 那种静默的零：界面显示成功、表格是空的、
        没有任何地方说得出为什么。

        `completed` 且 imported=0 **不算**——那是「已经是最新的，没有新增」，
        是好事，且界面上会显示成另一句话。只有 partial / failed /
        blocked_environment 这些非成功终态才要求必须给出原因。
        """
        with self.connection() as con:
            rows = con.execute(
                """SELECT id,platform,status,imported_count,completeness,last_error_code
                     FROM sync_run
                    WHERE status IN ('partial','failed','blocked_environment')
                      AND imported_count = 0
                      AND (last_error_code IS NULL OR TRIM(last_error_code) = '')
                    ORDER BY updated_at DESC LIMIT ?""",
                (int(limit),),
            ).fetchall()
        return [dict(row) for row in rows]

    def update_sync_run(
        self,
        sync_run_id: str,
        *,
        status: str | None = None,
        completeness: str | None = None,
        discovered_delta: int = 0,
        imported_delta: int = 0,
        duplicate_delta: int = 0,
        failed_delta: int = 0,
        unavailable_delta: int = 0,
        cursor: dict[str, Any] | None = None,
        resume_token: str | None = None,
        error_code: str | None = None,
        error_message: str | None = None,
        evidence: dict[str, Any] | None = None,
    ) -> bool:
        now = utcnow()
        completed = status in {"completed", "partial", "cancelled", "failed", "blocked_environment"}
        with self.connection() as con:
            cur = con.execute(
                """UPDATE sync_run SET
                     status=COALESCE(?,status),
                     completeness=COALESCE(?,completeness),
                     discovered_count=discovered_count+?,
                     imported_count=imported_count+?,
                     duplicate_count=duplicate_count+?,
                     failed_count=failed_count+?,
                     unavailable_count=unavailable_count+?,
                     cursor_json=CASE WHEN ? IS NULL THEN cursor_json ELSE ? END,
                     resume_token=COALESCE(?,resume_token),
                     last_error_code=?,last_error_message=?,
                     evidence_json=CASE WHEN ? IS NULL THEN evidence_json ELSE ? END,
                     started_at=CASE WHEN started_at IS NULL AND COALESCE(?,status) NOT IN ('queued','paused') THEN ? ELSE started_at END,
                     completed_at=CASE WHEN ? THEN ? ELSE completed_at END,
                     updated_at=?
                   WHERE id=?""",
                (
                    status,
                    completeness,
                    discovered_delta,
                    imported_delta,
                    duplicate_delta,
                    failed_delta,
                    unavailable_delta,
                    None if cursor is None else 1,
                    json.dumps(cursor or {}, ensure_ascii=False, sort_keys=True),
                    resume_token,
                    error_code,
                    error_message,
                    None if evidence is None else 1,
                    json.dumps(evidence or {}, ensure_ascii=False, sort_keys=True),
                    status,
                    now,
                    1 if completed else 0,
                    now,
                    now,
                    sync_run_id,
                ),
            )
        if cur.rowcount and status:
            self.append_sync_event(sync_run_id, status, {"error_code": error_code, "message": error_message})
        return cur.rowcount == 1

    def _decode_sync_run(self, row: sqlite3.Row) -> dict[str, Any]:
        item = dict(row)
        self._decode_json_field(item, "relation_scope_json", "[]")
        self._decode_json_field(item, "cursor_json", "{}")
        self._decode_json_field(item, "evidence_json", "{}")
        return item

    def get_sync_run(self, sync_run_id: str) -> dict[str, Any] | None:
        with self.connection() as con:
            row = con.execute("SELECT * FROM sync_run WHERE id=?", (sync_run_id,)).fetchone()
            events = con.execute(
                "SELECT * FROM sync_run_event WHERE sync_run_id=? ORDER BY sequence_no",
                (sync_run_id,),
            ).fetchall() if row else []
        if not row:
            return None
        result = self._decode_sync_run(row)
        result["events"] = []
        for event in events:
            item = dict(event)
            self._decode_json_field(item, "payload_json", "{}")
            result["events"].append(item)
        return result

    def list_sync_runs(self, *, source_account_id: str | None = None, limit: int = 100) -> list[dict[str, Any]]:
        sql = "SELECT * FROM sync_run"
        args: list[Any] = []
        if source_account_id:
            sql += " WHERE source_account_id=?"
            args.append(source_account_id)
        sql += " ORDER BY updated_at DESC,id DESC LIMIT ?"
        args.append(min(max(limit, 1), 500))
        with self.connection() as con:
            rows = con.execute(sql, args).fetchall()
        return [self._decode_sync_run(row) for row in rows]

    def control_sync_run(self, sync_run_id: str, action: str) -> bool:
        run = self.get_sync_run(sync_run_id)
        if not run:
            return False
        transitions = {
            "pause": ({"queued", "authorizing", "discovering", "scanning", "normalizing", "artifacting", "exporting"}, "paused"),
            "resume": ({"paused", "partial", "failed", "blocked_environment"}, "queued"),
            "cancel": ({"queued", "authorizing", "discovering", "scanning", "normalizing", "artifacting", "exporting", "paused"}, "cancelled"),
            "retry": ({"partial", "failed", "blocked_environment"}, "queued"),
        }
        allowed, target = transitions.get(action, (set(), ""))
        if run["status"] not in allowed:
            return False
        return self.update_sync_run(sync_run_id, status=target, error_code=None, error_message=None)

    def record_sync_seen_relations(
        self,
        *,
        sync_run_id: str,
        relation_type: str,
        relation_ids_by_collection: dict[str, set[str]],
    ) -> int:
        now = utcnow()
        inserted = 0
        with self.connection() as con:
            con.execute("BEGIN IMMEDIATE")
            for collection_key, relation_ids in relation_ids_by_collection.items():
                for relation_id in relation_ids:
                    cur = con.execute(
                        """INSERT OR IGNORE INTO sync_seen_relation(
                               sync_run_id,relation_type,collection_key,relation_id,observed_at
                           ) VALUES(?,?,?,?,?)""",
                        (sync_run_id, relation_type, collection_key or "", relation_id, now),
                    )
                    inserted += max(cur.rowcount, 0)
            con.execute("COMMIT")
        return inserted

    def list_sync_seen_relation_ids(
        self,
        *,
        sync_run_id: str,
        relation_type: str,
        collection_key: str | None = None,
    ) -> set[str]:
        sql = "SELECT relation_id FROM sync_seen_relation WHERE sync_run_id=? AND relation_type=?"
        args: list[Any] = [sync_run_id, relation_type]
        if collection_key is not None:
            sql += " AND collection_key=?"
            args.append(collection_key)
        with self.connection() as con:
            return {str(row["relation_id"]) for row in con.execute(sql, args).fetchall()}

    def list_sync_seen_collections(self, *, sync_run_id: str, relation_type: str) -> set[str]:
        with self.connection() as con:
            rows = con.execute(
                """SELECT DISTINCT collection_key FROM sync_seen_relation
                   WHERE sync_run_id=? AND relation_type=?""",
                (sync_run_id, relation_type),
            ).fetchall()
        return {str(row["collection_key"] or "") for row in rows}

    def list_existing_relation_collections(
        self,
        *,
        platform: str,
        external_account_id: str,
        relation_type: str,
    ) -> set[str]:
        account_id = stable_id("acct", platform.strip().lower(), external_account_id)
        with self.connection() as con:
            rows = con.execute(
                """SELECT DISTINCT r.collection_key FROM user_relation r
                   JOIN content c ON c.id=r.content_id
                   WHERE c.platform=? AND r.source_account_id=? AND r.relation_type=?""",
                (platform.strip().lower(), account_id, relation_type),
            ).fetchall()
        return {str(row["collection_key"] or "") for row in rows}

    def upsert_sync_run_scope(
        self,
        *,
        sync_run_id: str,
        relation_type: str,
        collection_key: str,
        status: str,
        completeness: str,
        discovered_delta: int = 0,
        imported_delta: int = 0,
        failed_delta: int = 0,
    ) -> None:
        now = utcnow()
        with self.connection() as con:
            con.execute(
                """INSERT INTO sync_run_scope(
                       sync_run_id,relation_type,collection_key,status,completeness,
                       discovered_count,imported_count,failed_count,updated_at
                   ) VALUES(?,?,?,?,?,?,?,?,?)
                   ON CONFLICT(sync_run_id,relation_type,collection_key) DO UPDATE SET
                     status=excluded.status,
                     completeness=excluded.completeness,
                     discovered_count=sync_run_scope.discovered_count+excluded.discovered_count,
                     imported_count=sync_run_scope.imported_count+excluded.imported_count,
                     failed_count=sync_run_scope.failed_count+excluded.failed_count,
                     updated_at=excluded.updated_at""",
                (
                    sync_run_id,
                    relation_type,
                    collection_key,
                    status,
                    completeness,
                    discovered_delta,
                    imported_delta,
                    failed_delta,
                    now,
                ),
            )

    def list_sync_run_scopes(self, sync_run_id: str) -> list[dict[str, Any]]:
        with self.connection() as con:
            rows = con.execute(
                """SELECT * FROM sync_run_scope WHERE sync_run_id=?
                   ORDER BY relation_type,collection_key""",
                (sync_run_id,),
            ).fetchall()
        return [dict(row) for row in rows]

    def upsert_sync_checkpoint(
        self,
        *,
        source_account_id: str,
        relation_type: str,
        collection_key: str,
        cursor: dict[str, Any],
        known_anchor: str | None,
        last_complete_sync_run_id: str | None,
        complete: bool,
    ) -> str:
        checkpoint_id = stable_id("checkpoint", source_account_id, relation_type, collection_key)
        now = utcnow()
        with self.connection() as con:
            con.execute(
                """INSERT INTO sync_checkpoint(
                       id,source_account_id,relation_type,collection_key,cursor_json,known_anchor,
                       last_complete_sync_run_id,last_success_at,updated_at
                   ) VALUES(?,?,?,?,?,?,?,?,?)
                   ON CONFLICT(id) DO UPDATE SET
                     cursor_json=excluded.cursor_json,
                     known_anchor=COALESCE(excluded.known_anchor,sync_checkpoint.known_anchor),
                     last_complete_sync_run_id=CASE WHEN ? THEN excluded.last_complete_sync_run_id ELSE sync_checkpoint.last_complete_sync_run_id END,
                     last_success_at=CASE WHEN ? THEN excluded.last_success_at ELSE sync_checkpoint.last_success_at END,
                     updated_at=excluded.updated_at""",
                (
                    checkpoint_id,
                    source_account_id,
                    relation_type,
                    collection_key,
                    json.dumps(cursor, ensure_ascii=False, sort_keys=True),
                    known_anchor,
                    last_complete_sync_run_id,
                    now,
                    now,
                    1 if complete else 0,
                    1 if complete else 0,
                ),
            )
        return checkpoint_id

    def get_sync_checkpoint(
        self,
        *,
        source_account_id: str,
        relation_type: str,
        collection_key: str,
    ) -> dict[str, Any] | None:
        checkpoint_id = stable_id("checkpoint", source_account_id, relation_type, collection_key)
        with self.connection() as con:
            row = con.execute("SELECT * FROM sync_checkpoint WHERE id=?", (checkpoint_id,)).fetchone()
        if not row:
            return None
        result = dict(row)
        try:
            cursor = json.loads(result.pop("cursor_json") or "{}")
        except (TypeError, ValueError):
            cursor = {}
        result["cursor"] = cursor if isinstance(cursor, dict) else {}
        return result

    def artifact_unique_bytes(self) -> int:
        with self.connection() as con:
            row = con.execute("SELECT COALESCE(SUM(byte_size),0) AS total FROM (SELECT sha256,MAX(byte_size) AS byte_size FROM artifact GROUP BY sha256)").fetchone()
            return int(row["total"] if row else 0)

    def list_artifacts_for_replication(
        self,
        store_id: str,
        *,
        limit: int = 100,
        requires_verified_store: str | None = None,
    ) -> list[dict[str, Any]]:
        args: list[Any] = [store_id]
        prerequisite = ""
        if requires_verified_store:
            prerequisite = """AND EXISTS (
                SELECT 1 FROM object_replica required
                WHERE required.artifact_id=a.id AND required.store_id=? AND required.status='verified'
            )"""
            args.append(requires_verified_store)
        args.append(min(max(limit, 1), 1000))
        sql = f"""SELECT a.*
                  FROM artifact a
                  LEFT JOIN object_replica current
                    ON current.artifact_id=a.id AND current.store_id=?
                  WHERE a.local_path IS NOT NULL
                    AND a.status IN ('staged','ready','complete')
                    AND (current.status IS NULL OR current.status!='verified')
                    {prerequisite}
                  ORDER BY a.created_at ASC
                  LIMIT ?"""
        with self.connection() as con:
            return [dict(row) for row in con.execute(sql, args).fetchall()]

    def get_object_replica(self, artifact_id: str, store_id: str) -> dict[str, Any] | None:
        """Return one replica receipt without granting it completion authority."""
        with self.connection() as con:
            row = con.execute(
                """SELECT id,artifact_id,store_id,object_key,status,etag,verified_sha256,
                          original_sha256,encryption,updated_at,last_error_code
                   FROM object_replica WHERE artifact_id=? AND store_id=?""",
                (artifact_id, store_id),
            ).fetchone()
        return dict(row) if row else None

    def upsert_object_replica(
        self,
        *,
        artifact_id: str,
        store_id: str,
        object_key: str,
        status: str,
        etag: str | None = None,
        verified_sha256: str | None = None,
        original_sha256: str | None = None,
        encryption: str | None = None,
        last_error_code: str | None = None,
    ) -> str:
        replica_id = stable_id("replica", artifact_id, store_id)
        with self.connection() as con:
            con.execute(
                """INSERT INTO object_replica(id,artifact_id,store_id,object_key,status,etag,verified_sha256,original_sha256,encryption,updated_at,last_error_code)
                   VALUES(?,?,?,?,?,?,?,?,?,?,?)
                   ON CONFLICT(artifact_id,store_id) DO UPDATE SET
                     object_key=excluded.object_key,status=excluded.status,etag=excluded.etag,
                     verified_sha256=excluded.verified_sha256,original_sha256=excluded.original_sha256,
                     encryption=excluded.encryption,updated_at=excluded.updated_at,last_error_code=excluded.last_error_code""",
                (replica_id, artifact_id, store_id, object_key, status, etag, verified_sha256, original_sha256, encryption, utcnow(), last_error_code),
            )
            if status == "verified":
                rows = con.execute(
                    "SELECT store_id,verified_sha256,original_sha256,encryption FROM object_replica WHERE artifact_id=? AND status='verified'",
                    (artifact_id,),
                ).fetchall()
                by_store = {row["store_id"]: row for row in rows}
                required = {"r2", "oci", "github"}
                if required.issubset(by_store):
                    cipher_hashes = {str(by_store[item]["verified_sha256"] or "") for item in required}
                    original_hashes = {str(by_store[item]["original_sha256"] or "") for item in required}
                    algorithms = {str(by_store[item]["encryption"] or "") for item in required}
                    if len(cipher_hashes) == 1 and "" not in cipher_hashes and len(original_hashes) == 1 and len(algorithms) == 1:
                        con.execute("UPDATE artifact SET status='complete' WHERE id=?", (artifact_id,))
        return replica_id

    def replica_summary(self) -> list[dict[str, Any]]:
        with self.connection() as con:
            rows = con.execute(
                """SELECT r.store_id,r.status,COUNT(*) AS object_count,COALESCE(SUM(a.byte_size),0) AS byte_count
                   FROM object_replica r JOIN artifact a ON a.id=r.artifact_id
                   GROUP BY r.store_id,r.status ORDER BY r.store_id,r.status"""
            ).fetchall()
            return [dict(row) for row in rows]

    def replication_completion(self) -> dict[str, int]:
        with self.connection() as con:
            total = int(con.execute("SELECT COUNT(*) FROM artifact").fetchone()[0])
            complete = int(con.execute("SELECT COUNT(*) FROM artifact WHERE status='complete'").fetchone()[0])
            pending = max(0, total - complete)
            return {"required_replicas": 3, "total_artifacts": total, "all_three_verified": complete, "pending": pending}


class TenantScope:
    """按 user_id 收敛的读取视图（v0.0.0.7 / T01）。

    存在的理由：把"记得加 user_id"从**纪律**变成**类型**。
    面向用户的读取只要走这里，就不可能忘记过滤；裸 RuntimeStore 留给 worker
    与运维路径，它们本来就需要跨用户看作业队列。

    单条获取（get_*）一律先验证归属再返回，**不归你的一律返回 None** ——
    不是抛异常。返回 None 让调用方自然走向 404，而 403 会泄漏"这个 id 存在"
    这一事实本身。
    """

    def __init__(self, store: RuntimeStore, user_id: str):
        self._store = store
        self.user_id = user_id

    # ── 资料库 ────────────────────────────────────────────────────
    def list_library(self, **kwargs: Any) -> list[dict[str, Any]]:
        kwargs.pop("user_id", None)  # 调用方不得覆盖租户边界
        return self._store.list_library(user_id=self.user_id, **kwargs)

    def list_library_table(self, **kwargs: Any) -> dict[str, Any]:
        kwargs.pop("user_id", None)
        return self._store.list_library_table(user_id=self.user_id, **kwargs)

    def get_content(self, content_id: str) -> dict[str, Any] | None:
        """只有当本用户对该内容确有一条关系时才返回。

        content 本身是全局去重的共享维度，光有 content_id 不代表有权看它；
        凭据是 user_relation 上的那条边。
        """
        if not self._owns_content(content_id):
            return None
        return self._store.get_content(content_id)

    def content_bodies(self, content_ids: list[str]) -> dict[str, str]:
        owned = [cid for cid in content_ids if self._owns_content(cid)]
        return self._store.content_bodies(owned) if owned else {}

    # ── 来源账号 ──────────────────────────────────────────────────
    def list_source_accounts(self) -> list[dict[str, Any]]:
        return [a for a in self._store.list_source_accounts() if a.get("user_id") == self.user_id]

    def get_source_account(self, account_id: str, *, include_handle: bool = False) -> dict[str, Any] | None:
        account = self._store.get_source_account(account_id, include_handle=include_handle)
        if account is None or account.get("user_id") != self.user_id:
            return None
        return account

    # ── 同步运行 ──────────────────────────────────────────────────
    def list_sync_runs(self, *, source_account_id: str | None = None, limit: int = 100) -> list[dict[str, Any]]:
        if source_account_id and self.get_source_account(source_account_id) is None:
            return []
        runs = self._store.list_sync_runs(source_account_id=source_account_id, limit=limit)
        return [r for r in runs if r.get("user_id") == self.user_id]

    def get_sync_run(self, sync_run_id: str) -> dict[str, Any] | None:
        run = self._store.get_sync_run(sync_run_id)
        if run is None or run.get("user_id") != self.user_id:
            return None
        return run

    # ── 内部 ──────────────────────────────────────────────────────
    def _owns_content(self, content_id: str) -> bool:
        with self._store.connection() as con:
            row = con.execute(
                "SELECT 1 FROM user_relation WHERE content_id=? AND user_id=? LIMIT 1",
                (content_id, self.user_id),
            ).fetchone()
        return row is not None
