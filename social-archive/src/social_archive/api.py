
from __future__ import annotations

import io
import zipfile
import json
import ipaddress
import os
import secrets
import threading
import time
from dataclasses import asdict
from datetime import UTC, date, datetime
from pathlib import Path, PurePosixPath
from typing import Any, Literal
from urllib.parse import urlparse

import uvicorn
from fastapi import Depends, FastAPI, Header, HTTPException, Query, Request
from fastapi.responses import FileResponse, JSONResponse, PlainTextResponse, Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, ConfigDict, Field

from . import __version__, auth, failure_copy
from .account_sync import (
    SERVER_ACCOUNT_CONNECTORS,
    NOT_SYNCABLE_YET,
    SYNCABLE_NOW,
    AccountSyncCoordinator,
    PLATFORM_LABELS,
    PLATFORM_RELATIONS,
)
from .config import Settings
from .data_export_import import read_export_archive
from .credentials import CUSTODIAL_PLATFORMS
from .platform_payloads import PayloadUnreadable, parse_bilibili_favlist
from .payload_shape import sketch
from .db import RuntimeStore
from .credentials import (
    CUSTODIAL_PLATFORMS,
    DOMESTIC_PLATFORMS,
    CredentialRejected,
    CredentialStore,
    CredentialUnavailable,
    CredentialVault,
)
from .destinations import DestinationRegistry, _markdown
from .failure_copy import describe_sync_outcome
from .models import (
    AccountConnectCompleteRequest,
    AccountConnectRequest,
    AccountSyncRequest,
    CaptureBatchRequest,
    CaptureRequest,
    CaptureResponse,
    ConnectorRunRequest,
    JobView,
    MarkdownImportRequest,
    SyncBatchRequest,
    SyncControlRequest,
)
from .registry import ConnectorRegistry
from .service import ArchiveService
from .utils import atomic_write, json_bytes, read_secret, sha256_bytes, utcnow

settings = Settings.from_env()
settings.ensure_directories(require_api_token=True)
store = RuntimeStore(settings.runtime_db)
store.initialize()
service = ArchiveService(settings, store)
registry = ConnectorRegistry(settings)
destinations = DestinationRegistry(settings, store)
account_sync = AccountSyncCoordinator(settings, store, service, registry)
app = FastAPI(title="Social Archive", version=__version__, docs_url="/api/docs", redoc_url=None)
# 登录路由（v0.0.0.7 / T02）。挂在这里而不是散进本文件：auth 有自己的
# Cookie 语义与失败文案，混进 pairing/token 那套只会互相污染。
app.include_router(auth.build_router(settings, store))

# 有界 Cookie 托管（v0.0.0.7 / T05）。
# 凭据用独立密钥对，**不回退到备份那对**——回退会让「备份通道只有公钥」
# 这条性质在没人察觉的情况下失效。没配就是没配，写入时明确 503。
credential_vault = CredentialVault(
    recipient=settings.credential_age_recipient,
    identity_file=settings.credential_age_identity_file,
)
credential_store = CredentialStore(store, credential_vault)


class ClassifyRequest(BaseModel):
    """「批量修改分类」那颗按钮送上来的东西（v0.0.0.7 / T15）。

    **这个模型和它的路由此前都不存在**，而 `apps/pwa/app.js` 一直在往
    `POST /v1/library/classify` 发这三个字段。2026-08-06 实测：405 Method Not Allowed。
    """
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    content_ids: list[str] = Field(min_length=1, max_length=500)
    topic: str = Field(default="未分类", max_length=256)
    keywords: list[str] = Field(default_factory=list, max_length=32)


class ExportRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    destination_ids: list[str] = Field(default_factory=list, max_length=8)


class CredentialUploadRequest(BaseModel):
    """上传一份平台会话。

    字段名刻意叫 cookies_txt 而不是 cookies/session/token —— 让它在日志、
    异常和 diff 里一眼可辨，脱敏守卫也好按名字兜底。
    """

    model_config = ConfigDict(extra="forbid")
    # 1 MiB 足够任何平台的 cookies.txt；再大基本是误传了别的文件。
    cookies_txt: str = Field(min_length=1, max_length=1_048_576)


def _credential_user(request: Request) -> str:
    """凭据路由只认**会话**，不认共享 bearer 令牌。

    共享令牌是给扩展做业务上行的；凭据的写入与撤销必须绑定到一个具体的人，
    否则"按 user_id 隔离"就成了空话——拿着同一个令牌谁都能覆盖别人的会话。
    """
    user_id = auth.session_user_id(request, store)
    if not user_id:
        raise HTTPException(status_code=401, detail="请先登录你的档案馆。")
    return user_id


@app.get("/v1/credentials")
def list_credentials(request: Request) -> dict[str, Any]:
    """只回状态，永不回值。"""
    user_id = _credential_user(request)
    return {"items": [
        {
            "platform": item.platform, "connected": item.connected,
            "cookie_count": item.cookie_count, "updated_at": item.updated_at,
            "last_used_at": item.last_used_at,
        }
        for item in credential_store.status(user_id)
    ]}


@app.put("/v1/credentials/{platform}", status_code=200)
def put_credential(platform: str, payload: CredentialUploadRequest, request: Request) -> dict[str, Any]:
    user_id = _credential_user(request)
    try:
        status = credential_store.put(
            user_id=user_id, platform=platform, cookies_txt=payload.cookies_txt
        )
    except CredentialRejected as exc:
        # 400 而不是 422：这不是格式问题，是**产品明确不接收**这个平台的凭据。
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except CredentialUnavailable as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    return {
        "platform": status.platform, "connected": True,
        "cookie_count": status.cookie_count, "updated_at": status.updated_at,
        "message_zh": "登录信息已加密保存，随时可以一键撤销。",
    }


@app.delete("/v1/credentials/{platform}")
def delete_credential(platform: str, request: Request) -> dict[str, Any]:
    user_id = _credential_user(request)
    removed = credential_store.revoke(user_id=user_id, platform=platform)
    return {
        "platform": str(platform or "").strip().lower(), "revoked": removed,
        "connected": False,
        "message_zh": "已撤销并从库中删除。" if removed else "本来就没有保存这个平台的登录信息。",
    }


class LocalObsidianReceiptRequest(BaseModel):
    """An attested receipt from the paired extension's fixed loopback bridge."""

    model_config = {"extra": "forbid", "str_strip_whitespace": True}
    content_id: str = Field(min_length=1, max_length=200)
    status: Literal["done", "noop", "failed"]
    remote_path: str | None = Field(default=None, max_length=2048)


def _observed_bound(value: str | None, *, end_of_day: bool) -> str | None:
    if not value:
        return None
    candidate = value.strip()
    try:
        if len(candidate) == 10:
            day = date.fromisoformat(candidate)
            return f"{day.isoformat()}T{'23:59:59.999999Z' if end_of_day else '00:00:00Z'}"
        parsed = datetime.fromisoformat(candidate.replace("Z", "+00:00"))
    except ValueError as exc:
        raise HTTPException(status_code=422, detail="时间筛选仅支持 ISO 8601 日期或日期时间") from exc
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC).isoformat().replace("+00:00", "Z")


def _safe_local_obsidian_path(value: str | None) -> str | None:
    if value is None:
        return None
    path = PurePosixPath(value)
    if (
        path.is_absolute()
        or len(path.parts) < 3
        or path.parts[0] != "Social Archive"
        or any(part in {"", ".", ".."} for part in path.parts)
        or path.suffix.lower() != ".md"
    ):
        raise HTTPException(status_code=422, detail="Obsidian 本机回执路径必须位于 Social Archive/ 且为 Markdown 文件")
    return str(path)


def _expected_token() -> str | None:
    return read_secret(settings.api_token_file)


def _request_hostname(request: Request) -> str:
    raw = request.headers.get("host", "").strip().lower()
    if not raw or "," in raw:
        return ""
    return (urlparse(f"//{raw}").hostname or "").lower().rstrip(".")


def _public_hostname(value: str) -> str:
    return (urlparse(value).hostname or "").lower().rstrip(".")


def _trusted_library_access(request: Request) -> bool:
    """Trust Cloudflare Access only on the dedicated library hostname.

    The origin is loopback-only behind Cloudflare Tunnel. Cloudflare Access injects
    the assertion after authentication; the API hostname is deliberately excluded.
    """
    expected_host = _public_hostname(settings.public_library_url)
    actual_host = _request_hostname(request)
    assertion = request.headers.get("cf-access-jwt-assertion", "").strip()
    return bool(expected_host and actual_host == expected_host and len(assertion) >= 80)


# v0.0.0.7 / T03：这里原有 `require_api_hostname`，用途是
# 「把**未鉴权的配对端点**挡在私有资料库域名之外」。配对链路已随 T03 删除，
# 于是它守的那批端点一个都不存在了，全仓也没有任何一处 Depends 引用它
# （scripts/find_unwired_code.py 扫出来的）。
#
# 留着比删掉更糟：一个名字叫 require_* 的函数摆在鉴权代码中间，
# 会让人以为这层防护还在生效。**没有生效的防护要显式删掉，不能留着装样子。**
# 真正的鉴权在下面的 require_token 与 auth.session_user_id。


def require_token(request: Request, authorization: str | None = Header(default=None)) -> None:
    if not settings.pairing_required:
        return
    if _trusted_library_access(request):
        return
    supplied = authorization.removeprefix("Bearer ").strip() if authorization else ""
    # v0.0.0.7 / T03：先认扩展令牌（长期、可撤销、绑 user_id）。
    # 配对码那条路暂时保留，等它整条链路删干净再摘——先加后删，
    # 否则会出现一个扩展既不能用旧机制也还没接上新机制的空窗期。
    if supplied and store.resolve_extension_token(supplied):
        return
    expected = _expected_token()
    if not expected:
        raise HTTPException(503, "服务端配对尚未完成")
    if not supplied or not secrets.compare_digest(supplied, expected):
        raise HTTPException(401, "扩展尚未授权或令牌已失效")


