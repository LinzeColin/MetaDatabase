import importlib.util
import json
import subprocess
from pathlib import Path

import httpx
import pytest
import yaml

from social_archive.connectors.command import CommandArtifactConnector
from social_archive.models import ConnectorRunRequest
from social_archive.registry import ConnectorRegistry


def _load_cli_server():
    root = Path(__file__).resolve().parents[2]
    spec = importlib.util.spec_from_file_location("social_archive_sa204_cli_server", root / "sidecars" / "cli-tools" / "server.py")
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module

def test_gallery_download_uses_argv_without_shell(settings,monkeypatch):
    seen={}
    def fake_run(argv,**kwargs):
        seen.update({'argv':argv,'kwargs':kwargs});out=Path(kwargs['cwd'])/'a.json';out.write_text('{}');return subprocess.CompletedProcess(argv,0,'','')
    monkeypatch.setattr('subprocess.run',fake_run)
    result=CommandArtifactConnector('tiktok',settings.staging_root).capture_url('https://www.wikipedia.org/video','gallery-dl')
    assert result.status=='success' and isinstance(seen['argv'],list) and 'shell' not in seen['kwargs']

def test_remote_cli_worker_maps_only_relative_paths(settings, monkeypatch):
    class Response:
        def raise_for_status(self): return None
        def json(self):
            return {"status":"success","run_id":"r1","artifacts":["r1/a.mp4","../../escape"],"observations":[{"url":"https://www.wikipedia.org/wiki/Archiving"}]}
    class Client:
        def __init__(self, **kwargs): pass
        def __enter__(self): return self
        def __exit__(self, *args): return None
        def post(self, *args, **kwargs): return Response()
    monkeypatch.setattr("social_archive.connectors.command.httpx.Client", Client)
    connector=CommandArtifactConnector("generic", settings.staging_root, worker_url="http://cli-tools:5560", worker_output_root=settings.data_root/"vendor-output/cli")
    result=connector.capture_url("https://www.wikipedia.org/wiki/Archiving", "yt-dlp")
    assert result.status == "success"
    assert len(result.artifacts) == 1
    assert result.scan_receipt["execution_boundary"] == "isolated_http_sidecar"


def test_remote_instagram_sidecar_never_receives_or_reads_core_session(settings, monkeypatch):
    seen = {}

    class Response:
        def raise_for_status(self):
            return None

        def json(self):
            return {
                "status": "success",
                "run_id": "instagram-run",
                "artifacts": ["instagram-run/photo.jpg", "../../instagram_session"],
                "observations": [{"id": "ABC123", "url": "https://www.instagram.com/p/ABC123/"}],
            }

    class Client:
        def __init__(self, **kwargs):
            seen["timeout"] = kwargs["timeout"]

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return None

        def post(self, url, **kwargs):
            seen["url"] = url
            seen["payload"] = kwargs["json"]
            seen["headers"] = kwargs["headers"]
            return Response()

    class ForbiddenSession:
        def __getattribute__(self, name):
            raise AssertionError(f"core must not access the Instagram session: {name}")

    monkeypatch.setattr("social_archive.connectors.command.httpx.Client", Client)
    output_root = settings.data_root / "vendor-output" / "cli"
    connector = CommandArtifactConnector(
        "instagram",
        settings.staging_root,
        worker_url="http://cli-tools:5560",
        worker_output_root=output_root,
    )
    result = connector.instagram_saved(ForbiddenSession(), "owner", 7)

    assert result.status == "success"
    assert result.scan_receipt["completeness"] == "partial"
    assert result.scan_receipt["scope"] == "account_relation"
    assert result.scan_receipt["execution_boundary"] == "isolated_http_sidecar"
    assert seen["url"] == "http://cli-tools:5560/v1/instagram/saved"
    assert seen["payload"] == {"username": "owner", "limit": 7}
    assert "session" not in seen["payload"]
    assert seen["headers"] == {}
    assert result.artifacts == [
        {"path": str((output_root / "instagram-run" / "photo.jpg").resolve()), "type": "downloaded_file"}
    ]


