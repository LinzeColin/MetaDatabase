
from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


def _bool(name: str, default: bool) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


def _float(name: str, default: float) -> float:
    try:
        return float(os.getenv(name, str(default)))
    except ValueError as exc:
        raise ValueError(f"{name} 必须是数字") from exc


@dataclass(frozen=True)
class Settings:
    env: str
    host: str
    port: int
    data_root: Path
    runtime_db: Path
    staging_root: Path
    # Legacy compatibility value only. Runtime must never create, mount, clone,
    # or write this path; durable facts use SOCIAL_ARCHIVE_PRIVATE_DB_CLIENT.
    private_database_root: Path
    pwa_root: Path
    watch_root: Path
    export_root: Path
    log_level: str
    paid_api_allowed: bool
    l2_enabled: bool
    l3_enabled: bool
    r2_soft_bytes: int
    r2_hard_bytes: int
    oci_soft_bytes: int
    oci_hard_bytes: int
    github_release_soft_bytes: int
    github_release_hard_bytes: int
    max_download_bytes: int
    worker_poll_seconds: float
    xhs_worker_url: str
    douk_worker_url: str
    ks_worker_url: str
    cli_worker_url: str
    cli_worker_token_file: str | None
    cli_output_root: Path
    public_base_url: str = "http://127.0.0.1:8765"
    public_library_url: str = "http://127.0.0.1:8765"
    api_token_file: str | None = None
    # 注意：pairing_required 名字里带 pairing，但它是**总鉴权开关**——
    # require_token 第一行据此早退。旧的一次性码链路已随 v0.0.0.7/T03 删除，
    # 这个字段与那条链路无关，删掉等于全站不再鉴权。
    pairing_required: bool = False
    # **不要求交互式登录**（2026-08-17）。
    #
    # 起因：`social-archive.linzezhang.com` 被 Cloudflare Access 挡着，而 OAuth 的
    # redirect_uri 与 login_base 都钉在那个域名上——于是登录只能在一个进不去的
    # 地方完成，令牌又只能由登录签发：死结。Owner 三个星期打不开自己的档案馆。
    #
    # 开启后：`/v1/auth/me` 与 `/v1/auth/extension-token` 认 Owner，不要会话；
    # `/v1/auth/providers` 返回空表，前端那屏登录不再出现。
    #
    # **代价要说清楚**：这一档下，知道网址的人就能取到 Owner 令牌。
    # 它是为「先让功能能用」准备的，不是长期形态；要恢复登录把这个变量拿掉即可。
    login_required: bool = True
    notion_token_file: str | None = None
    notion_database_id: str | None = None
    notion_data_source_id: str | None = None
    notion_api_version: str = "2026-03-11"
    obsidian_vault_root: Path | None = None
    obsidian_rest_url: str | None = None
    obsidian_rest_token_file: str | None = None
    obsidian_rest_ca_file: str | None = None
    github_repository: str | None = None
    github_archive_repository: str | None = None
    github_token_file: str | None = None
    github_markdown_branch: str = "main"
    age_recipient: str | None = None
    age_identity_file: str | None = None
    # 凭据用的是**另一对**密钥，不复用上面那对（v0.0.0.7 / T05+T06）。
    #
    # 上面那对是三副本备份通道的：日常只需要公钥加密，私钥「仅在明确的恢复演练
    # 时读取」（encryption.py 的原话），因此它留在宿主机、不进容器。
    #
    # 而托管的平台 Cookie 必须能被 Core 解回来喂给 gallery-dl，也就是说
    # 那把私钥得进容器、且常驻在一个 24 小时联网的进程里。
    # 把备份私钥拿去干这件事，等于把「备份通道只有公钥」这条性质悄悄作废——
    # 一旦 Core 被攻破，攻击者拿到的就不只是当前凭据，而是**全部历史备份**。
    #
    # 所以分成两对。T05 当时把 CredentialVault 与 AgeEncryptor 分了类，
    # 却仍然共用同一个 identity 设置——那是分了一半，本次补齐。
    credential_age_recipient: str | None = None
    credential_age_identity_file: str | None = None
    karakeep_url: str | None = None
    karakeep_token_file: str | None = None
    linkwarden_url: str | None = None
    linkwarden_token_file: str | None = None
    account_sync_default_interval_minutes: int = 360
    account_sync_page_size: int = 100
    account_sync_max_items_per_run: int = 100000
    # 登录（v0.0.0.7 / T02）。client_id 不是密钥，走环境变量；
    # client_secret 只从 systemd credential 文件读，不进仓、不进 .env。
    google_client_id: str | None = None
    google_client_secret_file: str | None = None
    github_client_id: str | None = None
    github_client_secret_file: str | None = None

    @classmethod
    def from_env(cls) -> "Settings":
        data_root = Path(os.getenv("SOCIAL_ARCHIVE_DATA_ROOT", "/var/lib/social-archive")).resolve()
        gib = 1024 ** 3
        mib = 1024 ** 2
        obsidian_root = os.getenv("SOCIAL_ARCHIVE_OBSIDIAN_VAULT_ROOT", "").strip()
        return cls(
            env=os.getenv("SOCIAL_ARCHIVE_ENV", "development"),
            host=os.getenv("SOCIAL_ARCHIVE_HOST", "127.0.0.1"),
            port=int(os.getenv("SOCIAL_ARCHIVE_PORT", "8765")),
            data_root=data_root,
            runtime_db=Path(os.getenv("SOCIAL_ARCHIVE_RUNTIME_DB", str(data_root / "runtime/social-archive.sqlite3"))).resolve(),
            staging_root=Path(os.getenv("SOCIAL_ARCHIVE_STAGING_ROOT", str(data_root / "staging"))).resolve(),
            private_database_root=Path(os.getenv("SOCIAL_ARCHIVE_PRIVATE_DATABASE_ROOT", str(data_root / "private-database"))).resolve(),
            pwa_root=Path(os.getenv("SOCIAL_ARCHIVE_PWA_ROOT", "apps/pwa")).resolve(),
            watch_root=Path(os.getenv("SOCIAL_ARCHIVE_WATCH_ROOT", str(data_root / "import"))).resolve(),
            export_root=Path(os.getenv("SOCIAL_ARCHIVE_EXPORT_ROOT", str(data_root / "exports"))).resolve(),
            log_level=os.getenv("SOCIAL_ARCHIVE_LOG_LEVEL", "INFO"),
            paid_api_allowed=_bool("SOCIAL_ARCHIVE_PAID_API_ALLOWED", False),
            l2_enabled=_bool("SOCIAL_ARCHIVE_L2_ENABLED", False),
            l3_enabled=_bool("SOCIAL_ARCHIVE_L3_ENABLED", True),
            r2_soft_bytes=int(_float("SOCIAL_ARCHIVE_R2_SOFT_GIB", 8.0) * gib),
            r2_hard_bytes=int(_float("SOCIAL_ARCHIVE_R2_HARD_GIB", 9.25) * gib),
            oci_soft_bytes=int(_float("SOCIAL_ARCHIVE_OCI_SOFT_GIB", 16.0) * gib),
            oci_hard_bytes=int(_float("SOCIAL_ARCHIVE_OCI_HARD_GIB", 19.0) * gib),
            github_release_soft_bytes=int(_float("SOCIAL_ARCHIVE_GITHUB_RELEASE_SOFT_GIB", 8.0) * gib),
            github_release_hard_bytes=int(_float("SOCIAL_ARCHIVE_GITHUB_RELEASE_HARD_GIB", 9.25) * gib),
            max_download_bytes=int(_float("SOCIAL_ARCHIVE_MAX_DOWNLOAD_MIB", 1800) * mib),
            worker_poll_seconds=_float("SOCIAL_ARCHIVE_WORKER_POLL_SECONDS", 2.0),
            xhs_worker_url=os.getenv("SOCIAL_ARCHIVE_XHS_WORKER_URL", "http://127.0.0.1:5556"),
            douk_worker_url=os.getenv("SOCIAL_ARCHIVE_DOUK_WORKER_URL", "http://127.0.0.1:5555"),
            ks_worker_url=os.getenv("SOCIAL_ARCHIVE_KS_WORKER_URL", "http://127.0.0.1:5557"),
            cli_worker_url=os.getenv("SOCIAL_ARCHIVE_CLI_WORKER_URL", "").rstrip("/"),
            cli_worker_token_file=os.getenv("SOCIAL_ARCHIVE_CLI_WORKER_TOKEN_FILE") or None,
            cli_output_root=Path(os.getenv("SOCIAL_ARCHIVE_CLI_OUTPUT_ROOT", str(data_root / "vendor-output/cli"))).resolve(),
            public_base_url=(os.getenv("SOCIAL_ARCHIVE_PUBLIC_BASE_URL", "").strip() or "http://127.0.0.1:8765").rstrip("/"),
            public_library_url=(os.getenv("SOCIAL_ARCHIVE_PUBLIC_LIBRARY_URL", "").strip() or os.getenv("SOCIAL_ARCHIVE_PUBLIC_BASE_URL", "").strip() or "http://127.0.0.1:8765").rstrip("/"),
            api_token_file=os.getenv("SOCIAL_ARCHIVE_API_TOKEN_FILE") or None,
            pairing_required=_bool("SOCIAL_ARCHIVE_PAIRING_REQUIRED", False),
            login_required=_bool("SOCIAL_ARCHIVE_LOGIN_REQUIRED", True),
            notion_token_file=os.getenv("SOCIAL_ARCHIVE_NOTION_TOKEN_FILE") or None,
            notion_database_id=os.getenv("SOCIAL_ARCHIVE_NOTION_DATABASE_ID") or None,
            notion_data_source_id=os.getenv("SOCIAL_ARCHIVE_NOTION_DATA_SOURCE_ID") or None,
            notion_api_version=os.getenv("SOCIAL_ARCHIVE_NOTION_API_VERSION", "2026-03-11"),
            obsidian_vault_root=Path(obsidian_root).expanduser().resolve() if obsidian_root else None,
            obsidian_rest_url=os.getenv("SOCIAL_ARCHIVE_OBSIDIAN_REST_URL") or None,
            obsidian_rest_token_file=os.getenv("SOCIAL_ARCHIVE_OBSIDIAN_REST_TOKEN_FILE") or None,
            obsidian_rest_ca_file=os.getenv("SOCIAL_ARCHIVE_OBSIDIAN_REST_CA_FILE") or None,
            github_repository=os.getenv("SOCIAL_ARCHIVE_GITHUB_MARKDOWN_REPOSITORY") or None,
            github_archive_repository=os.getenv("SOCIAL_ARCHIVE_GITHUB_ARCHIVE_REPOSITORY") or None,
            github_token_file=os.getenv("SOCIAL_ARCHIVE_GITHUB_TOKEN_FILE") or None,
            github_markdown_branch=os.getenv("SOCIAL_ARCHIVE_GITHUB_MARKDOWN_BRANCH", "main"),
            age_recipient=os.getenv("SOCIAL_ARCHIVE_AGE_RECIPIENT") or None,
            age_identity_file=os.getenv("SOCIAL_ARCHIVE_AGE_IDENTITY_FILE") or None,
            credential_age_recipient=os.getenv("SOCIAL_ARCHIVE_CREDENTIAL_AGE_RECIPIENT") or None,
            credential_age_identity_file=os.getenv("SOCIAL_ARCHIVE_CREDENTIAL_AGE_IDENTITY_FILE") or None,
            karakeep_url=(os.getenv("SOCIAL_ARCHIVE_KARAKEEP_URL") or "").rstrip("/") or None,
            karakeep_token_file=os.getenv("SOCIAL_ARCHIVE_KARAKEEP_TOKEN_FILE") or None,
            linkwarden_url=(os.getenv("SOCIAL_ARCHIVE_LINKWARDEN_URL") or "").rstrip("/") or None,
            linkwarden_token_file=os.getenv("SOCIAL_ARCHIVE_LINKWARDEN_TOKEN_FILE") or None,
            google_client_id=os.getenv("SOCIAL_ARCHIVE_GOOGLE_CLIENT_ID") or None,
            google_client_secret_file=os.getenv("SOCIAL_ARCHIVE_GOOGLE_CLIENT_SECRET_FILE") or None,
            github_client_id=os.getenv("SOCIAL_ARCHIVE_GITHUB_CLIENT_ID") or None,
            github_client_secret_file=os.getenv("SOCIAL_ARCHIVE_GITHUB_CLIENT_SECRET_FILE") or None,
            account_sync_default_interval_minutes=int(os.getenv("SOCIAL_ARCHIVE_ACCOUNT_SYNC_INTERVAL_MINUTES", "360")),
            account_sync_page_size=int(os.getenv("SOCIAL_ARCHIVE_ACCOUNT_SYNC_PAGE_SIZE", "100")),
            account_sync_max_items_per_run=int(os.getenv("SOCIAL_ARCHIVE_ACCOUNT_SYNC_MAX_ITEMS", "100000")),
        )

    def ensure_directories(self, *, require_api_token: bool = False) -> None:
        for path in (
            self.data_root,
            self.runtime_db.parent,
            self.staging_root,
            self.watch_root,
            self.export_root,
            self.cli_output_root,
        ):
            path.mkdir(parents=True, exist_ok=True)
        if self.obsidian_vault_root:
            self.obsidian_vault_root.mkdir(parents=True, exist_ok=True)
        if self.paid_api_allowed:
            raise RuntimeError("零费用合同禁止 SOCIAL_ARCHIVE_PAID_API_ALLOWED=true")
        if self.r2_soft_bytes >= self.r2_hard_bytes or self.oci_soft_bytes >= self.oci_hard_bytes:
            raise RuntimeError("存储软门必须小于硬门")
        # Pairing protects the request-serving Core API.  Offline maintenance
        # units deliberately receive only their own least-privilege
        # credentials, so they must not be forced to carry the API token.
        if require_api_token and self.pairing_required and not self.api_token_file:
            raise RuntimeError("启用鉴权保护时必须提供长期 API Token 文件")
        if self.notion_api_version != "2026-03-11":
            raise RuntimeError("本版本只接受已验收的 Notion-Version 2026-03-11")
        if self.obsidian_rest_ca_file and not Path(self.obsidian_rest_ca_file).is_file():
            raise RuntimeError("Obsidian REST CA 文件不存在")
        if not 15 <= self.account_sync_default_interval_minutes <= 10080:
            raise RuntimeError("账号同步间隔必须在 15–10080 分钟")
        if not 1 <= self.account_sync_page_size <= 250:
            raise RuntimeError("账号同步单页数量必须在 1–250")
        if self.account_sync_max_items_per_run < self.account_sync_page_size:
            raise RuntimeError("账号同步单次上限不得小于单页数量")
