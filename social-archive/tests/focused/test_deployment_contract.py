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

import yaml

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
    (project / ".env").write_text(
        "SOCIAL_ARCHIVE_ENV=production\n"
        "SOCIAL_ARCHIVE_DATA_HOST_PATH=/var/lib/social-archive\n"
        "SOCIAL_ARCHIVE_DATA_ROOT=/var/lib/social-archive\n"
        "SOCIAL_ARCHIVE_IMPORT_HOST_PATH=/var/lib/social-archive/import\n"
        "SOCIAL_ARCHIVE_VENDOR_OUTPUT_HOST_PATH=/var/lib/social-archive/vendor-output\n"
        "SOCIAL_ARCHIVE_HOST_DATA_GID=10001\n",
        encoding="utf-8",
    )
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

    (project / ".env").write_text(
        "SOCIAL_ARCHIVE_ENV=production\n"
        "SOCIAL_ARCHIVE_DATA_HOST_PATH=/var/lib/social-archive\n"
        "SOCIAL_ARCHIVE_DATA_ROOT=/var/lib/social-archive\n"
        "SOCIAL_ARCHIVE_IMPORT_HOST_PATH=./runtime/import\n"
        "SOCIAL_ARCHIVE_VENDOR_OUTPUT_HOST_PATH=/var/lib/social-archive/vendor-output\n"
        "SOCIAL_ARCHIVE_HOST_DATA_GID=10001\n",
        encoding="utf-8",
    )
    split_result = subprocess.run(["bash", "scripts/prepare_systemd_host.sh", "--dry-run"], cwd=project, text=True, capture_output=True, check=False)
    assert split_result.returncode == 2
    assert "SOCIAL_ARCHIVE_IMPORT_HOST_PATH" in split_result.stderr

    (project / ".env").write_text(
        "SOCIAL_ARCHIVE_ENV=production\n"
        "SOCIAL_ARCHIVE_DATA_HOST_PATH=/var/lib/social-archive\n"
        "SOCIAL_ARCHIVE_DATA_ROOT=/var/lib/social-archive\n"
        "SOCIAL_ARCHIVE_IMPORT_HOST_PATH=/var/lib/social-archive/import\n"
        "SOCIAL_ARCHIVE_VENDOR_OUTPUT_HOST_PATH=/var/lib/social-archive/vendor-output\n"
        "SOCIAL_ARCHIVE_HOST_DATA_GID=10001\n",
        encoding="utf-8",
    )

    apply_result = subprocess.run(["bash", "scripts/prepare_systemd_host.sh", "--apply"], cwd=project, text=True, capture_output=True, check=False)
    assert apply_result.returncode == 2
    assert "只允许在 /opt/social-archive 执行" in apply_result.stderr
    assert sorted(str(path.relative_to(project)) for path in project.rglob("*")) == before


