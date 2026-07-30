from __future__ import annotations

import importlib.util
import io
import json
import os
import shlex
import subprocess
import sys
import urllib.error
from pathlib import Path

from social_archive.utils import approved_shared_host_secret


ROOT = Path(__file__).resolve().parents[2]


def _load_script(name: str):
    spec = importlib.util.spec_from_file_location(f"{name}_test_module", ROOT / "scripts" / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    assert spec.loader
    spec.loader.exec_module(module)
    return module


def _write_executable(path: Path, body: str) -> None:
    path.write_text(body, encoding="utf-8")
    path.chmod(0o755)


def test_install_dry_run_is_zero_write_even_when_prerequisites_are_available(tmp_path):
    project = tmp_path / "project"
    scripts = project / "scripts"
    scripts.mkdir(parents=True)
    (scripts / "install.sh").write_text((ROOT / "scripts" / "install.sh").read_text(encoding="utf-8"), encoding="utf-8")
    for relative in ("pyproject.toml", "compose.yaml", ".env.example", "scripts/setup_wizard.py", "scripts/generate_pairing_code.py", "scripts/status_server.py"):
        target = project / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text("fixture\n", encoding="utf-8")
    fake_bin = tmp_path / "bin"
    fake_bin.mkdir()
    _write_executable(fake_bin / "git", "#!/bin/sh\nexit 0\n")
    _write_executable(fake_bin / "python3", f"#!/bin/sh\nexec {shlex.quote(sys.executable)} \"$@\"\n")
    _write_executable(
        fake_bin / "docker",
        "#!/bin/sh\nif [ \"${1:-}\" = compose ] && [ \"${2:-}\" = version ]; then echo fixture-compose; exit 0; fi\nexit 1\n",
    )
    before = sorted(str(path.relative_to(project)) for path in project.rglob("*"))
    env = {**os.environ, "PATH": f"{fake_bin}{os.pathsep}{os.environ['PATH']}"}
    result = subprocess.run(["bash", "scripts/install.sh", "--dry-run"], cwd=project, env=env, text=True, capture_output=True, check=False)

    assert result.returncode == 0, result.stderr
    assert "未创建 .env、runtime、Secret" in result.stdout
    assert sorted(str(path.relative_to(project)) for path in project.rglob("*")) == before
    assert not (project / ".env").exists()
    assert not (project / "runtime").exists()


def test_systemd_host_prepare_dry_run_is_zero_write(tmp_path):
    project = tmp_path / "project"
    scripts = project / "scripts"
    scripts.mkdir(parents=True)
    prepare = scripts / "prepare_systemd_host.sh"
    prepare.write_text((ROOT / "scripts" / "prepare_systemd_host.sh").read_text(encoding="utf-8"), encoding="utf-8")
    prepare.chmod(0o755)
    (project / ".env").write_text("SOCIAL_ARCHIVE_ENV=production\n", encoding="utf-8")
    python_path = project / ".venv" / "bin" / "python"
    python_path.parent.mkdir(parents=True)
    _write_executable(python_path, "#!/bin/sh\nexit 0\n")
    units = project / "deploy" / "systemd"
    units.mkdir(parents=True)
    for name in (
        "social-archive.service",
        "social-archive-backup.service",
        "social-archive-backup.timer",
        "social-archive-cloudflared.service",
        "social-archive-private-database-sync.service",
        "social-archive-private-database-sync.timer",
        "social-archive-replication.service",
        "social-archive-replication.timer",
        "social-archive-status.service",
        "social-archive-status.timer",
        "social-archive-status-web.service",
    ):
        (units / name).write_text("fixture\n", encoding="utf-8")
    secrets = project / "runtime" / "secrets"
    secrets.mkdir(parents=True)
    for name in (
        "r2_access_key_id",
        "r2_secret_access_key",
        "oci_access_key_id",
        "oci_secret_access_key",
        "github_token",
        "social_archive_api_token",
        "social_archive_pairing_code",
        "cli_worker_token",
        "notion_token",
        "obsidian_rest_token",
        "karakeep_api_token",
        "linkwarden_api_token",
    ):
        (secrets / name).write_text("fixture\n", encoding="utf-8")
    before = sorted(str(path.relative_to(project)) for path in project.rglob("*"))

    result = subprocess.run(["bash", "scripts/prepare_systemd_host.sh", "--dry-run"], cwd=project, text=True, capture_output=True, check=False)

    assert result.returncode == 0, result.stderr
    assert "未创建账户、目录、备份、/etc 配置或 unit" in result.stdout
    assert sorted(str(path.relative_to(project)) for path in project.rglob("*")) == before
    assert not (project / "etc").exists()

    apply_result = subprocess.run(["bash", "scripts/prepare_systemd_host.sh", "--apply"], cwd=project, text=True, capture_output=True, check=False)
    assert apply_result.returncode == 2
    assert "只允许在 /opt/social-archive 执行" in apply_result.stderr
    assert sorted(str(path.relative_to(project)) for path in project.rglob("*")) == before


def test_systemd_host_prepare_bridges_nonroot_container_and_host_service_secret_access():
    prepare = (ROOT / "scripts" / "prepare_systemd_host.sh").read_text(encoding="utf-8")

    assert 'CORE_SECRET_GID="10001"' in prepare
    assert 'groupadd --system --gid "$CORE_SECRET_GID" "$CORE_SECRET_GROUP"' in prepare
    assert 'usermod -a -G "$CORE_SECRET_GROUP" "$SYSTEM_USER"' in prepare
    assert 'chown root:"$CORE_SECRET_GROUP" "$ROOT/runtime/secrets"' in prepare
    assert 'chmod 0710 "$ROOT/runtime/secrets"' in prepare
    assert 'chown "$CORE_SECRET_GID:$CORE_SECRET_GID" "$secret_path"' in prepare
    assert 'chmod 0640 "$secret_path"' in prepare


def test_only_the_documented_nonroot_secret_bridge_can_use_group_read_mode():
    assert approved_shared_host_secret(
        Path("/opt/social-archive/runtime/secrets/social_archive_api_token"),
        mode=0o640,
        uid=10001,
        gid=10001,
    )
    assert not approved_shared_host_secret(
        Path("/tmp/social_archive_api_token"),
        mode=0o640,
        uid=10001,
        gid=10001,
    )
    assert not approved_shared_host_secret(
        Path("/opt/social-archive/runtime/secrets/social_archive_api_token"),
        mode=0o644,
        uid=10001,
        gid=10001,
    )
    assert not approved_shared_host_secret(
        Path("/opt/social-archive/runtime/secrets/social_archive_api_token"),
        mode=0o640,
        uid=10002,
        gid=10001,
    )


def test_start_uses_the_installed_project_python_for_pairing_code_generation():
    start = (ROOT / "scripts" / "start.sh").read_text(encoding="utf-8")
    assert ".venv/bin/python scripts/generate_pairing_code.py" in start
    assert "docker compose up -d --force-recreate core-api core-worker" in start


def test_install_checks_out_the_pinned_cli_build_context_before_docker_build():
    install = (ROOT / "scripts" / "install.sh").read_text(encoding="utf-8")
    vendor_command = ".venv/bin/python scripts/vendor_sync.py --source bilibili_cli --resolve-and-lock"

    assert vendor_command in install
    assert install.index(vendor_command) < install.index("docker compose build core-api core-worker cli-tools")


def test_install_provisions_shared_nonroot_bind_mounts_for_core_and_cli_sidecar():
    install = (ROOT / "scripts" / "install.sh").read_text(encoding="utf-8")
    core_dockerfile = (ROOT / "Dockerfile").read_text(encoding="utf-8")
    cli_dockerfile = (ROOT / "sidecars" / "cli-tools" / "Dockerfile").read_text(encoding="utf-8")

    assert "runtime/vendor-output/{cli,xhs,kuaishou,douk}" in install
    assert "chown -R 10001:10001 runtime/import runtime/vendor-output" in install
    assert "chmod 2770 runtime/import runtime/vendor-output runtime/vendor-output/{cli,xhs,kuaishou,douk}" in install
    assert "groupadd --system --gid 10001 socialarchive" in core_dockerfile
    assert "useradd --system --uid 10001 --gid socialarchive" in core_dockerfile
    assert "groupadd --system --gid 10001 socialarchive" in cli_dockerfile
    assert "useradd --system --uid 10002 --gid socialarchive" in cli_dockerfile
    assert "chown -R cliworker:socialarchive /work /worker" in cli_dockerfile


def test_deployment_probe_read_only_never_calls_dns_or_https(monkeypatch, capsys):
    module = _load_script("deployment_probe")
    calls: list[str] = []
    monkeypatch.setattr(module.socket, "getaddrinfo", lambda *_args, **_kwargs: calls.append("dns"))
    monkeypatch.setattr(module.urllib.request, "urlopen", lambda *_args, **_kwargs: calls.append("https"))
    monkeypatch.setattr(sys, "argv", ["deployment_probe.py", "--domain", "social-archive.example", "--read-only"])

    assert module.main() == 3
    report = json.loads(capsys.readouterr().out)
    assert report == {
        "domain": "social-archive.example",
        "status": "NOT_RUN",
        "network_attempted": False,
        "reason": "需要显式 --network-confirmed；--read-only 不执行 DNS 或 HTTPS 请求",
    }
    assert calls == []


def test_deployment_probe_keeps_http_failure_code_without_copying_provider_body(monkeypatch, capsys):
    module = _load_script("deployment_probe")
    monkeypatch.setattr(module.socket, "getaddrinfo", lambda *_args, **_kwargs: [(None, None, None, None, ("203.0.113.8", 443))])

    def http_error(request, *_args, **_kwargs):
        raise urllib.error.HTTPError(str(request), 403, "forbidden", {}, io.BytesIO(b"token=must-not-publish"))

    monkeypatch.setattr(module.urllib.request, "urlopen", http_error)
    monkeypatch.setattr(sys, "argv", ["deployment_probe.py", "--domain", "status.example", "--network-confirmed"])

    assert module.main() == 3
    report = json.loads(capsys.readouterr().out)
    assert report["https"] == {"status": 403, "error_type": "HTTPError"}
    assert "must-not-publish" not in json.dumps(report)


def test_static_deployment_and_systemd_contracts_pass_without_docker_or_network():
    for script in ("validate_deployment_contract.py", "validate_systemd.py"):
        result = subprocess.run([sys.executable, str(ROOT / "scripts" / script)], cwd=ROOT, text=True, capture_output=True, check=False)
        assert result.returncode == 0, result.stderr
        assert "PASS" in result.stdout


def test_status_projection_has_a_loopback_systemd_and_tunnel_route():
    tunnel = (ROOT / "deploy" / "cloudflare" / "tunnel-config.example.yml").read_text(encoding="utf-8")
    service = (ROOT / "deploy" / "systemd" / "social-archive-status-web.service").read_text(encoding="utf-8")
    publisher = (ROOT / "deploy" / "systemd" / "social-archive-status.service").read_text(encoding="utf-8")

    assert "status.linzezhang.com" in tunnel
    assert "path: ^/social-archive(\\.json|-health)$" in tunnel
    assert "service: http://127.0.0.1:18780" in tunnel
    assert "service: http://127.0.0.1:80" in tunnel
    assert "Environment=SOCIAL_ARCHIVE_STATUS_BIND_HOST=127.0.0.1" in service
    assert "Environment=SOCIAL_ARCHIVE_STATUS_PORT=" not in service
    assert "ReadOnlyPaths=/var/lib/social-archive/status" in service
    assert "ReadWritePaths=" not in service
    assert "StateDirectory=social-archive" in publisher


def test_tunnel_renderer_uses_isolated_ports_and_has_no_file_write(tmp_path):
    module = _load_script("render_cloudflare_tunnel_config")
    env_file = tmp_path / ".env"
    env_file.write_text(
        "SOCIAL_ARCHIVE_CORE_LOOPBACK_PORT=18765\nSOCIAL_ARCHIVE_STATUS_PORT=18780\n",
        encoding="utf-8",
    )
    rendered = module.render_remote_configuration(env_file=env_file)
    serialized = json.dumps(rendered, ensure_ascii=False)

    assert "http://127.0.0.1:18765" in serialized
    assert "http://127.0.0.1:18780" in serialized
    assert rendered["config"]["ingress"][2]["path"] == r"^/social-archive(\.json|-health)$"
    assert "http://127.0.0.1:80" in serialized
    assert list(tmp_path.glob("*.yml")) == []