# **能用的最低插件版本**（v0.0.0.20）。
#
# 此前资料库判兼容用的是 `version === PRODUCT_VERSION`——**完全相等才算兼容**。
# 于是服务端每升一个补丁版本，所有已装插件当场全部被判成不兼容，
# 同步、保存、连接全被挡住，直到用户手动去覆盖文件。
#
# 2026-08-06 一天里升了 19 个版本，**每一次都会把他整个锁在外面**。
# 而他这一轮开工时的原话正是：「整个软件完全不能使用」。
# 那次的直接原因是安装页不讲更新，但**这条相等判据才是让它变致命的东西**。
#
# 改成「不低于某个下限」。这个下限**只在真的破坏兼容时才动**：
# 批次协议变了、接口语义变了、老插件会写坏数据。
# 界面文案、标签页行为、筛选框这类改动一律不动它——
# 那些值得提示「有新版本」，不值得把人锁在门外。
#
# 现在定在 0.0.0.9：那是**整条链第一次真的能跑通**的版本
#   · 0.0.0.9 之前没有 B 站取数路，也没有登录态确认（连账号都建不起来）
#   · 0.0.0.9 及以后发的批次形状服务端都收得下（两种形状都有判据在跑）
MINIMUM_EXTENSION_VERSION = "0.0.0.9"


def _free_disk() -> dict[str, Any]:
    """数据库所在那块盘还剩多少。**量的是数据库那条路，不是根分区。**

    量错地方是这类检查最常见的空转：根分区宽裕而数据盘满了，它照样报健康。
    这里用数据库文件所在目录去问，问不出来就说问不出来——
    **不许拿 0 或者 null 冒充「没问题」**（这个仓栽在空默认值上不止一次）。
    """
    import shutil

    target = Path(settings.runtime_db).expanduser().resolve()
    for candidate in (target, *target.parents):
        if candidate.exists():
            try:
                usage = shutil.disk_usage(candidate)
            except OSError as error:                      # noqa: PERF203
                return {"measured": False, "why_zh": f"量不出来：{error}"}
            # **量了不说等于没量。**（2026-08-10）
            #
            # 这几个数从 v0.0.0.18 起就在 /health 里，而**没有任何界面读过它们**
            # （`grep -n "health.disk" apps/pwa/app.js apps/browser-extension/popup.js`
            # 是空的）。同一天实测：主机跑到 95.8%、只剩 1.59G，
            # 而资料库那一屏一个字都没提；`/v1/storage/status` 说「配额正常」——
            # 它说的是**我们自己的 R2/OCI 字节预算**，和主机磁盘是两件事。
            #
            # 后果是具体的：盘真满了以后媒体下不下来，而界面会一直说「配额正常」，
            # 他会以为是平台挡的（那一列正好写着「视频没存下」）。
            #
            # **判断和句子都放在这里**，因为界面那一侧的规矩是
            # 「接口自带 message_zh，我们不另造句子」（造句子等于绕过冻结词典）。
            #
            # 阈值取 2 GiB：这个产品会下载媒体（L3），单个视频几十到几百 MB，
            # 低于 2G 就是"下一个大文件可能落不下来"。它只用来**提醒**，
            # 不拦任何东西——真正的暂停由配额那条路负责。
            free_bytes = usage.free
            tight = free_bytes < 2 * 1024 ** 3
            payload = {
                "measured": True,
                "measured_at": str(candidate),
                "free_bytes": free_bytes,
                "free_gb": round(free_bytes / 1024 ** 3, 2),
                "total_gb": round(usage.total / 1024 ** 3, 2),
                "used_percent": round(100 * (usage.total - usage.free) / usage.total, 1)
                if usage.total else None,
                "tight": tight,
            }
            if tight:
                payload["message_zh"] = (
                    f"服务器磁盘只剩 {payload['free_gb']} G（已用 {payload['used_percent']}%）。"
                    "文字和链接照常保存；再满下去，新的视频文件可能存不下来。"
                )
            return payload
    return {"measured": False, "why_zh": "数据库路径的每一层都不存在，量不到盘"}


# 复制/备份那条链**上一次真的跑完是什么时候**。（2026-08-13）
#
# ## 为什么要有这一格
#
# 2026-08-11 23:53 起，`social-archive-replication.service` 每次触发都以
# `200/CHDIR` 失败（有人把 `/opt/social-archive` 改成了 700，而它以
# socialarchive 用户跑）。**连着失败 108 次、28 小时**，而：
#
#   · `/v1/status` 的 `replicas` 一直是 `verified` —— 那是**库里记着的历史回执**，
#     记的是过去成功过，不是现在还在跑；
#   · `recovery.last_backup` 写死成 "unknown"；
#   · 界面上没有任何一处提到备份。
#
# **「加密存三份」停了一天多，而每一个绿灯都还是绿的。**
#
# ## 这一格取的是什么
#
# `replicate_objects.py` 每跑一次就重写 `status/object-replication.json`。
# 服务跑不起来时脚本根本不执行，那个文件就停在旧时间——**所以它的时间戳
# 是这条链的活性信号**，而回执是历史。两者差别正是这次事故的全部。
def _replication_liveness() -> dict[str, Any]:
    path = settings.data_root / "status/object-replication.json"
    try:
        document = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {"last_run_at": None, "status": "unknown", "stale": None,
                "why": "还没有 status/object-replication.json"}
    last = str(document.get("generated_at") or "")
    hours: float | None = None
    try:
        seen = datetime.fromisoformat(last.replace("Z", "+00:00"))
        hours = (datetime.now(UTC) - seen).total_seconds() / 3600.0
    except ValueError:
        pass
    # 定时器约每 15 分钟触发一次，2 小时没动过就是真的没在跑了。
    stale = None if hours is None else hours > 2.0
    status = str(document.get("status") or "unknown")
    # **句子在这边写，界面只负责说出来**（和存储吃紧那一格同一个规矩：
    # 界面自己造句等于绕过冻结词典）。
    #
    # 措辞要先按住他最担心的那件事：**已经存下来的东西没有少**。
    # 停的是"再复制一份到别处"，不是"你的东西丢了"。
    # 句子在冻结词典里（`failure_copy`），这里只挑哪一句——
    # 「词典只有一处真源」，而且那本词典也在 check_docs_match_the_ui 的语料里，
    # 说明书引用它时对得上。
    message = ""
    if stale:
        message = failure_copy.backup_stale_sentence(hours)
    elif status not in ("PASS", "unknown"):
        message = failure_copy.BACKUP_RUN_INCOMPLETE_SENTENCE
    return {
        "last_run_at": last or None,
        "status": status,
        "hours_since": None if hours is None else round(hours, 2),
        "stale": stale,
        "message_zh": message,
    }


# **备份本身**上一次真的做出来是什么时候。（2026-08-13）
#
# 上面那一格盯的是 replication（把制品再复制到别处）。这一格盯它的上游：
# `backup.timer` 每天跑一次 `backup.py`，做出一份加密快照。**两条链会单独死。**
#
# 2026-08-12、08-13 连着两天，`backup.service` 以同一个 `200/CHDIR` 失败——
# 和 08-11 那次 replication 事故同一个根因（`/opt/social-archive` 被改回 700，
# 两个服务共用这个 `WorkingDirectory`）。后果在快照目录上一目了然：
#
#     20260811T032747Z   ← 最后一次自动备份
#     （8/12、8/13 两天整个缺失）
#     20260813T085049Z   ← 人手触发才补上的
#
# **而修那次事故时我只确认了 replication 恢复、没回头查 backup**，
# 于是它又静静死了两天，`/health` 全程一个字都没有。
#
# ## 这一格取的是什么
#
# 不新增心跳文件，**直接看产物**：`backups/private-database/<UTC 时间戳>/`，
# 目录名就是那次备份的时刻。而且要求里面有 `manifest.json`——跑一半崩掉也会
# 留下目录，**光有目录不算做完**。自述会骗人，产物不会。
def _newest_completed_snapshot(root: Path) -> tuple[datetime | None, str, bool]:
    """那个目录里**最近一份做完的**快照。回 (时刻, 目录名, 读得到吗)。

    做完的标记是里面有 `manifest.json`——跑一半崩掉也会留下目录，
    **光有目录不算做完**。
    """
    readable = True
    try:
        entries = list(root.iterdir())
    except FileNotFoundError:
        # 目录不在 = 确实一次都没备份过（备份跑起来会自己建）。这是**知道**，不是不知道。
        entries = []
    except OSError:
        # 读不动（权限等）——这才是真的不知道。**不许和上一支并成一个默认值。**
        readable, entries = False, []

    newest: datetime | None = None
    newest_name = ""
    for entry in entries:
        if not (entry / "manifest.json").is_file():
            continue  # 跑一半留下的空壳
        try:
            when = datetime.strptime(entry.name, "%Y%m%dT%H%M%SZ").replace(tzinfo=UTC)
        except ValueError:
            continue
        if newest is None or when > newest:
            newest, newest_name = when, entry.name
    return newest, newest_name, readable


