from __future__ import annotations

import importlib.util
import json
import os
import sys
from pathlib import Path

import httpx
import yaml

from social_archive.connectors.http_workers import OpenAPIURLWorkerConnector


def _load_vendor_sync():
    root = Path(__file__).resolve().parents[2]
    spec = importlib.util.spec_from_file_location("social_archive_sa202_vendor_sync", root / "scripts" / "vendor_sync.py")
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_openapi_probe_uses_one_documented_url_route_and_collects_new_artifact(monkeypatch, tmp_path):
    output_root = tmp_path / "douk-output"
    seen: dict[str, object] = {"get": [], "post": []}

    class Response:
        status_code = 200

        def raise_for_status(self):
            return None

        def json(self):
            return {
                "paths": {
                    "/v1/douyin/detail": {
                        "post": {
                            "description": "Parse a URL and download selected media",
                            "requestBody": {
                                "content": {
                                    "application/json": {
                                        "schema": {
                                            "type": "object",
                                            "required": ["url"],
                                            "properties": {
                                                "url": {"type": "string"},
                                                "download": {"type": "boolean"},
                                            },
                                        }
                                    }
                                }
                            },
                        }
                    }
                }
            }

    class Client:
        def __init__(self, *args, **kwargs):
            return None

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return None

        def get(self, url, **kwargs):
            seen["get"].append(url)
            return Response()

        def post(self, url, json, **kwargs):
            seen["post"].append((url, json))
            (output_root / "fixture.mp4").write_bytes(b"fixture")
            return Response()

    monkeypatch.setattr(httpx, "Client", Client)
    connector = OpenAPIURLWorkerConnector("douyin", "抖音", "http://douk-worker", output_root=output_root)
    url = "https://www.douyin.com/video/fixture"

    assert connector.health() == {"state": "healthy", "route": "/v1/douyin/detail"}
    result = connector.capture({"url": url, "cookie": "must-not-forward"})

    assert result.status == "success"
    assert seen["get"] == ["http://douk-worker/openapi.json", "http://douk-worker/openapi.json"]
    assert seen["post"] == [("http://douk-worker/v1/douyin/detail", {"url": url, "download": True})]
    assert result.artifacts == [{"path": str((output_root / "fixture.mp4").resolve()), "type": "vendor_download"}]
    assert result.scan_receipt["completeness"] == "complete"


def test_openapi_probe_resolves_ks_component_schema_and_never_forwards_cookie(monkeypatch, tmp_path):
    output_root = tmp_path / "kuaishou-output"
    seen: dict[str, object] = {"get": [], "post": []}
    document = {
        "paths": {
            "/share": {
                "post": {
                    "summary": "Resolve a sharing redirect",
                    "requestBody": {
                        "content": {
                            "application/json": {"schema": {"$ref": "#/components/schemas/ShareModel"}}
                        }
                    },
                }
            },
            "/detail/": {
                "post": {
                    "summary": "Get item detail",
                    "requestBody": {
                        "content": {
                            "application/json": {"schema": {"$ref": "#/components/schemas/DetailModel"}}
                        }
                    },
                }
            },
        },
        "components": {
            "schemas": {
                "ShareModel": {
                    "type": "object",
                    "required": ["text"],
                    "properties": {"text": {"type": "string"}},
                },
                "DetailModel": {
                    "type": "object",
                    "required": ["text"],
                    "properties": {
                        "text": {"type": "string"},
                        "cookies": {"type": "string"},
                        "proxy": {"type": "string"},
                    },
                },
            }
        },
    }

    class Response:
        status_code = 200

        def raise_for_status(self):
            return None

        def json(self):
            return document

    class Client:
        def __init__(self, *args, **kwargs):
            return None

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return None

        def get(self, url, **kwargs):
            seen["get"].append(url)
            return Response()

        def post(self, url, json, **kwargs):
            seen["post"].append((url, json))
            (output_root / "fixture.mp4").write_bytes(b"fixture")
            return Response()

    monkeypatch.setattr(httpx, "Client", Client)
    connector = OpenAPIURLWorkerConnector("kuaishou", "快手", "http://ks-worker", output_root=output_root)
    url = "https://www.kuaishou.com/short-video/fixture"

    assert connector.health() == {"state": "healthy", "route": "/detail/"}
    result = connector.capture({"url": url, "cookie": "must-not-forward", "cookies": "must-not-forward", "proxy": "must-not-forward"})

    assert result.status == "success"
    assert seen["get"] == ["http://ks-worker/openapi.json", "http://ks-worker/openapi.json"]
    assert seen["post"] == [("http://ks-worker/detail/", {"text": url})]
    assert result.artifacts == [{"path": str((output_root / "fixture.mp4").resolve()), "type": "vendor_download"}]


