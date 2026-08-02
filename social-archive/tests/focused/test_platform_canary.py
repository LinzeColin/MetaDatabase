from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import sys
from types import SimpleNamespace


def _load_canary(root: Path):
    spec = importlib.util.spec_from_file_location("platform_canary_test_module", root / "scripts/platform_canary.py")
    module = importlib.util.module_from_spec(spec)
    assert spec.loader
    spec.loader.exec_module(module)
    return module


def test_generic_web_canary_uses_restricted_api_token(monkeypatch, tmp_path: Path):
    root = Path(__file__).resolve().parents[2]
    module = _load_canary(root)
    token_file = tmp_path / "api-token"
    token_file.write_text("fixture-api-token\n", encoding="utf-8")
    token_file.chmod(0o600)
    settings = SimpleNamespace(pairing_required=True, api_token_file=str(token_file))
    monkeypatch.setattr(module.Settings, "from_env", lambda: settings)
    captured: dict[str, object] = {}

    class Response:
        def raise_for_status(self) -> None:
            return None

        def json(self) -> dict[str, str]:
            return {"content_id": "cnt-canary"}

    def post(url: str, *, headers: dict[str, str], json: dict[str, object], timeout: int) -> Response:
        captured.update({"url": url, "headers": headers, "json": json, "timeout": timeout})
        return Response()

    monkeypatch.setattr(module.httpx, "post", post)

    outcome = module.run_one("generic-web", 1)

    assert outcome["status"] == "PASS"
    assert outcome["details"] == {"content_id": "cnt-canary"}
    assert captured["headers"] == {"Authorization": "Bearer fixture-api-token"}
    assert captured["timeout"] == 10


def test_generic_web_canary_fails_closed_when_pairing_requires_token(monkeypatch):
    root = Path(__file__).resolve().parents[2]
    module = _load_canary(root)
    settings = SimpleNamespace(pairing_required=True, api_token_file=None)
    monkeypatch.setattr(module.Settings, "from_env", lambda: settings)

    def unexpected_post(*_args, **_kwargs):
        raise AssertionError("missing token must block before outbound core request")

    monkeypatch.setattr(module.httpx, "post", unexpected_post)

    outcome = module.run_one("generic-web", 1)

    assert outcome["status"] == "BLOCKED_ENVIRONMENT"
    assert outcome["details"]["error_code"] == "API_TOKEN_MISSING"


def test_canary_receipt_uses_the_configured_runtime_data_root(monkeypatch, tmp_path: Path, capsys):
    root = Path(__file__).resolve().parents[2]
    module = _load_canary(root)
    monkeypatch.setattr(module.Settings, "from_env", lambda: SimpleNamespace(data_root=tmp_path))

    document = {"platform": "generic-web", "status": "PASS", "details": {"content_id": "cnt-canary"}}
    module.save(document)

    receipt = tmp_path / "evidence" / "platform-canaries" / "generic-web.json"
    assert receipt.is_file()
    assert receipt.read_text(encoding="utf-8").strip()
    assert '"platform": "generic-web"' in capsys.readouterr().out


def test_read_only_canary_blocks_before_settings_secret_or_network(monkeypatch):
    root = Path(__file__).resolve().parents[2]
    module = _load_canary(root)

    monkeypatch.setattr(module.Settings, "from_env", lambda: (_ for _ in ()).throw(AssertionError("settings must not load")))
    monkeypatch.setattr(module, "read_secret", lambda *_args: (_ for _ in ()).throw(AssertionError("secret must not be read")))
    monkeypatch.setattr(module.httpx, "post", lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError("network must not run")))

    for platform in ("generic-web", "reddit", "x", "instagram"):
        outcome = module.run_one(platform, 1, read_only=True)
        assert outcome["status"] == "BLOCKED_ENVIRONMENT"
        assert outcome["details"]["error_code"] == "OWNER_CANARY_NOT_AUTHORIZED"
        assert outcome["details"]["credential_read"] is False
        assert outcome["details"]["network_attempted"] is False
        assert outcome["details"]["runtime_write"] is False


def test_read_only_cli_does_not_persist_receipts(monkeypatch, capsys):
    root = Path(__file__).resolve().parents[2]
    module = _load_canary(root)
    calls: list[tuple[str, int, bool]] = []

    def fake_run(platform: str, limit: int, *, read_only: bool = False) -> dict:
        calls.append((platform, limit, read_only))
        return {"platform": platform, "status": "BLOCKED_ENVIRONMENT", "details": {"read_only": True}}

    monkeypatch.setattr(module, "run_one", fake_run)
    monkeypatch.setattr(module, "save", lambda _doc: (_ for _ in ()).throw(AssertionError("read-only must not persist")))
    monkeypatch.setattr(sys, "argv", ["platform_canary.py", "all", "--read-only", "--limit", "2"])

    assert module.main() == 0
    emitted = [json.loads(line) for line in capsys.readouterr().out.splitlines()]
    assert [item["platform"] for item in emitted] == ["generic-web", "x", "reddit", "instagram", "tiktok", "xiaohongshu", "douyin", "kuaishou", "bilibili"]
    assert calls == [(item["platform"], 2, True) for item in emitted]