def test_systemd_host_prepare_refuses_to_erase_existing_nonsecret_host_configuration(tmp_path):
    project = tmp_path / "project"
    scripts = project / "scripts"
    scripts.mkdir(parents=True)
    data_root = project / "data"
    prepare_text = (ROOT / "scripts" / "prepare_systemd_host.sh").read_text(encoding="utf-8")
    replacements = {
        'TARGET_ROOT="/opt/social-archive"': f'TARGET_ROOT="{project}"',
        'HOST_ENV_DIR="/etc/social-archive"': f'HOST_ENV_DIR="{project / "etc" / "social-archive"}"',
        'SYSTEMD_DIR="/etc/systemd/system"': f'SYSTEMD_DIR="{project / "systemd"}"',
        'BACKUP_ROOT="/var/backups/social-archive"': f'BACKUP_ROOT="{project / "backups"}"',
        'HOST_DATA_ROOT="/var/lib/social-archive"': f'HOST_DATA_ROOT="{data_root}"',
    }
    for before, after in replacements.items():
        assert before in prepare_text
        prepare_text = prepare_text.replace(before, after)
    prepare = scripts / "prepare_systemd_host.sh"
    prepare.write_text(prepare_text, encoding="utf-8")
    prepare.chmod(0o755)
    (project / ".env").write_text(
        "SOCIAL_ARCHIVE_ENV=production\n"
        f"SOCIAL_ARCHIVE_DATA_HOST_PATH={data_root}\n"
        f"SOCIAL_ARCHIVE_DATA_ROOT={data_root}\n"
        f"SOCIAL_ARCHIVE_IMPORT_HOST_PATH={data_root}/import\n"
        f"SOCIAL_ARCHIVE_VENDOR_OUTPUT_HOST_PATH={data_root}/vendor-output\n"
        "SOCIAL_ARCHIVE_HOST_DATA_GID=980\n",
        encoding="utf-8",
    )
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
    host_env = project / "etc" / "social-archive" / "social-archive.env"
    host_env.parent.mkdir(parents=True)
    host_env.write_text("SOCIAL_ARCHIVE_R2_ENDPOINT=https://fixture.invalid\n", encoding="utf-8")
    before = host_env.read_text(encoding="utf-8")

    fake_bin = tmp_path / "bin"
    fake_bin.mkdir()
    _write_executable(
        fake_bin / "id",
        "#!/bin/sh\nif [ \"${1:-}\" = \"-u\" ]; then echo 0; elif [ \"${1:-}\" = \"-g\" ]; then echo 980; else exit 0; fi\n",
    )
    for command in ("useradd", "install", "systemctl", "stat"):
        _write_executable(fake_bin / command, "#!/bin/sh\nexit 0\n")
    env = {**os.environ, "PATH": f"{fake_bin}{os.pathsep}{os.environ['PATH']}"}
    result = subprocess.run(["bash", "scripts/prepare_systemd_host.sh", "--apply"], cwd=project, env=env, text=True, capture_output=True, check=False)

    assert result.returncode == 2
    assert "拒绝覆盖并清空既有非 Secret 配置" in result.stderr
    assert host_env.read_text(encoding="utf-8") == before
    assert not data_root.exists()
    assert not (project / "backups").exists()


def test_systemd_host_prepare_keeps_long_lived_secrets_root_only_and_uses_unit_credentials():
    prepare = (ROOT / "scripts" / "prepare_systemd_host.sh").read_text(encoding="utf-8")
    replication = (ROOT / "deploy" / "systemd" / "social-archive-replication.service").read_text(encoding="utf-8")
    backup = (ROOT / "deploy" / "systemd" / "social-archive-backup.service").read_text(encoding="utf-8")
    status = (ROOT / "deploy" / "systemd" / "social-archive-status.service").read_text(encoding="utf-8")

    assert 'CORE_CONTAINER_UID="10001"' in prepare
    assert 'install -d -m 2770 -o "$CORE_CONTAINER_UID" -g "$SYSTEM_USER" "$shared_path"' in prepare
    assert 'github_token 已设置时必须保持 root:root 0600' in prepare
    assert 'LoadCredential= at process start' in prepare
    assert "CORE_SECRET_GROUP" not in prepare
    assert 'chmod 0640 "$secret_path"' not in prepare
    assert "SOCIAL_ARCHIVE_GITHUB_TOKEN_FILE=$ROOT/runtime/secrets/github_token" not in prepare
    assert "validate_host_env_replacement" in prepare
    assert "拒绝覆盖并清空既有非 Secret 配置" in prepare
    assert 'LoadCredential=github_token:/opt/social-archive/runtime/secrets/github_token' in replication
    assert 'Environment=SOCIAL_ARCHIVE_GITHUB_TOKEN_FILE=%d/github_token' in replication
    assert 'LoadCredential=r2_access_key_id:/opt/social-archive/runtime/secrets/r2_access_key_id' in backup
    assert 'Environment=SOCIAL_ARCHIVE_R2_ACCESS_KEY_ID_FILE=%d/r2_access_key_id' in backup
    assert 'LoadCredential=api_token:/opt/social-archive/runtime/secrets/social_archive_api_token' in status
    assert 'Environment=SOCIAL_ARCHIVE_API_TOKEN_FILE=%d/api_token' in status


def test_only_the_documented_nonroot_container_secret_bridge_can_use_group_read_mode():
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
    assert not approved_shared_host_secret(
        Path("/opt/social-archive/runtime/secrets/social_archive_api_token"),
        mode=0o640,
        uid=10001,
        gid=10002,
    )


def test_start_uses_the_installed_project_python_for_pairing_code_generation():
    start = (ROOT / "scripts" / "start.sh").read_text(encoding="utf-8")
    assert ".venv/bin/python scripts/generate_pairing_code.py" in start
    assert "docker compose up -d --force-recreate core-api core-worker" in start