def _backup_liveness() -> dict[str, Any]:
    # **备份服务一次跑四件事，而只看第一件会漏掉后面三件。**（2026-08-13）
    #
    # `social-archive-backup.service` 里串着四条 ExecStart，`Type=oneshot`
    # 按序执行、前一条失败就不往下走：
    #
    #     backup.py --once                  做私有库加密快照
    #     backup_runtime_db.py --github     做运行库快照并推一份到 GitHub
    #     prune_runtime_db_snapshots.py     清理
    #     prune_r2_backup_replicas.py       清理
    #
    # 第一条成了、第二条挂了 → 服务整体失败，**而私有库那边有新快照**，
    # 只看它就是绿的。宿主机上 `check_durability_units.sh` 第四列抓得到，
    # 徽章抓不到——而他看的是徽章。
    #
    # 所以两条链都看，**取更旧的那一个**（最弱的一环）。不新增句子：
    # 「已经 N 小时没有做出新的备份了」对两条都成立。
    newest, newest_name, readable = _newest_completed_snapshot(
        settings.data_root / "backups/private-database")
    rt_newest, rt_name, rt_readable = _newest_completed_snapshot(
        settings.data_root / "backups/runtime-db")

    # 取更旧的那条当口径；任一条读不到就整体算读不到。
    readable = readable and rt_readable
    if newest is not None and rt_newest is not None:
        newest, newest_name = ((newest, newest_name) if newest <= rt_newest
                               else (rt_newest, rt_name))
    elif rt_newest is None:
        newest, newest_name = None, ""

    if newest is None:
        # **「读不到」和「确实一个都没有」是两回事**，不许并成一个默认值：
        # 前者是不知道（不该拿它吓人），后者是真的没有备份（必须说）。
        if not readable:
            return {"last_backup_at": None, "hours_since": None, "stale": None,
                    "message_zh": "",
                    "why": "读不到 backups/private-database——这不等于没有备份"}
        return {"last_backup_at": None, "hours_since": None, "stale": True,
                "message_zh": failure_copy.NO_BACKUP_YET_SENTENCE,
                "why": "backups/private-database 下没有一个做完的快照"}

    hours = (datetime.now(UTC) - newest).total_seconds() / 3600.0
    # 定时器一天一次（带几分钟抖动）。30 小时 = **整整一次都没跑成**，
    # 不是"跑晚了几分钟"——留够余量，免得变成狼来了。
    stale = hours > 30.0
    return {
        "last_backup_at": newest_name,
        "hours_since": round(hours, 2),
        "stale": stale,
        "message_zh": failure_copy.backup_missing_sentence(hours) if stale else "",
    }


@app.get("/health")
def health() -> dict[str, Any]:
    return {
        "status": "ok",
        "project": "Social Archive",
        "version": __version__,
        "time": utcnow(),
        "paid_api_allowed": settings.paid_api_allowed,
        "archive_defaults": {"L0": True, "L1": True, "L2": settings.l2_enabled, "L3": settings.l3_enabled},
        # **备份这条链还在不在跑**——不是"以前成功过"，是"刚才跑过"。
        #
        # 两格，因为是两条会单独死的链：`backup` 做出快照，`replication`
        # 把它复制到别处。2026-08-12~13 实测只死了前一条，而当时只有后一条
        # 接了出来，于是整整两天没有新备份、而这里全绿。
        "backup": _backup_liveness(),
        "replication": _replication_liveness(),
        # **后台在不在跑，也算健康的一部分。**
        #
        # 2026-08-06 一次被打断的部署留下 core-api 起来了、core-worker 卡在
        # Created 没启动。而这个端点由 api 提供，它照样回 "ok" ——
        # 从外面完全看不出后台没在跑，任务只会静静积压。
        # 一个只报"我自己还在"的健康检查，正是这个产品一直在防的那种沉默。
        #
        # 放在这里（而不是只放 /v1/status）是因为**部署脚本打的就是这一条**，
        # 而那次故障恰恰要在部署当场被发现。
        "worker": store.worker_liveness(),
        # **盘满是这个服务已知的死法，而此前没有任何东西会先说一声。**
        #
        # 2026-08-05 那次：/v1/accounts 报 `sqlite3.OperationalError:
        # unable to open database file`——SQLite 建不出 -wal/-shm 时就是这句。
        # 部署脚本因此立了「不足 5G 不许构建」那道门，但那只拦住**我**，
        # 拦不住盘自己满：2026-08-07 实测同机另一个项目的容器可写层
        # 2.5 小时涨了 0.58G（2.48→3.06GB），而我们自己的服务一声不吭。
        #
        # 放在 /health 是因为它是唯一一条不需要鉴权、任何监控都打得到的路。
        # **只报事实，不在这里判死活**：判多少算低是监控的事，
        # 而一个会因为磁盘把自己标成不健康的服务，会在还能用的时候被摘掉。
        "disk": _free_disk(),
        # 资料库据此判「这个插件还能用吗」。**不是拿它和当前版本比相等**——
        # 见 MINIMUM_EXTENSION_VERSION 上面那段。
        "minimum_extension_version": MINIMUM_EXTENSION_VERSION,
    }


@app.get("/v1/status", dependencies=[Depends(require_token)])
def status() -> dict[str, Any]:
    return {
        "project": "Social Archive",
        "version": __version__,
        "endpoint": settings.public_base_url,
        "library_url": settings.public_library_url,
        "archive_defaults": ["L0", "L1", "L3"],
        "l2_enabled": settings.l2_enabled,
        "connectors": registry.health_views(store.connector_states()),
        "destinations": destinations.views(),
        "queue": {"items": store.list_jobs(limit=20)},
        "storage": {"items": store.quota_states(), "replicas": store.replica_summary(), "completion": store.replication_completion()},
        # INV-NO-SILENT-ZERO 的两个审计。**必须挂在这里才算数**——
        # 在此之前它们都只是库里的函数，没有任何调用方，
        # 也就是说「不许有说不清的零」这条不变量其实没有任何东西在执行。
        #
        #   unexplained_zero  终态、0 条、没有失败码 —— v0.0.0.6 的那种零
        #   stalled           永远到不了终态 —— 「点了同步一直在转」的那种
        #
        # 两者不重叠：前者只看终态，后者只看非终态。
        "sync_health": {
            "unexplained_zero": store.unexplained_zero_runs(limit=20),
            "stalled": store.stalled_active_runs(limit=20),
        },
        # T01 的 Oracle。**同样是挂上来才算数**——它此前和上面两个审计一样，
        # 写好了、有判据、全绿，而生产代码里一个调用方都没有
        # （由 scripts/find_unwired_code.py 扫出来，那是同一形态的第 5 次）。
        # `uncovered_tables` 非空说明审计面自己漏了表，比 orphan 计数更要紧。
        "tenancy": store.tenancy_audit(),
        # INV-TRUTH-TRACEABLE。同样是「挂上来才算数」——这条不变量此前
        # 一个判据都没有。broken 非空 = 库里有东西说不清从哪来。
        "provenance": store.provenance_audit(),
    }


def _safe_account_metadata(metadata: dict[str, Any]) -> dict[str, Any]:
    """Reject credential-shaped metadata before it reaches the runtime journal."""
    forbidden = ("cookie", "token", "authorization", "password", "secret", "auth_header")
    bad: list[str] = []

    def inspect(value: Any, path: str = "metadata") -> None:
        if isinstance(value, dict):
            for key, nested in value.items():
                key_text = str(key)
                key_path = f"{path}.{key_text}"
                if any(marker in key_text.lower() for marker in forbidden):
                    bad.append(key_path)
                inspect(nested, key_path)
        elif isinstance(value, list):
            for index, nested in enumerate(value):
                inspect(nested, f"{path}[{index}]")

    inspect(metadata)
    if bad:
        raise HTTPException(status_code=422, detail="账号连接元数据不得包含 Cookie、令牌、密码或认证头")
    return dict(metadata)


@app.get("/v1/accounts", dependencies=[Depends(require_token)])
def accounts() -> dict[str, Any]:
    return {
        "items": store.list_source_accounts(),
        # **每个平台附上「现在同步得动吗」。** 界面照着画，不自己判断。
        # 给不出 sync_supported 的话，界面只能对所有平台一律画「立即同步」，
        # 而其中四个点下去必然失败——那正是 Owner 说「不知道怎么操作」的来源。
        "supported_platforms": [
            {
                "platform": platform,
                "relations": relations,
                "sync_supported": platform in SYNCABLE_NOW,
                "not_syncable_reason": NOT_SYNCABLE_YET.get(platform, ""),
                # **谁来干这活：服务端，还是浏览器。**
                #
                # 少了这一条，扩展只能猜——而它猜错了。syncAccountById 里
                # 除了 Chrome 书签之外一律走 runBrowserAccountSync，
                # 那条路会 `chrome.tabs.update(tabId, {url, active: true})`
                # **抢走用户正在看的标签页并切到前台**，然后撞上
                # acquireRelationItems() 这个显式 stub。
                #
                # 实测（2026-08-04，真 Chrome）：对 x 跑一次
                # runBrowserAccountSync，标签页被抢了 2 次
                # （→ x.com/i/bookmarks，→ x.com/home，两次 active=true），
                # 而服务端这边 x 明明在 SERVER_ACCOUNT_CONNECTORS 里、
                # 根本不需要浏览器参与。
                #
                # 这是同一个 Owner 抱怨（「把目标网页开了关关了开」）的另一半：
                # 上一轮只挡住了「服务端说同步不了」的平台，
                # 这一条挡住「服务端自己就能干、根本不该动浏览器」的平台。
                "server_handled": platform in SERVER_ACCOUNT_CONNECTORS,
                # **「能不能同步」和「连它有没有用」是两个问题。**
                #
                # 把 x / instagram 移出 SYNCABLE_NOW 之后，界面顺手把它们的
                # 「连接账号」按钮也一起藏了——因为那段代码写的是
                # 「同步不了的平台，连了也没用」。那句话对国内四家是真的
                # （它们的 Cookie 一步都不离开浏览器，服务端根本不接收），
                # **对 x / instagram 是假的**：托管的登录状态会被
                # worker.py 的 L3 取原文件那条路用到
                # （CredentialStore.materialize → capture_url(cookies_path=…)）。
                #
                # 所以再下发一条。判断依据是 credentials.CUSTODIAL_PLATFORMS
                # ——那张表就是「哪些平台的登录状态可以托管」的真源。
                # reddit 不在里面不是漏掉：它走 OAuth，没有 Cookie 要托管，
                # 而 OAuth 那条路目前没有 Owner 点得到的入口。
                "connect_supported": platform in SYNCABLE_NOW or platform in CUSTODIAL_PLATFORMS,
            }
            for platform, relations in PLATFORM_RELATIONS.items()
        ],
    }