def test_bilibili_sidecar_uses_only_documented_read_only_json_commands(monkeypatch, tmp_path):
    server = _load_cli_server()
    server.OUTPUT_ROOT = tmp_path
    calls = []

    def fake_run(argv, run_dir, timeout=900, *, require_artifacts=True):
        calls.append((argv, require_artifacts))
        if argv[1] == "favorites":
            data = [{"id": 100, "title": "默认收藏夹"}]
        else:
            data = {"items": [{"bvid": f"BV-{argv[1]}", "title": "fixture"}]}
        return {"status": "success", "exit_code": 0, "stdout": json.dumps({"ok": True, "data": data}), "stderr": "", "artifacts": []}

    monkeypatch.setattr(server, "_run", fake_run)

    favorites = server._bilibili_list({"subcommand": "favorites", "limit": 500})
    history = server._bilibili_list({"subcommand": "history", "limit": 500})
    watch_later = server._bilibili_list({"subcommand": "watch-later", "limit": 500})

    assert [argv for argv, _ in calls] == [
        ["bili", "favorites", "--json"],
        ["bili", "history", "--max", "100", "--json"],
        ["bili", "watch-later", "--json"],
    ]
    assert all(require_artifacts is False for _, require_artifacts in calls)
    assert favorites["status"] == history["status"] == watch_later["status"] == "success"
    assert favorites["observations"] == [{"id": 100, "title": "默认收藏夹"}]
    assert history["observations"] == [{"bvid": "BV-history", "title": "fixture"}]
    assert watch_later["observations"] == [{"bvid": "BV-watch-later", "title": "fixture"}]
    with pytest.raises(ValueError):
        server._bilibili_list({"subcommand": "like"})


def test_bilibili_sidecar_turns_upstream_rate_limit_into_structured_degraded(monkeypatch, tmp_path):
    server = _load_cli_server()
    server.OUTPUT_ROOT = tmp_path

    def fake_run(argv, run_dir, timeout=900, *, require_artifacts=True):
        return {
            "status": "failed",
            "exit_code": 1,
            "stdout": json.dumps({"ok": False, "error": {"code": "rate_limited", "message": "HTTP 412"}}),
            "stderr": "",
            "artifacts": [],
        }

    monkeypatch.setattr(server, "_run", fake_run)
    result = server._bilibili_list({"subcommand": "history", "limit": 20})

    assert result["status"] == "degraded"
    assert result["error_code"] == "BILI_RATE_LIMITED"
    assert result["retryable"] is True
    assert result["observations"] == []


@pytest.mark.parametrize("stdout", ["", "not-json", json.dumps({"ok": False, "error": {"code": "invalid"}})])
def test_bilibili_sidecar_refuses_empty_or_unstructured_list_output(monkeypatch, tmp_path, stdout):
    server = _load_cli_server()
    server.OUTPUT_ROOT = tmp_path

    def fake_run(argv, run_dir, timeout=900, *, require_artifacts=True):
        return {
            "status": "success",
            "exit_code": 0,
            "stdout": stdout,
            "stderr": "",
            "artifacts": [],
        }

    monkeypatch.setattr(server, "_run", fake_run)
    result = server._bilibili_list({"subcommand": "history", "limit": 20})

    assert result["status"] == "failed"
    assert result["error_code"] == "BILI_INVALID_RESPONSE"
    assert result["retryable"] is True
    assert result["observations"] == []
    assert "raw_text" not in json.dumps(result, ensure_ascii=False)


def test_bilibili_subprocess_gets_an_empty_per_run_home(monkeypatch, tmp_path):
    server = _load_cli_server()
    run_dir = tmp_path / "run"
    run_dir.mkdir()
    seen = {}

    def fake_run(argv, **kwargs):
        seen["argv"] = argv
        seen["env"] = kwargs["env"]
        return subprocess.CompletedProcess(argv, 0, "{}", "")

    monkeypatch.setattr(server.shutil, "which", lambda binary: f"/usr/bin/{binary}")
    monkeypatch.setattr(server.subprocess, "run", fake_run)
    result = server._run(["bili", "history", "--json"], run_dir, require_artifacts=False)

    assert result["status"] == "success"
    assert seen["argv"] == ["bili", "history", "--json"]
    assert seen["env"]["HOME"] == str(run_dir / "home")
    assert seen["env"]["XDG_CONFIG_HOME"] == str(run_dir / "home" / ".config")
    assert seen["env"]["XDG_CACHE_HOME"] == str(run_dir / "home" / ".cache")
    assert seen["env"]["XDG_DATA_HOME"] == str(run_dir / "home" / ".local" / "share")
    assert all("/run/secrets" not in value for value in seen["env"].values())


