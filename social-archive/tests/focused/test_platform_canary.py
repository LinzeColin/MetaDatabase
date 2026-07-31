from __future__ import annotations

import importlib.util
from pathlib import Path
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