@app.post("/v1/accounts/connect/start", status_code=202, dependencies=[Depends(require_token)])
def account_connect_start(request: AccountConnectRequest) -> dict[str, Any]:
    try:
        result = account_sync.connect_start(request)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return {
        "connection_ref": result.connection_ref,
        "platform": result.platform,
        "auth_method": result.auth_method,
        "state": result.state,
        "next_action_zh": result.next_action_zh,
        "supported_relations": result.supported_relations,
    }


@app.post("/v1/accounts/connect/{platform}/complete", status_code=201, dependencies=[Depends(require_token)])
def account_connect_complete(platform: str, request: AccountConnectCompleteRequest) -> dict[str, Any]:
    metadata = _safe_account_metadata(request.metadata)
    auth_method = str(metadata.get("auth_method") or "browser_session")
    allowed_methods = {"oauth", "qr", "browser_session", "official_export", "local_import", "chrome_bookmarks"}
    if auth_method not in allowed_methods:
        raise HTTPException(status_code=422, detail="账号连接方式无效")
    try:
        account_id = account_sync.complete_connection(
            platform=platform.strip().lower(),
            auth_method=auth_method,
            connection_ref=request.connection_ref,
            external_account_id=request.external_account_id,
            display_name=request.display_name,
            auto_sync_enabled=bool(metadata.get("auto_sync_enabled", True)),
            sync_interval_minutes=int(metadata.get("sync_interval_minutes", settings.account_sync_default_interval_minutes)),
            metadata=metadata,
            verified=request.verified,
        )
        # **同步不了的平台照样连得上——只是不起同步。**（2026-08-10）
        #
        # YouTube 落在这一档：`NOT_SYNCABLE_YET` 那句话自己就写着
        # 「可以点这张卡片上的『连接账号』，把登录状态交给你自己的服务器保管」。
        # 而这里原本无条件起一次首同步，于是我给 start_sync 加上「扫不动就拒绝」
        # 之后，**整个连接当场 422**——把一件他本来做得成的事弄坏了。
        # （是全量判据抓到的，不是我读代码看出来的。）
        scannable = account_sync._scannable_relations(platform.strip().lower())
        first = None
        if scannable:
            first = account_sync.start_sync(
                account_id, AccountSyncRequest(mode="first_full", trigger_type="first_connect"))
    except (TypeError, ValueError) as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return {
        "account_id": account_id,
        "state": "connected",
        "first_sync": first,
        # 不起同步时不许还说「同步已经开始」——那正是这个仓反复出的那种假话。
        "next_action_zh": (
            "账号已连接，首次全量同步已经开始。" if first
            else NOT_SYNCABLE_YET.get(platform.strip().lower())
                 or "账号已连接。本版还不能自动读这个平台，你可以在页面上用扩展手动保存单条。"),
    }


@app.post("/v1/accounts/{account_id}/sync", status_code=202, dependencies=[Depends(require_token)])
def start_account_sync(account_id: str, request: AccountSyncRequest) -> dict[str, Any]:
    try:
        return account_sync.start_sync(account_id, request)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@app.post("/v1/accounts/{account_id}/forget", dependencies=[Depends(require_token)])
def forget_account(account_id: str) -> dict[str, Any]:
    """把这个账号连同它带进来的内容一起删掉——**不可逆**。（2026-08-10）

    Owner 的原话：「账号内存删除，增加删除按钮，从零测试能不能用」。
    他要的是**清干净、从零再走一遍**，用来确认这套东西到底能不能用。

    `DELETE /v1/accounts/{id}`（断开）做不到这件事：内容全留着，重连之后
    分不清「同步真的跑了」还是「本来就有」。

    **只删只属于它的内容**：同一条内容可能同时被两个账号收藏，
    别的账号还留着的一条都不碰，并把「留下几条是因为别人也存了」如实报出来。
    """
    result = store.forget_source_account(account_id)
    if not result.get("found"):
        raise HTTPException(status_code=404, detail="账号不存在")
    shared = int(result["kept_content_shared_with_other_accounts"])
    return {
        "account_id": account_id,
        "platform": result["platform"],
        "removed_relations": result["removed_relations"],
        "removed_content": result["removed_content"],
        "removed_sync_runs": result["removed_sync_runs"],
        "kept_content_shared_with_other_accounts": shared,
        "message_zh": (
            f"已删除这个账号，连同它带进来的 {result['removed_content']} 条内容"
            f"和 {result['removed_sync_runs']} 次同步记录。"
            + (f"另有 {shared} 条因为别的账号也存过而留着。" if shared else "")
            + "这一步不可逆——要再有这些内容，得重新连接并同步一次。"
        ),
    }


@app.delete("/v1/accounts/{account_id}", dependencies=[Depends(require_token)])
def disconnect_account(account_id: str) -> dict[str, Any]:
    """断开一个已连接的账号。**只断连接，不删内容。**

    INV-REVERSIBLE：加了什么就要能撤什么。连接账号一次点击，此前断开做不到，
    而连上之后它每 6 小时自己跑一次——用户没有任何办法让它停下来。

    归档的内容一条都不动：断开是"别再替我去取了"，不是"把我存的东西清掉"。
    平台登录状态的撤销是另一件事，走 DELETE /v1/credentials/{platform}，
    分开让用户各自决定；合并会让「我只是不想它自动跑」变成「登录状态也没了」。
    """
    result = store.disconnect_source_account(account_id)
    if not result.get("found"):
        raise HTTPException(status_code=404, detail="账号不存在")
    kept = int(result["kept_content_count"])
    return {
        "account_id": account_id,
        "connection_state": "disconnected",
        "cancelled_runs": result["cancelled_runs"],
        "kept_content_count": kept,
        "message_zh": (
            f"已断开连接，不会再自动同步。已经存下的 {kept} 条内容都留着，"
            "随时可以重新连接。"
        ),
    }


@app.get("/v1/accounts/{account_id}/sync-runs", dependencies=[Depends(require_token)])
def account_sync_runs(account_id: str, limit: int = Query(50, ge=1, le=500)) -> dict[str, Any]:
    if not store.get_source_account(account_id):
        raise HTTPException(status_code=404, detail="账号不存在")
    return {"items": [
        _explain_sync_run(row)
        for row in store.list_sync_runs(source_account_id=account_id, limit=limit)
    ]}


def _explain_sync_run(row: dict[str, Any]) -> dict[str, Any]:
    """给同步运行补上「给人看的那句话」（v0.0.0.7 / T14）。

    为什么放在服务端而不是各客户端各算一遍：
    PWA 与扩展是两个界面，词典各抄一份就有两处会漂。更要命的是**漏抄**——
    扩展先前压根没有词典，同步失败时只显示状态标签「需要处理」，
    说不出为什么。T14 的验收原文是「界面说得出为什么」，那就得每个界面都能。

    在这里算一次，两边都拿得到，且词典只有一处真源。
    """
    label = PLATFORM_LABELS.get(str(row.get("platform") or ""), str(row.get("platform") or ""))
    outcome = describe_sync_outcome(
        imported=int(row.get("imported_count") or 0),
        failure_code=row.get("last_error_code"),
        platform_label=label,
        status=str(row.get("status") or ""),
        # 卡住与否要看"多久没动"，所以时间戳必须一起传下去。
        updated_at=row.get("updated_at"),
    )
    return {**row, "outcome": outcome["outcome"],
            "message_zh": outcome["message_zh"], "action_zh": outcome["action_zh"]}


@app.get("/v1/sync-runs", dependencies=[Depends(require_token)])
def sync_runs(limit: int = Query(100, ge=1, le=500)) -> dict[str, Any]:
    return {"items": [_explain_sync_run(row) for row in store.list_sync_runs(limit=limit)]}


@app.get("/v1/sync-runs/{sync_run_id}", dependencies=[Depends(require_token)])
def sync_run_detail(sync_run_id: str) -> dict[str, Any]:
    row = store.get_sync_run(sync_run_id)
    if not row:
        raise HTTPException(status_code=404, detail="同步运行不存在")
    return _explain_sync_run(row)


@app.post("/v1/sync-runs/{sync_run_id}/control", dependencies=[Depends(require_token)])
def control_sync_run(sync_run_id: str, request: SyncControlRequest) -> dict[str, Any]:
    if not store.control_sync_run(sync_run_id, request.action):
        raise HTTPException(status_code=409, detail="当前状态不能执行该操作")
    row = store.get_sync_run(sync_run_id)
    return {"sync_run_id": sync_run_id, "action": request.action, "status": row["status"] if row else "unknown"}


@app.post("/v1/sync-runs/{sync_run_id}/batches", status_code=202, dependencies=[Depends(require_token)])
def ingest_sync_batch(sync_run_id: str, request: SyncBatchRequest) -> dict[str, Any]:
    try:
        return account_sync.ingest_batch(sync_run_id, request)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@app.get("/v1/connectors", dependencies=[Depends(require_token)])
def connectors() -> dict[str, Any]:
    return {"items": registry.health_views(store.connector_states())}


# 平台 → 响应解析器。**只登记有实测依据的**。
#
# 登记在这里 ≠ 这个平台可以同步。能不能同步由 account_sync.SYNCABLE_NOW 说了算，
# 那张表要的是「整条链路跑通过」；这张表要的只是「这一段字节我们读得懂」。
# bilibili 在这里、不在那里，正是当前的真实状态。
PAYLOAD_PARSERS = {
    "bilibili": parse_bilibili_favlist,
}


class CapturedResponse(BaseModel):
    """观察器在 Owner 浏览器里抄回来的一条平台响应。

    **正文原样送过来，扩展不解析**（background.js:1303 的原话：
    「解析失败会吞掉本来能救的数据」）。原始字节到了这里，
    读不懂还能留证、还能重放；在浏览器里读不懂就是彻底没了。
    """

    platform: str
    url: str = ""
    body: str