def test_bilibili_http_rate_limit_is_structured_without_retrying_or_cookie(settings, monkeypatch):
    seen = {}

    class Response:
        def raise_for_status(self):
            request = httpx.Request("POST", "http://cli-tools:5560/v1/bilibili/list")
            response = httpx.Response(412, request=request)
            raise httpx.HTTPStatusError("rate limited", request=request, response=response)

    class Client:
        def __init__(self, **kwargs):
            return None

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return None

        def post(self, url, **kwargs):
            seen["url"] = url
            seen["payload"] = kwargs["json"]
            seen["headers"] = kwargs["headers"]
            return Response()

    monkeypatch.setattr("social_archive.connectors.command.httpx.Client", Client)
    connector = CommandArtifactConnector("bilibili", settings.staging_root, worker_url="http://cli-tools:5560")
    result = connector.bilibili_list("history", ["--limit", "500"])

    assert seen == {
        "url": "http://cli-tools:5560/v1/bilibili/list",
        "payload": {"subcommand": "history", "limit": 100},
        "headers": {},
    }
    assert result.status == "degraded"
    assert result.errors == [{
        "code": "BILI_RATE_LIMITED",
        "message": "B站暂时限流（HTTP 412/429）；未尝试绕过，请稍后重试或保存当前页。",
        "retryable": True,
    }]
    assert result.scan_receipt["completeness"] == "unknown"


def test_bilibili_rate_limit_leaves_ytdlp_and_current_page_independent(settings, service, monkeypatch):
    class Response:
        def __init__(self, payload):
            self.payload = payload

        def raise_for_status(self):
            return None

        def json(self):
            return self.payload

    class Client:
        def __init__(self, **kwargs):
            return None

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return None

        def post(self, url, **kwargs):
            if url.endswith("/v1/bilibili/list"):
                return Response({"status": "degraded", "error_code": "BILI_RATE_LIMITED", "message": "rate limited", "retryable": True, "observations": [], "artifacts": []})
            assert url.endswith("/v1/capture-url")
            assert kwargs["json"]["tool"] == "yt-dlp"
            return Response({"status": "success", "run_id": "media-run", "artifacts": ["media-run/fixture.mp4"], "observations": [{"url": kwargs["json"]["url"]}]})

    monkeypatch.setattr("social_archive.connectors.command.httpx.Client", Client)
    worker = CommandArtifactConnector(
        "bilibili",
        settings.staging_root,
        worker_url="http://cli-tools:5560",
        worker_output_root=settings.data_root / "vendor-output" / "cli",
    )
    url = "https://www.bilibili.com/video/BV1fixture"
    rate_limited = worker.bilibili_list("history")
    media = worker.capture_url(url, "yt-dlp")
    current_page, captures = ConnectorRegistry(settings).run("generic-web", ConnectorRunRequest(url=url, requested_levels=["L0", "L1"]))

    assert rate_limited.status == "degraded"
    assert media.status == "success"
    assert media.scan_receipt["execution_boundary"] == "isolated_http_sidecar"
    assert current_page.status == "success"
    assert service.capture(captures[0]).accepted_levels == ["L0", "L1"]


def test_bilibili_sidecar_build_uses_only_fixed_vendor_context_without_bilibili_secret():
    root = Path(__file__).resolve().parents[2]
    compose = yaml.safe_load((root / "compose.yaml").read_text(encoding="utf-8"))
    worker = compose["services"]["cli-tools"]
    dockerfile = (root / "sidecars" / "cli-tools" / "Dockerfile").read_text(encoding="utf-8")
    core_dockerfile = (root / "Dockerfile").read_text(encoding="utf-8")

    assert worker["build"]["context"] == "./sidecars/cli-tools"
    assert worker["build"]["additional_contexts"] == {"bilibili_cli": "./runtime/vendors/bilibili_cli"}
    assert worker["secrets"] == ["cli_worker_token", "instagram_session"]
    assert "bilibili" not in json.dumps(worker["secrets"], ensure_ascii=False).lower()
    assert 'COPY --from=bilibili_cli pyproject.toml README.md LICENSE /opt/bilibili-cli/' in dockerfile
    assert 'COPY --from=bilibili_cli bili_cli /opt/bilibili-cli/bili_cli' in dockerfile
    assert "bilibili-cli" not in core_dockerfile
