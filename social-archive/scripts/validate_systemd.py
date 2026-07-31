from __future__ import annotations

import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SYSTEMD = ROOT / "deploy" / "systemd"
REQUIRED = {
    "social-archive.service",
    "social-archive-backup.service",
    "social-archive-backup.timer",
    "social-archive-cloudflared.service",
    "social-archive-status.service",
    "social-archive-status.timer",
    "social-archive-status-web.service",
    "social-archive-replication.service",
    "social-archive-replication.timer",
    "social-archive-private-database-sync.service",
    "social-archive-private-database-sync.timer",
}


def _fail(message: str) -> None:
    print(message, file=sys.stderr)
    raise SystemExit(1)


def _require(text: str, needle: str, name: str) -> None:
    if needle not in text:
        _fail(f"{name} 缺少运行合同：{needle}")


def main() -> int:
    host_prepare = ROOT / "scripts" / "prepare_systemd_host.sh"
    if not host_prepare.is_file():
        _fail("缺少受控宿主机准备脚本：scripts/prepare_systemd_host.sh")
    host_prepare_text = host_prepare.read_text(encoding="utf-8")
    for needle in (
        "--dry-run|--apply",
        'TARGET_ROOT="/opt/social-archive"',
        "systemctl daemon-reload",
        "未启用或启动任何 unit",
        "runtime/secrets",
        "LoadCredential=",
        "validate_host_env_replacement",
        "拒绝覆盖并清空既有非 Secret 配置",
    ):
        _require(host_prepare_text, needle, "prepare_systemd_host.sh")
    if "systemctl enable" in host_prepare_text or "systemctl start" in host_prepare_text:
        _fail("prepare_systemd_host.sh 不得启用或启动生产服务")
    if 'chmod 0640 "$secret_path"' in host_prepare_text or 'chown "$CORE_CONTAINER_UID:$CORE_SECRET_GROUP" "$secret_path"' in host_prepare_text:
        _fail("prepare_systemd_host.sh 不得放宽长期 Secret 文件权限")

    env_example = (ROOT / ".env.example").read_text(encoding="utf-8")
    for needle in (
        "SOCIAL_ARCHIVE_CORE_LOOPBACK_PORT=18765",
        "SOCIAL_ARCHIVE_STATUS_PORT=18780",
    ):
        _require(env_example, needle, ".env.example")

    existing = {path.name for path in SYSTEMD.glob("*") if path.is_file()}
    missing = REQUIRED - existing
    if missing:
        _fail("缺少 systemd 文件：" + ",".join(sorted(missing)))

    documents = {path.name: path.read_text(encoding="utf-8") for path in SYSTEMD.glob("*") if path.is_file()}
    for name, text in documents.items():
        if "launchd" in text.lower() or "chatgpt" in text.lower():
            _fail(f"禁止开发 Agent/macOS 常驻依赖：{name}")
        if name.endswith(".service") and "[Service]" not in text:
            _fail(f"无 Service 段：{name}")
        if name.endswith(".timer") and "[Timer]" not in text:
            _fail(f"无 Timer 段：{name}")

    core = documents["social-archive.service"]
    _require(core, "WorkingDirectory=/opt/social-archive", "social-archive.service")
    _require(core, "ExecStart=/usr/bin/docker compose up -d core-api core-worker", "social-archive.service")
    _require(core, "Wants=network-online.target social-archive-status-web.service", "social-archive.service")

    cloudflared = documents["social-archive-cloudflared.service"]
    for needle in (
        "ConditionPathExists=/etc/social-archive/social-archive-cloudflared.env",
        "EnvironmentFile=/etc/social-archive/social-archive-cloudflared.env",
        "ExecStart=/usr/local/bin/cloudflared tunnel --no-autoupdate run --token ${SOCIAL_ARCHIVE_CLOUDFLARED_TOKEN}",
        "NoNewPrivileges=yes",
        "ProtectSystem=strict",
    ):
        _require(cloudflared, needle, "social-archive-cloudflared.service")
    if "SOCIAL_ARCHIVE_CLOUDFLARED_TOKEN=" in cloudflared:
        _fail("social-archive-cloudflared.service 不得在 unit 中保存 Tunnel Token 值")

    tunnel_renderer = ROOT / "scripts" / "render_cloudflare_tunnel_config.py"
    if not tunnel_renderer.is_file():
        _fail("缺少受控 Tunnel 配置渲染器：scripts/render_cloudflare_tunnel_config.py")
    renderer_text = tunnel_renderer.read_text(encoding="utf-8")
    for needle in (
        "SOCIAL_ARCHIVE_CORE_LOOPBACK_PORT",
        "SOCIAL_ARCHIVE_STATUS_PORT",
        "/social-archive-health",
        "http://127.0.0.1:80",
    ):
        _require(renderer_text, needle, "render_cloudflare_tunnel_config.py")

    for name, command in {
        "social-archive-status.service": "scripts/status_publish.py",
        "social-archive-replication.service": "scripts/replicate_objects.py --store all --limit 200",
        "social-archive-private-database-sync.service": "scripts/sync_private_database.py --once",
        "social-archive-backup.service": "scripts/backup.py --once",
    }.items():
        text = documents[name]
        _require(text, command, name)
        _require(text, "NoNewPrivileges=yes", name)
        _require(text, "ProtectSystem=strict", name)
        _require(text, "ReadWritePaths=/var/lib/social-archive", name)
        if any(
            "/opt/social-archive/runtime" in line
            for line in text.splitlines()
            if line.startswith("ReadWritePaths=")
        ):
            _fail(f"{name} 不得写入源码工作目录 runtime")

    status_service = documents["social-archive-status.service"]
    _require(status_service, "LoadCredential=api_token:/opt/social-archive/runtime/secrets/social_archive_api_token", "social-archive-status.service")
    _require(status_service, "Environment=SOCIAL_ARCHIVE_API_TOKEN_FILE=%d/api_token", "social-archive-status.service")
    if "StateDirectory=" in status_service or "ReadOnlyPaths=/opt/social-archive/runtime/secrets" in status_service:
        _fail("social-archive-status.service 不得重置共享数据根或直接暴露长期 Secret 路径")

    replication = documents["social-archive-replication.service"]
    for needle in (
        "LoadCredential=r2_access_key_id:/opt/social-archive/runtime/secrets/r2_access_key_id",
        "LoadCredential=oci_secret_access_key:/opt/social-archive/runtime/secrets/oci_secret_access_key",
        "LoadCredential=github_token:/opt/social-archive/runtime/secrets/github_token",
        "Environment=SOCIAL_ARCHIVE_GITHUB_TOKEN_FILE=%d/github_token",
    ):
        _require(replication, needle, "social-archive-replication.service")

    backup = documents["social-archive-backup.service"]
    for needle in (
        "LoadCredential=r2_access_key_id:/opt/social-archive/runtime/secrets/r2_access_key_id",
        "LoadCredential=oci_secret_access_key:/opt/social-archive/runtime/secrets/oci_secret_access_key",
        "Environment=SOCIAL_ARCHIVE_R2_ACCESS_KEY_ID_FILE=%d/r2_access_key_id",
        "Environment=SOCIAL_ARCHIVE_OCI_SECRET_ACCESS_KEY_FILE=%d/oci_secret_access_key",
    ):
        _require(backup, needle, "social-archive-backup.service")

    status_web = documents["social-archive-status-web.service"]
    for needle in (
        "Requires=social-archive-status.service",
        "PartOf=social-archive.service",
        "EnvironmentFile=/etc/social-archive/social-archive.env",
        "Environment=SOCIAL_ARCHIVE_STATUS_BIND_HOST=127.0.0.1",
        "scripts/status_server.py",
        "ReadOnlyPaths=/var/lib/social-archive/status",
        "NoNewPrivileges=yes",
        "ProtectSystem=strict",
    ):
        _require(status_web, needle, "social-archive-status-web.service")
    if "Environment=SOCIAL_ARCHIVE_STATUS_PORT=" in status_web:
        _fail("social-archive-status-web.service 必须从受控 EnvironmentFile 读取隔离端口")
    if any(line.startswith("ReadWritePaths=") for line in status_web.splitlines()):
        _fail("social-archive-status-web.service 不得拥有写入路径")

    for timer_name, unit in {
        "social-archive-status.timer": "social-archive-status.service",
        "social-archive-replication.timer": "social-archive-replication.service",
        "social-archive-private-database-sync.timer": "social-archive-private-database-sync.service",
        "social-archive-backup.timer": "social-archive-backup.service",
    }.items():
        _require(documents[timer_name], f"Unit={unit}", timer_name)

    print("PASS：systemd 运行合同完整，状态与复制只可写入 /var/lib/social-archive。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