def test_openapi_probe_refuses_ambiguous_routes_without_posting(monkeypatch):
    seen: list[tuple[str, dict[str, object]]] = []
    document = {
        "paths": {
            "/detail": {
                "post": {
                    "requestBody": {
                        "content": {
                            "application/json": {
                                "schema": {
                                    "type": "object",
                                    "required": ["url"],
                                    "properties": {"url": {"type": "string"}},
                                }
                            }
                        }
                    }
                }
            },
            "/extract": {
                "post": {
                    "requestBody": {
                        "content": {
                            "application/json": {
                                "schema": {
                                    "type": "object",
                                    "required": ["text"],
                                    "properties": {"text": {"type": "string"}},
                                }
                            }
                        }
                    }
                }
            },
        }
    }

    class Response:
        status_code = 200

        def raise_for_status(self):
            return None

        def json(self):
            return document

    class Client:
        def __init__(self, *args, **kwargs):
            return None

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return None

        def get(self, url, **kwargs):
            return Response()

        def post(self, url, json, **kwargs):
            seen.append((url, json))
            raise AssertionError("ambiguous OpenAPI must not be called")

    monkeypatch.setattr(httpx, "Client", Client)
    connector = OpenAPIURLWorkerConnector("kuaishou", "快手", "http://ks-worker")

    assert connector.health()["state"] == "degraded"
    result = connector.capture({"url": "https://www.kuaishou.com/short-video/fixture"})

    assert result.status == "degraded"
    assert result.scan_receipt == {"completeness": "failed", "item_count": 0}
    assert result.errors[0]["code"] == "WORKER_PROBE_OR_CALL_FAILED"
    assert seen == []


def test_ks_worker_is_documented_openapi_sidecar_without_secret_or_core_import():
    root = Path(__file__).resolve().parents[2]
    compose = yaml.safe_load((root / "compose.workers.yaml").read_text(encoding="utf-8"))
    worker = compose["services"]["ks-worker"]
    core_dockerfile = (root / "Dockerfile").read_text(encoding="utf-8")

    assert worker["build"]["context"] == "./runtime/vendors/KS-Downloader"
    assert worker["command"] == ["python", "main.py", "api"]
    assert set(worker["profiles"]) == {"domestic-stable", "kuaishou"}
    assert worker["ports"] == ["127.0.0.1:5557:5557"]
    assert worker["restart"] == "unless-stopped"
    assert worker["security_opt"] == ["no-new-privileges:true"]
    assert "secrets" not in worker
    assert "cookie" not in json.dumps(worker, ensure_ascii=False).lower()
    assert "KS-Downloader" not in core_dockerfile
    assert "COPY runtime" not in core_dockerfile