def _record_unreadable_shape(platform: str, url: str, body: str, failure_code: str) -> None:
    """读不懂的时候，把这条响应的**字段骨架**记下来——只记名字，不记值。

    **为什么**：他按那颗诊断按钮是为了让我知道该盯哪个地址。可地址只解决一半——
    拿到之后服务端还得读得懂那个响应，而现在只有 B 站有解析器。也就是说，
    他按完那一下，我拿到抖音的地址，然后发现自己**还是写不出解析器**，
    得回头请他再做一件事。**让他按第二次，正是这个项目一直在拔的那种东西。**

    响应体本来就到了这台机器（就是这个端点收的），读完就丢。读不懂时把结构留下，
    我照着写解析器，他那一下就够了。

    **只记名字、类型、长度，一个值都不记**（见 `payload_shape` 的硬边界）。
    写不进去不抛：这是锦上添花，不能因为它让那一按失败。
    """
    try:
        target = settings.data_root / "diagnostics" / "unreadable-payload-shapes.jsonl"
        target.parent.mkdir(parents=True, exist_ok=True)
        line = json.dumps({
            "at": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
            "platform": platform,
            "url": url.split("?")[0],
            "failure_code": failure_code,
            "sketch": sketch(body),
        }, ensure_ascii=False)
        with target.open("a", encoding="utf-8") as handle:
            handle.write(line + "\n")
    except Exception:                                        # noqa: BLE001
        pass


@app.post("/v1/extension/captures/parse", dependencies=[Depends(require_token)])
def parse_captured_response(payload: CapturedResponse) -> dict[str, Any]:
    """把一条抓回来的响应体读成条目——**或者说清为什么读不成**。

    这个端点存在的理由是一件实测出来的事（2026-08-04，纯 curl 无 Cookie）：

        GET api.bilibili.com/x/v3/fav/resource/list?media_id=12&pn=1&ps=5
        → HTTP 200 → {"code":0,"message":"OK","ttl":1,"data":null}

    **HTTP 200、业务码 0、message "OK"、data 是 null。** 照常理写的解析器
    会拿到空列表并报告「同步成功，0 条」——用户读到「你没有收藏」，
    真相是「你没登录」。v0.0.0.6 生产上"永远是 0"就是这个形状。

    所以这里**永远不会**返回 `{"items": [], "ok": true}` 那种含糊的成功：
    要么给出条目，要么给出失败码 + 一句能照着做的中文。
    """
    platform = payload.platform.strip().lower()
    parser = PAYLOAD_PARSERS.get(platform)
    if parser is None:
        return {
            "ok": False,
            "platform": platform,
            "failure_code": "PLATFORM_PARSER_MISSING",
            # 用中文名。把 `xiaohongshu` 这种内部 id 甩给用户，
            # 是在让他读我们的代码。
            "message_zh": f"还没有写{PLATFORM_LABELS.get(platform, platform)}的响应解析，这一条读不了。",
            "items": [],
            "shape_recorded": _record_unreadable_shape(
                platform, payload.url, payload.body, "PLATFORM_PARSER_MISSING") or True,
        }
    try:
        items, has_more = parser(payload.body)
    except PayloadUnreadable as exc:
        # 形状变了也要留骨架——「以前读得懂、现在读不懂」正是最需要看结构的时候。
        _record_unreadable_shape(platform, payload.url, payload.body, exc.failure_code)
        return {
            "ok": False,
            "platform": platform,
            "failure_code": exc.failure_code,
            "message_zh": exc.message_zh,
            "items": [],
        }
    return {
        "ok": True,
        "platform": platform,
        "failure_code": None,
        "message_zh": f"读懂了 {len(items)} 条。",
        "has_more": has_more,
        "items": [asdict(item) for item in items],
    }


class DiagnosticReport(BaseModel):
    """诊断按钮抓到的**地址形态**——不含任何响应体。

    响应体留在浏览器的内存缓冲里，从不上传：它可能带着平台返回的个人信息，
    而要固化拦截前缀只需要地址。
    """

    platform: str
    page_url: str = ""
    urls: list[str] = Field(default_factory=list)
    capture_count: int = 0
    readable_count: int = 0
    # **少收下的、没去读的，都要有个数。**
    #
    # 拦截缓冲区会在 200 条封顶，解析前还会按地址去重并封顶 30 条。
    # 这两处收敛都是必要的（否则 Owner 那一按会卡几分钟），但收敛得
    # **不留痕迹**就危险了：报告上「抓到 200 条、读得懂 0 条」，
    # 到底是平台没发那个请求，还是那条被挤掉了 / 没轮到读？
    # 这两件事的下一步完全不同，而报告是我固化拦截前缀时唯一的依据。
    dropped_count: int = 0
    not_parsed_count: int = 0
    # **哪几条读得懂。** 只收地址，仍然不收响应体。
    #
    # 只报 readable_count 这个数字，等于报了「有三条能读」却不说是哪三条——
    # 而 T09（抓到即固化）要的恰恰是那个地址：拦截前缀就是从它身上取的。
    # Owner 只按一次诊断，报告里少了这一样，那一按就白按。
    readable_urls: list[str] = Field(default_factory=list)
    note: str = ""


@app.post("/v1/extension/diagnostics", dependencies=[Depends(require_token)])
def record_diagnostic(report: DiagnosticReport) -> dict[str, Any]:
    """把诊断结果落到自己的服务器上，省掉「你复制给我」这一步。

    ## 为什么

    国内平台的收藏接口地址只存在于 Owner 已登录的浏览器里。诊断按钮把它们
    抓出来显示在弹窗上，旁边一颗「复制」——**然后还要他把那段文字发给我**。

    Owner 的原话：「能你做的就别让我做 我没有技术基础」。让他复制粘贴
    一段技术文本，正是这句话要消掉的东西。落到他自己的服务器上之后，
    我直接去读，他点完那一下就完了。

    ## 边界

    · **只收地址与计数，不收响应体。** 模型里根本没有 body 字段。
    · 落的是 data_root 下的一个 JSONL，不进数据库——不改 schema，
      就不会有「带迁移的回滚」那种最危险的回滚。
    · 追加写，永不覆盖：诊断可能要跑好几次，每次都是一条记录。
    """
    # **不能写 data_root/evidence。** 那个目录在生产上是 root:socialarchive(980)
    # 2755，而 Core 跑在 uid 10001 / gid 10001——写不进去，实测 500 +
    # PermissionError。写 diagnostics/，它由 prepare_systemd_host.sh 用
    # `install -d -m 2770 -o 10001` 建出来，属主就是 Core 自己。
    target = settings.data_root / "diagnostics" / "extension-diagnostics.jsonl"
    line = json.dumps({
        "at": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
        "platform": report.platform.strip().lower(),
        "page_url": report.page_url.split("?")[0],
        "urls": report.urls[:80],
        "capture_count": report.capture_count,
        "readable_count": report.readable_count,
        "dropped_count": report.dropped_count,
        "not_parsed_count": report.not_parsed_count,
        "readable_urls": report.readable_urls[:20],
        "note": report.note[:300],
    }, ensure_ascii=False)
    # **写不进去不是 500。** 诊断上报是个锦上添花的便利；它挂掉不该给用户
    # 一串堆栈，而该告诉他还有复制按钮这条退路——弹窗里已经写好那句话了。
    # 第一版就是直接抛，实测在生产上 500（evidence/ 目录 Core 写不进）。
    try:
        target.parent.mkdir(parents=True, exist_ok=True)
        with target.open("a", encoding="utf-8") as handle:
            handle.write(line + "\n")
    except OSError as exc:
        return {
            "recorded": False,
            "failure_code": "DIAGNOSTIC_SINK_UNWRITABLE",
            "message_zh": "结果没能存到服务器（服务器上那个目录写不进去）。"
                          "请点弹窗里的「复制」，把内容发给开发者。",
            "detail": exc.__class__.__name__,
        }
    return {"recorded": True, "message_zh": "诊断结果已存到你自己的服务器，不需要你再复制给谁。"}


@app.get("/v1/extension/bootstrap", dependencies=[Depends(require_token)])
def extension_bootstrap() -> dict[str, Any]:
    """Single low-latency payload for popup/options/side-panel rendering."""
    connector_items = registry.health_views(store.connector_states())
    destination_items = destinations.views()
    jobs = store.list_jobs(limit=100)
    storage_items = store.quota_states()
    replicas = store.replica_summary()
    destination_receipts = store.list_destination_receipts(limit=30)
    privacy_facts = store.privacy_facts()
    connected_sources = sum(1 for item in connector_items if item["state"] == "healthy")
    connected_destinations = sum(1 for item in destination_items if item["state"] == "connected")
    return {
        "project": "Social Archive",
        "version": __version__,
        "endpoint": settings.public_base_url,
        "library_url": settings.public_library_url,
        "archive_defaults": ["L0", "L1", "L3"],
        "l2_enabled": settings.l2_enabled,
        "connectors": connector_items,
        "destinations": destination_items,
        "jobs": jobs,
        "destination_receipts": destination_receipts,
        "storage": {"items": storage_items, "replicas": replicas, "completion": store.replication_completion()},
        "summary": {
            "connected_sources": connected_sources,
            "connected_destinations": connected_destinations,
            "failed_exports": sum(1 for item in destination_receipts if item["status"] == "failed"),
            "needs_user_action": (
                sum(1 for job in jobs if job["status"] in {"retry", "failed"})
                + sum(1 for item in destination_items if item["state"] in {"needs_user_action", "degraded", "expired", "blocked_policy"})
            ),
        },
        "pairing": {
            "required": settings.pairing_required,
            "paired": bool(_expected_token()) if settings.pairing_required else True,
            "mode": "cloud_first" if settings.public_base_url.startswith("https://") else "local_development",
        },
        # 这一段此前是三个写死的字面量，其中 cookie_custody: False 从 T05/T06
        # 起就是**假的**——产品确实在托管西方三源的登录状态（加密后落库）。
        # 一个自称是隐私边界的字段说了假话，比没有这个字段更糟。
        # 现在全部改成算出来的，并且把「哪些托管、哪些绝不出浏览器」分开说清楚——
        # 那个区别本来就是这个产品的设计，不是需要含糊过去的东西。
        "privacy": {
            "cookie_custody": bool(CUSTODIAL_PLATFORMS),
            "cookie_custody_platforms": sorted(CUSTODIAL_PLATFORMS),
            "cookie_never_leaves_browser_platforms": sorted(DOMESTIC_PLATFORMS),
            # 不是「我们不存密码」这句自称，是「库里现在没有这种列」这个测量。
            "password_custody": bool(privacy_facts["password_shaped_columns"]),
            "password_shaped_columns": privacy_facts["password_shaped_columns"],
            # 取代原先的 user_triggered_capture_only: True。它不成立——
            # 连接过的账号会按周期自己跑。这里给的是数目，不是一句形容。
            "auto_sync_accounts": privacy_facts["auto_sync_accounts"],
        },
    }


