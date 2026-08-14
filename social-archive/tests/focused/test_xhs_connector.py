from __future__ import annotations

import importlib.util
import json
import os
import sys
from pathlib import Path

import httpx
import yaml

from social_archive.connectors.base import ConnectorResult
from social_archive.connectors.http_workers import XHSWorkerConnector
from social_archive.models import ConnectorRunRequest
from social_archive.registry import ConnectorRegistry


def _load_vendor_sync():
    root = Path(__file__).resolve().parents[2]
    spec = importlib.util.spec_from_file_location("social_archive_sa201_vendor_sync", root / "scripts" / "vendor_sync.py")
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_xhs_payload_excludes_cookie_and_collects_only_new_worker_artifacts(monkeypatch, tmp_path):
    output_root = tmp_path / "xhs-output"
    seen = {}

    class FakeResponse:
        status_code = 200

        def raise_for_status(self):
            return None

        def json(self):
            return {"ok": True}

    class FakeClient:
        def __init__(self, *args, **kwargs):
            return None

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return None

        def post(self, url, json):
            seen["url"] = url
            seen["payload"] = json
            (output_root / "fixture.jpg").write_bytes(b"fixture")
            return FakeResponse()

    monkeypatch.setattr(httpx, "Client", FakeClient)
    result = XHSWorkerConnector("http://worker", output_root=output_root).capture(
        {
            "url": "https://www.xiaohongshu.com/explore/fixture",
            "index": [1, 3],
            "skip": True,
            "cookie": "must-not-pass",
        }
    )

    assert result.status == "success"
    assert seen["url"] == "http://worker/xhs/detail"
    assert "cookie" not in seen["payload"]
    assert seen["payload"] == {
        "url": "https://www.xiaohongshu.com/explore/fixture",
        "download": True,
        "index": [1, 3],
        "skip": True,
    }
    assert result.artifacts == [{"path": str((output_root / "fixture.jpg").resolve()), "type": "vendor_download"}]
    assert result.scan_receipt["completeness"] == "complete"


def test_xhs_worker_failure_does_not_block_current_page_l0_l1(settings, service):
    class FailingWorker:
        def capture(self, payload):
            return ConnectorResult(
                "xiaohongshu",
                "xhs-failed",
                "degraded",
                scan_receipt={"completeness": "failed", "item_count": 0},
                errors=[{"code": "XHS_WORKER_FAILED", "message": "fixture worker unavailable", "retryable": True}],
            )

    class FailingMediaFallback:
        def capture_url(self, url, tool):
            return ConnectorResult(
                "command-artifact",
                f"{tool}-failed",
                "degraded",
                scan_receipt={"completeness": "failed", "item_count": 0},
            )

    registry = ConnectorRegistry(settings)
    registry._connectors["xiaohongshu"] = FailingWorker()
    registry.command = FailingMediaFallback()
    worker_result, worker_captures = registry.run(
        "xiaohongshu",
        ConnectorRunRequest(url="https://www.xiaohongshu.com/explore/fixture"),
    )
    fallback, fallback_captures = registry.run(
        "generic-web",
        ConnectorRunRequest(url="https://www.xiaohongshu.com/explore/fixture", requested_levels=["L0", "L1"]),
    )

    assert worker_result.status == "degraded"
    assert worker_captures == []
    assert fallback.status == "success"
    assert len(fallback_captures) == 1
    response = service.capture(fallback_captures[0])
    assert response.accepted_levels == ["L0", "L1"]
    assert response.paused_levels == []



def test_vendor_sync_supports_taskpack_single_source_lock(monkeypatch, tmp_path, capsys):
    root = tmp_path / "social-archive"
    lock = root / "machine" / "third_party_lock.json"
    lock.parent.mkdir(parents=True)
    lock.write_text(
        json.dumps(
            {
                "schema_version": "2.0",
                "entries": [
                    {
                        "id": "xhs_downloader",
                        "repository": "https://github.com/JoeanAmier/XHS-Downloader",
                        "commit": "afaf2fb",
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
    resolved = "afaf2fb0123456789abcdef0123456789abcdef"

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
    monkeypatch.setattr(sys, "argv", ["vendor_sync.py", "--source", "xhs_downloader", "--resolve-and-lock"])

    assert module.main() == 0
    output = json.loads((root / "runtime" / "vendor-resolved.json").read_text(encoding="utf-8"))
    assert output["projects"] == [
        {
            "id": "xhs_downloader",
            "repository": "https://github.com/JoeanAmier/XHS-Downloader",
            "requested_ref": "afaf2fb",
            "resolved_commit": resolved,
            "license": "GPL-3.0",
            "boundary": "SIDECAR_PROCESS_OR_CONTAINER",
            "working_tree": "runtime/vendors/XHS-Downloader",
            "checkout": "detached",
        }
    ]
    assert json.loads(capsys.readouterr().out)["sources"] == ["xhs_downloader"]
    clone_calls = [argv for argv, _cwd, _environment in calls if argv[:2] == ["git", "clone"]]
    assert len(clone_calls) == 1
    assert clone_calls[0][-1] == str(root / "runtime" / "vendors" / "XHS-Downloader")
    assert all("not-selected" not in " ".join(argv) for argv, _cwd, _environment in calls)
    git_environments = [environment for argv, _cwd, environment in calls if argv[0] == "git"]
    assert all(environment is not None for environment in git_environments)
    assert all(environment["GIT_CONFIG_GLOBAL"] == os.devnull for environment in git_environments)
    assert all(environment["GIT_CONFIG_NOSYSTEM"] == "1" for environment in git_environments)
    assert all(environment["GIT_TERMINAL_PROMPT"] == "0" for environment in git_environments)
    assert all("GIT_CONFIG_COUNT" not in environment for environment in git_environments)
    assert all("GIT_CONFIG_KEY_0" not in environment for environment in git_environments)
    assert all("GIT_CONFIG_VALUE_0" not in environment for environment in git_environments)