def test_worker_does_not_inherit_the_api_only_image_healthcheck():
    compose = yaml.safe_load((ROOT / "compose.yaml").read_text(encoding="utf-8"))
    worker = compose["services"]["core-worker"]

    assert worker["command"] == ["social-archive-worker"]
    assert worker["healthcheck"] == {"disable": True}


def test_core_and_host_maintenance_share_an_explicit_bind_data_plane():
    compose = yaml.safe_load((ROOT / "compose.yaml").read_text(encoding="utf-8"))
    bind = "${SOCIAL_ARCHIVE_DATA_HOST_PATH:-./runtime/data}:/var/lib/social-archive"

    for service_name in ("core-api", "core-worker"):
        assert bind in compose["services"][service_name]["volumes"]
        core_secrets = compose["services"][service_name]["secrets"]
        assert "github_token" not in core_secrets
        assert "r2_access_key_id" not in core_secrets
        assert "oci_access_key_id" not in core_secrets
    assert "social_archive_data" not in (compose.get("volumes") or {})

    cli = compose["services"]["cli-tools"]
    assert cli["group_add"] == ["${SOCIAL_ARCHIVE_HOST_DATA_GID:-10001}"]

    example = (ROOT / ".env.example").read_text(encoding="utf-8")
    prepare = (ROOT / "scripts" / "prepare_systemd_host.sh").read_text(encoding="utf-8")
    assert "SOCIAL_ARCHIVE_DATA_HOST_PATH=./runtime/data" in example
    assert "SOCIAL_ARCHIVE_HOST_DATA_GID=10001" in example
    assert 'HOST_DATA_ROOT="/var/lib/social-archive"' in prepare
    assert "SOCIAL_ARCHIVE_DATA_HOST_PATH" in prepare
    assert "SOCIAL_ARCHIVE_DATA_ROOT" in prepare
    assert "SOCIAL_ARCHIVE_IMPORT_HOST_PATH" in prepare
    assert "SOCIAL_ARCHIVE_VENDOR_OUTPUT_HOST_PATH" in prepare
    assert "SOCIAL_ARCHIVE_HOST_DATA_GID" in prepare


def test_core_entrypoint_preserves_group_writable_shared_data_without_root_runtime():
    dockerfile = (ROOT / "Dockerfile").read_text(encoding="utf-8")
    entrypoint = (ROOT / "scripts" / "container-entrypoint.sh").read_text(encoding="utf-8")

    assert 'ENTRYPOINT ["/bin/sh", "/app/scripts/container-entrypoint.sh"]' in dockerfile
    assert "umask 0007" in entrypoint
    assert 'exec "$@"' in entrypoint


def test_install_checks_out_the_pinned_cli_build_context_before_docker_build():
    install = (ROOT / "scripts" / "install.sh").read_text(encoding="utf-8")
    vendor_command = ".venv/bin/python scripts/vendor_sync.py --source bilibili_cli --resolve-and-lock"

    assert vendor_command in install
    assert install.index(vendor_command) < install.index("docker compose build core-api core-worker cli-tools")


def test_install_provisions_shared_nonroot_bind_mounts_for_core_and_cli_sidecar():
    install = (ROOT / "scripts" / "install.sh").read_text(encoding="utf-8")
    core_dockerfile = (ROOT / "Dockerfile").read_text(encoding="utf-8")
    cli_dockerfile = (ROOT / "sidecars" / "cli-tools" / "Dockerfile").read_text(encoding="utf-8")

    assert "runtime/{data,secrets,import,exports,vendor-src,evidence}" in install
    assert "runtime/vendor-output/{cli,xhs,kuaishou,douk}" in install
    assert "chown -R 10001:10001 runtime/data runtime/import runtime/vendor-output" in install
    assert "chmod 2770 runtime/data runtime/import runtime/vendor-output runtime/vendor-output/{cli,xhs,kuaishou,douk}" in install
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
    assert "LoadCredential=api_token:/opt/social-archive/runtime/secrets/social_archive_api_token" in publisher
    assert "Environment=SOCIAL_ARCHIVE_API_TOKEN_FILE=%d/api_token" in publisher
    assert "StateDirectory=" not in publisher


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