def test_douk_worker_is_experimental_sidecar_without_secret_or_core_import():
    root = Path(__file__).resolve().parents[2]
    compose = yaml.safe_load((root / "compose.workers.yaml").read_text(encoding="utf-8"))
    worker = compose["services"]["douk-worker"]
    core_dockerfile = (root / "Dockerfile").read_text(encoding="utf-8")

    assert worker["build"]["context"] == "./runtime/vendors/TikTokDownloader"
    assert worker["command"] == ["python", "main.py", "api"]
    assert worker["profiles"] == ["douk-experimental"]
    assert "stdin_open" not in worker
    assert "tty" not in worker
    assert "healthcheck" in worker
    assert worker["ports"] == ["127.0.0.1:5555:5555"]
    assert worker["restart"] == "no"
    assert worker["security_opt"] == ["no-new-privileges:true"]
    assert "secrets" not in worker
    assert "cookie" not in json.dumps(worker, ensure_ascii=False).lower()
    assert "TikTokDownloader" not in core_dockerfile
    assert "COPY runtime" not in core_dockerfile


def test_vendor_sync_supports_taskpack_douk_lock_in_isolated_git_environment(monkeypatch, tmp_path, capsys):
    root = tmp_path / "social-archive"
    lock = root / "machine" / "third_party_lock.json"
    lock.parent.mkdir(parents=True)
    lock.write_text(
        json.dumps(
            {
                "schema_version": "2.0",
                "entries": [
                    {
                        "id": "douk",
                        "repository": "https://github.com/JoeanAmier/TikTokDownloader",
                        "commit": "f404781",
                        "license": "GPL-3.0",
                        "boundary": "SIDECAR_PROCESS_OR_CONTAINER",
                    },
                    {
                        "id": "not_selected",
                        "repository": "https://github.com/example/not-selected",
                        "commit": "1234567",
                        "license": "MIT",
                        "boundary": "SIDECAR_HTTP",
                    },
                ],
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    module = _load_vendor_sync()
    monkeypatch.setattr(module, "ROOT", root)
    monkeypatch.setattr(module, "LOCK", lock)
    monkeypatch.setenv("GIT_CONFIG_COUNT", "1")
    monkeypatch.setenv("GIT_CONFIG_KEY_0", "credential.helper")
    monkeypatch.setenv("GIT_CONFIG_VALUE_0", "untrusted")
    calls = []
    resolved = "f4047810123456789abcdef0123456789abcdef0"

    def fake_run(argv, cwd=None, *, environment=None):
        calls.append((argv, cwd, environment))
        if argv[:2] == ["git", "clone"]:
            destination = Path(argv[-1])
            destination.mkdir(parents=True)
            (destination / ".git").mkdir()
            return ""
        if argv[:2] == ["git", "fetch"]:
            return ""
        if argv[:3] == ["git", "rev-parse", "--verify"]:
            return resolved
        if argv[:2] == ["git", "checkout"]:
            return ""
        raise AssertionError(f"unexpected command: {argv}")

    monkeypatch.setattr(module, "run", fake_run)
    monkeypatch.setattr(sys, "argv", ["vendor_sync.py", "--source", "douk", "--resolve-and-lock"])

    assert module.main() == 0
    output = json.loads((root / "runtime" / "vendor-resolved.json").read_text(encoding="utf-8"))
    assert output["projects"][0]["id"] == "douk"
    assert output["projects"][0]["working_tree"] == "runtime/vendors/TikTokDownloader"
    assert output["projects"][0]["resolved_commit"] == resolved
    assert json.loads(capsys.readouterr().out)["sources"] == ["douk"]
    assert all("not-selected" not in " ".join(argv) for argv, _cwd, _environment in calls)
    git_environments = [environment for argv, _cwd, environment in calls if argv[0] == "git"]
    assert all(environment is not None for environment in git_environments)
    assert all(environment["GIT_CONFIG_GLOBAL"] == os.devnull for environment in git_environments)
    assert all(environment["GIT_CONFIG_NOSYSTEM"] == "1" for environment in git_environments)
    assert all(environment["GIT_TERMINAL_PROMPT"] == "0" for environment in git_environments)
    assert all("GIT_CONFIG_COUNT" not in environment for environment in git_environments)
    assert all("GIT_CONFIG_KEY_0" not in environment for environment in git_environments)
    assert all("GIT_CONFIG_VALUE_0" not in environment for environment in git_environments)