def _artifact_mapping(captures: list[CaptureRequest], artifacts: list[dict[str, Any]]) -> dict[int, list[dict[str, Any]]]:
    mapping: dict[int, list[dict[str, Any]]] = {}
    if not artifacts or not captures:
        return mapping
    if len(captures) == 1:
        mapping[0] = artifacts
        return mapping
    for index, capture in enumerate(captures):
        key = capture.external_content_id
        if not key:
            continue
        matched = [item for item in artifacts if key in Path(str(item.get("path") or "")).name]
        if matched:
            mapping[index] = matched
    return mapping


@app.post("/v1/connectors/{connector_id}/run", status_code=202, dependencies=[Depends(require_token)])
def run_connector(connector_id: str, request: ConnectorRunRequest) -> dict[str, Any]:
    if request.cursor:
        raise HTTPException(status_code=422, detail="分页检查点仅由账号同步任务内部管理，不能从请求提交")
    started = time.perf_counter()
    try:
        result, captures = registry.run(connector_id, request)
        mapping = _artifact_mapping(captures, result.artifacts)
        responses: list[CaptureResponse] = []
        adopted_artifact_ids: list[str] = []
        for index, item in enumerate(captures):
            mapped = mapping.get(index, [])
            effective = item
            if mapped and "L3" in item.requested_levels:
                effective = item.model_copy(update={"requested_levels": [level for level in item.requested_levels if level != "L3"]})
            response = service.capture(effective)
            responses.append(response)
            if mapped and "L3" in item.requested_levels:
                adopted_artifact_ids.extend(service.attach_local_artifacts(response.content_id, mapped))

        receipt = dict(result.scan_receipt)
        relation_type = str(receipt.get("relation_type") or request.relation_type or "saved")
        collection_key = str(receipt.get("collection_key") or request.collection_key or "")
        source_account_id = str(receipt.get("source_account_id") or request.source_account_id or "") or None
        receipt_id = store.record_scan_receipt(connector_id, result.run_id, receipt, source_account_id=source_account_id, relation_type=relation_type)
        advanced_missing = 0
        if receipt.get("completeness") == "complete" and receipt.get("scope") == "account_relation":
            advanced_missing = store.apply_complete_scan(
                connector_id,
                {response.relation_id for response in responses},
                relation_type=relation_type,
                collection_key=collection_key,
                source_account_id=source_account_id,
            )
        state = "healthy" if result.status in {"success", "partial"} else ("blocked_environment" if result.status == "blocked_environment" else "degraded")
        store.upsert_connector_state(
            connector_id,
            state=state,
            policy_gate="pass",
            auth_gate="pass" if state == "healthy" else "unknown",
            technical_gate="pass" if state == "healthy" else "unknown",
            error_code=(result.errors[0].get("code") if result.errors else None),
            last_checked_at=utcnow(),
            latency_ms=max(0, round((time.perf_counter() - started) * 1000)),
            message_zh="最近一次读取完成。" if state == "healthy" else "最近一次读取未完成；请按下一步处理或使用保存当前页面。",
        )
        return {
            "connector_id": connector_id,
            "run_id": result.run_id,
            "status": result.status,
            "scan_receipt": receipt,
            "scan_receipt_id": receipt_id,
            "imported": len(responses),
            "adopted_artifact_count": len(adopted_artifact_ids),
            "advanced_missing_relation_count": advanced_missing,
            "content_ids": [response.content_id for response in responses],
            "errors": result.errors,
            "next_action_zh": "已进入资料库。" if responses else (result.errors[0].get("message") if result.errors else "没有读取到可导入内容；仍可使用浏览器扩展保存当前页面。"),
        }
    except (ValueError, OSError, PermissionError, RuntimeError) as exc:
        store.upsert_connector_state(
            connector_id,
            state="degraded",
            policy_gate="pass",
            auth_gate="unknown",
            technical_gate="unknown",
            # 稳定码；类名进 message，不当码用（见 test_failure_codes_are_never_python_class_names）
            error_code="DESTINATION_PROBE_FAILED",
            last_checked_at=utcnow(),
            latency_ms=max(0, round((time.perf_counter() - started) * 1000)),
            message_zh="本次读取失败；请检查配置或使用保存当前页面。",
        )
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@app.post("/v1/captures", response_model=CaptureResponse, status_code=202, dependencies=[Depends(require_token)])
def capture(request: CaptureRequest) -> CaptureResponse:
    try:
        return service.capture(request)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@app.post("/v1/captures/batch", status_code=202, dependencies=[Depends(require_token)])
def capture_batch(request: CaptureBatchRequest) -> dict[str, Any]:
    responses: list[CaptureResponse] = []
    errors: list[dict[str, Any]] = []
    for index, item in enumerate(request.items):
        try:
            responses.append(service.capture(item))
        except ValueError as exc:
            errors.append({"index": index, "detail": str(exc)})
    return {
        "accepted": len(responses),
        "failed": len(errors),
        "items": [item.model_dump(mode="json") for item in responses],
        "errors": errors,
    }


@app.post("/v1/import/markdown", dependencies=[Depends(require_token)])
def import_markdown(request: MarkdownImportRequest) -> dict[str, Any]:
    try:
        return service.import_markdown(request)
    except (ValueError, OSError) as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@app.post("/v1/import/data-export", dependencies=[Depends(require_token)])
async def import_data_export(
    request: Request,
    platform_hint: str = Query(default="import", min_length=1, max_length=64),
    relation_type: str = Query(default="saved"),
    limit: int = Query(default=5000, ge=1, le=20000),
    # 文件名只用来在回执里叫得出它的名字，以及区分"压缩包 / 单个清单文件"。
    x_archive_filename: str = Header(default=""),
) -> dict[str, Any]:
    """读平台官方的「下载我的数据」压缩包。

    Owner 的平台表里 Instagram 与 X 的主路径就含「官方导出导入」——
    那是平台自己给的完整数据，不会因为接口改版而坏。

    **回执里每个文件都有一行**：读懂了几条、没读懂为什么。
    只报总数的话，「另外 30 个文件没看懂」就消失了。
    """
    content_length = request.headers.get("content-length")
    if content_length and int(content_length) > 500 * 1024 * 1024:
        raise HTTPException(status_code=413, detail="导出包超过 500 MiB")
    payload = await request.body()
    # **不是压缩包也要能读。** bilibili-cli 这类工具吐的是一个裸的
    # JSON/YAML 清单文件，而 Owner 的项目表里它的角色正是「JSON/YAML 导入」。
    read = read_export_archive(payload, limit=limit, filename=x_archive_filename[:180])
    if not read.get("ok"):
        raise HTTPException(status_code=422, detail=read.get("error") or "读不出这个包")
    captured, errors = [], []
    for record in read["items"]:
        try:
            captured.append(service.capture(CaptureRequest(
                platform=platform_hint,
                url=record["url"],
                title=record.get("title") or None,
                relation_type=relation_type,
                relation_observed_at=None,
            )).content_id)
        except (ValueError, OSError) as exc:
            errors.append({"url": record.get("url"), "code": "ITEM_INGEST_FAILED",
                           "message": f"{exc.__class__.__name__}: {exc}"[:300]})
    return {
        "imported": len(captured),
        "read": read["counted"],
        "file_count": read["file_count"],
        # **每个文件都留一行**，好让「有 30 个文件没看懂」说得出来
        "files": read["files"],
        "errors": errors,
    }


@app.post("/v1/import/social-archiver", dependencies=[Depends(require_token)])
async def import_social_archiver(
    request: Request,
    x_archive_filename: str = Header(default="social-archiver-export.zip"),
    platform_hint: str = Query(default="import", min_length=1, max_length=64),
    relation_type: str = Query(default="saved"),
    limit: int = Query(default=1000, ge=1, le=10000),
) -> dict[str, Any]:
    content_length = request.headers.get("content-length")
    if content_length and int(content_length) > 200 * 1024 * 1024:
        raise HTTPException(status_code=413, detail="导入包超过 200 MiB")
    payload = await request.body()
    try:
        return service.import_social_archiver_bundle(
            payload,
            filename=Path(x_archive_filename).name,
            platform_hint=platform_hint,
            relation_type=relation_type,
            limit=limit,
        )
    except (ValueError, OSError) as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@app.get("/v1/jobs", dependencies=[Depends(require_token)])
def jobs(limit: int = Query(100, ge=1, le=500), status_filter: str | None = Query(default=None, alias="status")) -> dict[str, Any]:
    return {"items": store.list_jobs(limit=limit, status=status_filter)}


@app.get("/v1/jobs/{job_id}", response_model=JobView, dependencies=[Depends(require_token)])
def get_job(job_id: str) -> dict[str, Any]:
    row = store.get_job(job_id)
    if not row:
        raise HTTPException(status_code=404, detail="任务不存在")
    return row


