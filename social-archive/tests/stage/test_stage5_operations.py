from pathlib import Path


def test_stage5_deployment_contract_keeps_core_private_and_status_runtime_only():
    root = Path(__file__).resolve().parents[2]
    systemd = root / "deploy" / "systemd"
    text = "\n".join(path.read_text(encoding="utf-8") for path in systemd.iterdir())
    compose = (root / "compose.yaml").read_text(encoding="utf-8")
    status_service = (systemd / "social-archive-status.service").read_text(encoding="utf-8")
    status_web_service = (systemd / "social-archive-status-web.service").read_text(encoding="utf-8")
    replication_service = (systemd / "social-archive-replication.service").read_text(encoding="utf-8")
    host_prepare = (root / "scripts" / "prepare_systemd_host.sh").read_text(encoding="utf-8")

    assert "launchd" not in text.lower() and "ChatGPT" not in text
    assert 'ports: ["127.0.0.1:${SOCIAL_ARCHIVE_CORE_LOOPBACK_PORT:-18765}:8765"]' in compose
    assert "ReadWritePaths=/var/lib/social-archive" in status_service
    assert "LoadCredential=api_token:/opt/social-archive/runtime/secrets/social_archive_api_token" in status_service
    assert "Environment=SOCIAL_ARCHIVE_API_TOKEN_FILE=%d/api_token" in status_service
    assert "StateDirectory=" not in status_service
    assert "LoadCredential=github_token:/opt/social-archive/runtime/secrets/github_token" in replication_service
    assert "Environment=SOCIAL_ARCHIVE_GITHUB_TOKEN_FILE=%d/github_token" in replication_service
    assert "Environment=SOCIAL_ARCHIVE_STATUS_BIND_HOST=127.0.0.1" in status_web_service
    assert "ReadOnlyPaths=/var/lib/social-archive/status" in status_web_service
    assert "ReadWritePaths=" not in status_web_service
    assert "/opt/social-archive/runtime" not in "\n".join(
        line for line in status_service.splitlines() if line.startswith("ReadWritePaths=")
    )
    assert "/opt/social-archive/runtime" not in "\n".join(
        line for line in replication_service.splitlines() if line.startswith("ReadWritePaths=")
    )
    assert "--dry-run|--apply" in host_prepare
    assert "systemctl daemon-reload" in host_prepare
    assert "systemctl enable" not in host_prepare and "systemctl start" not in host_prepare


def test_stage5_cloudflare_policy_has_distinct_ui_api_and_owner_evidence_boundary():
    root = Path(__file__).resolve().parents[2]
    policy = (root / "deploy" / "cloudflare" / "API_EDGE_POLICY.md").read_text(encoding="utf-8")
    tunnel = (root / "deploy" / "cloudflare" / "tunnel-config.example.yml").read_text(encoding="utf-8")

    for value in (
        "social-archive.linzezhang.com",
        "social-archive-api.linzezhang.com",
        "Cloudflare Access",
        "Bearer Token",
        # v0.0.0.7 / T03：原先这里是 "10 次"/"5 次"/"16 KiB"——一次性配对码的
        # 限流目标、错误尝试上限和请求体上限。那条链路已删，三个数字随之失去对象。
        # **边缘限流规则本身没有放宽**，判据因此改为直接核对那条真实规则，
        # 比核对一个产品目标数字更接近实际配置。
        "1 次 / 10 秒",
        "撤销后扩展上行立刻 401",
        "真实 Rule ID",
    ):
        assert value in policy
    # 反向：策略文件里不许再声明可用的配对端点。
    assert "`POST /v1/pairing/exchange`" not in policy.split("已随 v0.0.0.7")[0]
    assert tunnel.count("http://127.0.0.1:18765") == 2
    assert "status.linzezhang.com" in tunnel
    assert "path: ^/social-archive(\\.json|-health)$" in tunnel
    assert "http://127.0.0.1:18780" in tunnel
    assert "http://127.0.0.1:80" in tunnel
    assert "http_status:404" in tunnel
