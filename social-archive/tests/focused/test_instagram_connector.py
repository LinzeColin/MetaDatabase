from __future__ import annotations

import importlib.util
from pathlib import Path

import yaml

from social_archive.connectors.command import CommandArtifactConnector
from social_archive.models import ConnectorRunRequest
from social_archive.registry import ConnectorRegistry


def _load_cli_sidecar(monkeypatch, tmp_path):
    root = Path(__file__).resolve().parents[2]
    monkeypatch.setenv("SOCIAL_ARCHIVE_CLI_OUTPUT_ROOT", str(tmp_path / "sidecar-output"))
    monkeypatch.setenv("SOCIAL_ARCHIVE_INSTAGRAM_SESSION_FILE", str(tmp_path / "instagram-session"))
    spec = importlib.util.spec_from_file_location(
        "social_archive_sa104_cli_sidecar",
        root / "sidecars" / "cli-tools" / "server.py",
    )
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_instagram_without_session_is_blocked_and_current_page_fallback_remains_available(settings):
    result = CommandArtifactConnector("instagram", settings.staging_root).instagram_saved(None, None, 1)
    assert result.status == "blocked_environment"
    assert result.errors[0]["code"] == "INSTAGRAM_SESSION_OR_BINARY_MISSING"
    assert result.scan_receipt["completeness"] == "unknown"

    fallback, captures = ConnectorRegistry(settings).run(
        "generic-web",
        ConnectorRunRequest(url="https://www.instagram.com/p/example/"),
    )
    assert fallback.status == "success"
    assert fallback.scan_receipt["scope"] == "item"
    assert len(captures) == 1
    assert captures[0].platform == "generic-web"
    assert captures[0].relation_type == "manual_save"


def test_instagram_session_is_mounted_only_in_cli_sidecar():
    root = Path(__file__).resolve().parents[2]
    compose = yaml.safe_load((root / "compose.yaml").read_text(encoding="utf-8"))
    services = compose["services"]
    for core_service in ("core-api", "core-worker"):
        assert "instagram_session" not in services[core_service]["secrets"]
        assert all("instagram_session" not in str(volume) for volume in services[core_service]["volumes"])

    sidecar = services["cli-tools"]
    assert sidecar["environment"]["SOCIAL_ARCHIVE_INSTAGRAM_SESSION_FILE"] == "/run/secrets/instagram_session"
    assert "instagram_session" in sidecar["secrets"]
    assert "ports" not in sidecar
    assert "instaloader==" not in (root / "Dockerfile").read_text(encoding="utf-8")
    assert "instaloader==" in (root / "sidecars" / "cli-tools" / "Dockerfile").read_text(encoding="utf-8")


def test_cli_sidecar_owns_session_material_and_clamps_export_limit(monkeypatch, tmp_path):
    sidecar = _load_cli_sidecar(monkeypatch, tmp_path)
    session = tmp_path / "instagram-session"

    blocked = sidecar._instagram_saved({"username": "owner", "limit": 1})
    assert blocked["status"] == "blocked_environment"
    assert blocked["artifacts"] == []

    session.write_text("opaque-fixture-session", encoding="utf-8")
    session.chmod(0o600)
    seen: dict[str, object] = {}

    def fake_run(argv, run_dir, timeout=900):
        seen["argv"] = argv
        seen["run_dir"] = run_dir
        seen["timeout"] = timeout
        return {"status": "success", "exit_code": 0, "stdout": "", "stderr": "", "artifacts": []}

    monkeypatch.setattr(sidecar, "_run", fake_run)
    result = sidecar._instagram_saved({"username": "owner", "limit": 501})

    argv = seen["argv"]
    assert result["status"] == "success"
    assert argv[0] == "instaloader"
    assert argv[argv.index("--sessionfile") + 1] == str(session)
    assert argv[argv.index("--count") + 1] == "500"
    assert argv[argv.index("--login") + 1] == "owner"
    assert argv[-1] == ":saved"
    assert "opaque-fixture-session" not in " ".join(argv)