@app.post("/v1/jobs/{job_id}/retry", dependencies=[Depends(require_token)])
def retry_job(job_id: str) -> dict[str, Any]:
    row = store.get_job(job_id)
    if not row:
        raise HTTPException(status_code=404, detail="任务不存在")
    if row["status"] in {"queued", "running", "done"}:
        raise HTTPException(status_code=409, detail="当前任务已在队列中、正在处理或已经完成，不能重试")
    if not store.retry_job(job_id):
        raise HTTPException(status_code=409, detail="任务状态已变化，请刷新后重试")
    return {"job_id": job_id, "status": "queued", "message_zh": "已重新加入队列"}


@app.get("/v1/destinations", dependencies=[Depends(require_token)])
def destination_status() -> dict[str, Any]:
    return {"items": destinations.views()}


@app.post("/v1/destinations/{destination_id}/probe", dependencies=[Depends(require_token)])
def probe_destination(destination_id: str) -> dict[str, Any]:
    try:
        return destinations.probe(destination_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@app.post("/v1/destinations/{destination_id}/backfill", status_code=202, dependencies=[Depends(require_token)])
def backfill_destination(destination_id: str) -> dict[str, Any]:
    """把**已经在库里、却还没送到这个目的地**的内容补投一遍。

    2026-08-05 打生产量出来的：Owner 连上 GitHub 与 Obsidian 之后，两边各只有
    1 / 193 条。不是坏了——投递只在**新内容进来时**发生，他后来才连上，
    此前入库的不会自己追上去。而在他那一侧，「我连上了 GitHub，我的档案
    应该都在那儿」是最自然的期待。

    在这个接口之前，把 192 条补上去的唯一办法是**在界面上逐条点 192 次**，
    或者让我登进服务器敲命令——两条都不该是他要走的路。

    · 只给**已经授权过导出**的目的地补投（「界面上选了它」≠「授权往那里写」）。
    · 入队的是与单条导出**完全相同**的作业，不另开一条只有补投才走的路。
    · 作业 id 是稳定哈希 + INSERT OR IGNORE，重复点不会重复投。
    · **入队不等于送到**：返回里说清这一点，覆盖数要等 worker 跑完才会变。
    """
    destination_id = destination_id.strip().lower()
    if destination_id not in destinations.known_ids():
        raise HTTPException(status_code=404, detail="目的地不存在")
    if not destinations.is_export_authorized(destination_id):
        raise HTTPException(status_code=409,
                            detail="这个目的地还没有一次成功的写入授权，先在连接向导里完成一次真实写入。")
    missing = store.content_ids_missing_from_destination(destination_id)
    for content_id in missing:
        store.enqueue_job("export_destination",
                          {"content_id": content_id, "destination_id": destination_id},
                          connector_id=destination_id)
    return {
        "destination_id": destination_id,
        "enqueued": len(missing),
        "message_zh": (f"已排队 {len(missing)} 条。排队不等于送到——"
                       "它们会一条条送过去，过一会儿回来看这里的「已送到」数字。")
        if missing else "这里已经是齐的，没有需要补的。",
    }


@app.get("/v1/destinations/receipts", dependencies=[Depends(require_token)])
def destination_receipts(
    limit: int = Query(default=100, ge=1, le=500),
    destination_id: str | None = Query(default=None),
    content_id: str | None = Query(default=None),
    status_filter: str | None = Query(default=None, alias="status"),
) -> dict[str, Any]:
    return {
        "items": store.list_destination_receipts(
            limit=limit,
            destination_id=destination_id,
            content_id=content_id,
            status=status_filter,
        )
    }


@app.post("/v1/destinations/receipts/{receipt_id}/retry", status_code=202, dependencies=[Depends(require_token)])
def retry_destination_receipt(receipt_id: str) -> dict[str, Any]:
    receipt = store.get_destination_receipt(receipt_id)
    if not receipt:
        raise HTTPException(status_code=404, detail="目的地回执不存在")
    if receipt["status"] != "failed":
        raise HTTPException(status_code=409, detail="该回执不处于失败状态，无需重试")
    if receipt["destination_id"] != "social_archive" and not destinations.is_export_authorized(receipt["destination_id"], allow_recovery=True):
        raise HTTPException(status_code=409, detail="目的地尚未完成主动连接检查或授权已失效；请先检查连接后再重试")
    job_id = str(receipt.get("job_id") or "")
    if job_id:
        job = store.get_job(job_id)
        if job:
            if job["status"] in {"queued", "running"}:
                return {"job_id": job_id, "status": job["status"], "message_zh": "该目的地任务已在处理中。"}
            if job["status"] == "done":
                raise HTTPException(status_code=409, detail="该目的地任务已经完成，请刷新回执")
            if store.retry_job(job_id):
                return {"job_id": job_id, "status": "queued", "message_zh": "已重新加入目的地导出队列"}
    replacement_id = store.enqueue_job(
        "export_destination",
        {"content_id": receipt["content_id"], "destination_id": receipt["destination_id"]},
        connector_id=receipt["destination_id"],
    )
    replacement = store.get_job(replacement_id)
    if not replacement:
        raise HTTPException(status_code=409, detail="无法创建目的地重试任务，请刷新后重试")
    if replacement["status"] in {"queued", "running"}:
        return {"job_id": replacement_id, "status": replacement["status"], "message_zh": "该目的地任务已在处理中。"}
    if replacement["status"] == "done":
        raise HTTPException(status_code=409, detail="该目的地任务已经完成，请刷新回执")
    if not store.retry_job(replacement_id):
        raise HTTPException(status_code=409, detail="任务状态已变化，请刷新后重试")
    return {"job_id": replacement_id, "status": "queued", "message_zh": "已重新加入目的地导出队列"}


@app.post("/v1/destinations/obsidian-local/receipts", status_code=202, dependencies=[Depends(require_token)])
def record_local_obsidian_receipt(request: LocalObsidianReceiptRequest) -> dict[str, Any]:
    """Persist a paired Chrome-to-loopback Obsidian projection receipt.

    The API cannot itself inspect a user's local Vault.  It records a bounded,
    paired-client attestation without mixing this target with server-side Obsidian
    Vault/REST bindings, which may refer to a different Vault entirely.
    """
    content = store.get_content(request.content_id)
    if not content:
        raise HTTPException(status_code=404, detail="内容不存在")
    remote_path = _safe_local_obsidian_path(request.remote_path)
    if request.status in {"done", "noop"} and not remote_path:
        raise HTTPException(status_code=422, detail="成功的 Obsidian 本机回执必须包含目标路径")
    projection_sha256 = sha256_bytes(_markdown(content).encode("utf-8"))
    destination_id = "obsidian_local"
    attempted_at = utcnow()
    remote_id = request.content_id if remote_path else None
    if request.status in {"done", "noop"}:
        store.upsert_destination_binding(
            destination_id=destination_id,
            content_id=request.content_id,
            projection_sha256=projection_sha256,
            remote_id=remote_id,
            remote_path=remote_path,
            metadata={"mode": "chrome_loopback", "attested": True},
        )
    message_zh = {
        "done": "Obsidian 本机桥接已写入并回传回执。",
        "noop": "Obsidian 本机桥接内容未变化，未重复写入。",
        "failed": "Obsidian 本机桥接失败；请打开 Obsidian 后在扩展任务中心重试。",
    }[request.status]
    receipt_id = store.record_destination_receipt(
        destination_id=destination_id,
        content_id=request.content_id,
        status=request.status,
        projection_sha256=projection_sha256,
        attempted_at=attempted_at,
        message_zh=message_zh,
        remote_id=remote_id,
        remote_path=remote_path,
        error_code="OBSIDIAN_LOCAL_BRIDGE_FAILED" if request.status == "failed" else None,
        evidence={
            "attested": True,
            "bridge": "chrome_loopback",
            "retryable": request.status == "failed",
        },
    )
    return {
        "receipt_id": receipt_id,
        "content_id": request.content_id,
        "destination_id": destination_id,
        "status": request.status,
        "retryable": request.status == "failed",
    }


@app.post("/v1/library/{content_id}/export", status_code=202, dependencies=[Depends(require_token)])
def export_content(content_id: str, request: ExportRequest) -> dict[str, Any]:
    if not store.get_content(content_id):
        raise HTTPException(404, "内容不存在")
    allowed = set(destinations.known_destination_ids())
    requested_ids = list(dict.fromkeys(item.lower() for item in request.destination_ids if item.lower() in allowed and item.lower() != "social_archive"))
    ids = [destination_id for destination_id in requested_ids if destinations.is_export_authorized(destination_id)]
    skipped_destination_ids = [destination_id for destination_id in requested_ids if destination_id not in ids]
    job_ids = [store.enqueue_job("export_destination", {"content_id": content_id, "destination_id": destination_id}, connector_id=destination_id) for destination_id in ids]
    return {
        "content_id": content_id,
        "destination_ids": ids,
        "skipped_destination_ids": skipped_destination_ids,
        "job_ids": job_ids,
    }


@app.post("/v1/library/classify", dependencies=[Depends(require_token)])
def classify_library_items(request: ClassifyRequest) -> dict[str, Any]:
    """把选中的内容改成同一个主题与关键词。

    **这条路由此前不存在。** 界面上「批量修改分类」那颗按钮一直在调它，
    实测回的是 405——按下去从来没成功过一次。

    报数分两个：`requested` 是他点名了几条，`updated` 是真的改了几条。
    **两者不一样时要说出来**——选中的内容里若有已经不在库里的，
    报一句「都改好了」就是又一次「看着成了」。
    """
    result = store.reclassify_content(
        request.content_ids, topic=request.topic, keywords=request.keywords)
    if not result["updated"]:
        raise HTTPException(404, "选中的内容都不在库里，没有改动任何一条。")
    result["message_zh"] = (
        f"已把 {result['updated']} 条改成「{result['topic']}」。"
        if not result["missing"] else
        f"已把 {result['updated']} 条改成「{result['topic']}」；"
        f"另有 {len(result['missing'])} 条不在库里，没有改动。"
    )
    return result


@app.get("/v1/library/{content_id}/markdown", dependencies=[Depends(require_token)])
def export_markdown(content_id: str) -> PlainTextResponse:
    content = store.get_content(content_id)
    if not content:
        raise HTTPException(404, "内容不存在")
    return PlainTextResponse(_markdown(content), media_type="text/markdown; charset=utf-8")


@app.get("/v1/library", dependencies=[Depends(require_token)])
def library(
    q: str | None = None,
    platform: str | None = None,
    relation: str | None = None,
    topic: str | None = None,
    collection: str | None = None,
    archive_status: str | None = Query(default=None, alias="archive"),
    after: str | None = Query(default=None),
    observed_from: str | None = None,
    observed_to: str | None = None,
    sort_by: str = Query(default="time"),
    sort_dir: str = Query(default="desc", pattern="^(asc|desc)$"),
    limit: int = Query(100, ge=1, le=500),
    offset: int = Query(0, ge=0),
) -> dict[str, Any]:
    start = _observed_bound(observed_from, end_of_day=False)
    end = _observed_bound(observed_to, end_of_day=True)
    if start and end and start > end:
        raise HTTPException(status_code=422, detail="开始时间不得晚于结束时间")
    return store.list_library_table(
        q=q,
        platform=platform,
        relation=relation,
        topic=topic,
        collection=collection,
        archive_status=archive_status,
        after=after,
        observed_from=start,
        observed_to=end,
        sort_by=sort_by,
        sort_dir=sort_dir,
        limit=limit,
        offset=offset,
    )


@app.get("/v1/search", dependencies=[Depends(require_token)])
def search(q: str = Query(min_length=1), limit: int = Query(100, ge=1, le=500)) -> dict[str, Any]:
    return {"items": store.list_library(q=q, limit=limit)}


# **这条必须排在 `/v1/library/{content_id}` 前面。**（2026-08-10）
# FastAPI 按注册顺序匹配：放在后面时 `markdown.zip` 会被当成一个 content_id，
# 那颗按钮点下去是 404。**判据先跑出来的，不是读代码看出来的。**
@app.get("/v1/library/markdown.zip", dependencies=[Depends(require_token)])
def download_all_markdown() -> Response:
    """把已经导出的 Markdown 打成一个包给他。（2026-08-10）

    ## 为什么加这个

    Owner 的原话：「zzybrim/douyin-obsidian 别人已经开发成功了，
    你跑了十天了，还没有结果」。**他说得对。**

    去看他的实况：`markdown` 目的地 **193/193**——他那 193 条
    （含 86 条抖音）**早在 8 月 3 号就全部生成成 Markdown 了**，
    带 frontmatter、原始链接、正文，一直躺在服务器的 exports/markdown 下。

    而 `obsidian` 是 **1/193**，并且那个「Obsidian 库」是**服务器上的一个目录**
    （`SOCIAL_ARCHIVE_OBSIDIAN_REST_URL` 是空的）——**没有任何一条路通到他电脑上
    的 Obsidian**。所以界面上「Obsidian 已连接」是假的，那颗「把没送过去的 192 条
    补上」按钮就算点了，也只是在一台他从不打开的目录里多 192 个文件。

    对比那个项目赢在哪：**它写进用户自己的库**。

    浏览器写不了任意本地路径，服务器也够不着他的电脑——**能走通的那条路是
    「让他下载，自己拖进库里」**。这个接口就是那条路：一次点击拿到全部，
    解压后整个文件夹拖进 Obsidian 即可，不用装任何东西。

    ## 边界

    · 打的是**已经导出的那些**（markdown 目的地的产物），不是现算。
      所以包里有多少条，取决于那个目的地送到了多少——数字随包一起给出，
      不让他以为「下载了就是全部」。
    · 只读 exports/markdown，不写任何东西。
    """
    root = settings.export_root / "markdown"
    if not root.is_dir():
        raise HTTPException(status_code=503,
                            detail="还没有生成过 Markdown。到左边「自动导出」那一栏，找到 Markdown 那张卡片，先点「检查连接」；连上之后卡片上会出现「把没送过去的 N 条补上」，点它，再回来点这颗按钮就有了。")
    files = sorted(path for path in root.rglob("*.md") if path.is_file())
    if not files:
        raise HTTPException(status_code=503,
                            detail="Markdown 目录是空的——先让「Markdown」那个导出目的地跑一次")
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9) as archive:
        for path in files:
            archive.write(path, arcname=str(path.relative_to(root)))
    payload = buffer.getvalue()
    return Response(
        content=payload,
        media_type="application/zip",
        headers={
            "Content-Disposition": 'attachment; filename="social-archive-markdown.zip"',
            # **把条数说出来**：他要知道这一包是不是全部。
            "X-Markdown-File-Count": str(len(files)),
        },
    )


@app.get("/v1/library/{content_id}", dependencies=[Depends(require_token)])
def detail(content_id: str) -> dict[str, Any]:
    row = store.get_content(content_id)
    if not row:
        raise HTTPException(status_code=404, detail="内容不存在")
    return row


@app.get("/v1/storage/status", dependencies=[Depends(require_token)])
def storage_status() -> dict[str, Any]:
    decision = service.quota.evaluate_local_staging()
    return {"items": store.quota_states(), "replicas": store.replica_summary(), "completion": store.replication_completion(), "l3_allowed": decision.allow_l3, "message_zh": decision.message_zh}


@app.get("/v1/status-projection", dependencies=[Depends(require_token)])
def status_projection() -> dict[str, Any]:
    connector_items = registry.health_views(store.connector_states())
    # **「还没做到」不是「坏了」。**
    #
    # 2026-08-05 打生产量出来的：9 个连接器里 8 个是 blocked_environment
    # （x/reddit/instagram/tiktok/小红书/抖音/快手/B站——全是**能力声明**里
    # 写着本版本还不能自动读取的），唯一能工作的 generic-web 是 healthy。
    # 于是 overall 恒为 degraded，**永远不可能变成 healthy**。
    #
    # 一盏永远红着的灯，教会人不再看这盏灯。而它还报错了事实：
    # 那 8 个不是出了故障，是这一版本就没打算支持——那是已知状态，不是异常。
    #
    # 所以只对**本该工作的**那些判健康。被声明为「还不能」的不计入，
    # 但**它们的条数要报出来**，不能让「全绿」把「大部分还没做」盖掉。
    countable = [item for item in connector_items if item["state"] != "blocked_environment"]
    not_yet_supported = len(connector_items) - len(countable)
    if not countable:
        # 一个本该工作的都没有，就绝不报健康——那才是真的静默的零。
        overall = "degraded"
    elif all(item["state"] == "healthy" for item in countable):
        overall = "healthy"
    else:
        overall = "degraded"
    return {
        "project": "Social Archive",
        "version": __version__,
        "generated_at": utcnow(),
        "overall": overall,
        "not_yet_supported": not_yet_supported,
        "connectors": connector_items,
        "destinations": destinations.views(),
        "storage": store.quota_states(),
        "replicas": store.replica_summary(),
        # `last_backup` 曾经写死成 "unknown"（2026-08-11 那次事故的记录里点过名）。
        # **写死的 "unknown" 比空着更坏**：它长得像"查过了，不知道"，
        # 其实是"根本没去查"。现在它读的是真产物——最近那份做完的快照。
        # `last_restore_drill` 还是 unknown，因为**确实没有任何东西在记它**；
        # 保留原样，不拿一个编出来的值填上去。
        "recovery": {
            "last_backup": _backup_liveness().get("last_backup_at") or "unknown",
            "last_restore_drill": "unknown",
        },
    }


pwa_root = settings.pwa_root
extension_package = Path(
    os.getenv(
        "SOCIAL_ARCHIVE_EXTENSION_PACKAGE",
        str(Path(__file__).resolve().parents[2] / "dist" / "social-archive-extension.zip"),
    )
).resolve()


@app.get("/downloads/social-archive-extension.zip")
def download_browser_extension() -> FileResponse:
    if not extension_package.is_file():
        raise HTTPException(status_code=503, detail="浏览器插件安装包尚未生成，请稍后重试")
    payload = extension_package.read_bytes()
    return FileResponse(
        extension_package,
        media_type="application/zip",
        filename=f"social-archive-extension-v{__version__}.zip",
        headers={
            "Cache-Control": "private, max-age=3600",
            "X-Social-Archive-SHA256": sha256_bytes(payload),
        },
    )


if pwa_root.exists():
    app.mount("/assets", StaticFiles(directory=pwa_root), name="assets")

    @app.get("/")
    def pwa_index() -> FileResponse:
        return FileResponse(pwa_root / "index.html")

    @app.get("/extension-install")
    def extension_install_guide() -> FileResponse:
        return FileResponse(pwa_root / "extension-install.html")

    @app.get("/guide")
    def usage_guide() -> FileResponse:
        """完整使用说明。

        **在这条路由之前，这份说明他打不开。** 它一直躺在 git 工作树里
        （`docs/使用说明.md`），有判据核着它每一步在产品里真的存在，
        而产品里没有任何入口指向它——于是每次他要装、要连，
        都是我在聊天里现敲一遍步骤。**那不叫使用说明，那叫我记得。**

        这一页由 `scripts/build_guide_page.py` 从那份 md 生成，
        发布门里 `--check` 挡住「改了 md 忘了重生成」。
        """
        return FileResponse(pwa_root / "guide.html")

    @app.get("/item/{content_id}")
    def pwa_item(content_id: str) -> FileResponse:
        return FileResponse(pwa_root / "index.html")


def run() -> None:
    uvicorn.run("social_archive.api:app", host=settings.host, port=settings.port, log_level=settings.log_level.lower(), proxy_headers=True)


if __name__ == "__main__":
    run()
