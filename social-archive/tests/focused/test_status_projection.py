from __future__ import annotations

import importlib.util
import http.client
import json
import sys
import threading
from pathlib import Path

from social_archive.registry import ConnectorRegistry


def test_connector_registry_always_contains_all_platforms(settings, store):
    items = ConnectorRegistry(settings).health_views(store.connector_states())
    # 2026-08-05 由 9 变 10：Owner 裁定把 youtube 接上（它此前在服务端凭据表、
    # Cookie 导出白名单、manifest 权限三处都有，唯独界面上没有入口）。
    # **这个数字写死是有意的**——加平台是产品决定，不该悄悄发生。
    assert len(items) == 10
    assert {item["connector_id"] for item in items} >= {
        "x", "xiaohongshu", "bilibili", "generic-web", "youtube"}


def test_connector_status_uses_fresh_probe_metadata_and_fails_closed(settings, store, monkeypatch):
    store.upsert_connector_state(
        "x",
        state="healthy",
        policy_gate="pass",
        auth_gate="pass",
        technical_gate="pass",
        last_checked_at="2026-07-31T00:00:00Z",
        latency_ms=1,
        message_zh="旧的成功状态",
    )
    registry = ConnectorRegistry(settings)
    monkeypatch.setattr(
        registry,
        "_live_probe",
        lambda _: {"state": "blocked_environment", "error_code": "FIXTURE_OFFLINE"},
    )
    view = next(item for item in registry.health_views(store.connector_states()) if item["connector_id"] == "x")
    assert view["state"] == "blocked_environment"
    assert view["last_error_code"] == "FIXTURE_OFFLINE"
    assert view["last_checked_at"]
    assert isinstance(view["latency_ms"], int)
    # **这一条原来断言正文里要出现「状态代码：FIXTURE_OFFLINE」。**
    #
    # 它的用意是证明「这次读的是新鲜探针，不是库里那条旧的成功状态」——
    # 那个用意完全正确，保留（上面三条 last_error_code / last_checked_at /
    # latency_ms 已经各自证明了新鲜度）。
    #
    # 但**把失败码摆进给用户看的正文**是另一回事。2026-08-05 生产上
    # x 那一条显示的就是：
    #     「状态代码：X_ZERO_COST_NOT_CONFIRMED。尚未配置真实账号或
    #      Worker；先使用保存当前页面，再按向导配置。」
    # 既让用户读我们的失败码，又叫他「按向导配置」——**而没有任何向导
    # 能打开那道零费用门**（那是 Owner 的花钱判断）。
    #
    # 现在正文由 NOT_SYNCABLE_YET 逐平台给出真实原因（含「现在可以：…」）。
    assert "FIXTURE_OFFLINE" not in view["last_message_zh"], "失败码又被摆到用户面前了"
    assert "现在可以" in view["last_message_zh"], "只说做不到，没说现在能做什么"
    # 新鲜度仍然要证明：库里那条「旧的成功状态」不许泄漏出来
    assert "旧的成功状态" not in view["last_message_zh"]


def _load_status_publish(root: Path):
    spec = importlib.util.spec_from_file_location("status_publish_test_module", root / "scripts" / "status_publish.py")
    module = importlib.util.module_from_spec(spec)
    assert spec.loader
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _load_status_server(root: Path):
    spec = importlib.util.spec_from_file_location("status_server_test_module", root / "scripts" / "status_server.py")
    module = importlib.util.module_from_spec(spec)
    assert spec.loader
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _request_status(server, method: str, path: str):
    host, port = server.server_address[:2]
    connection = http.client.HTTPConnection(host, port, timeout=2)
    try:
        connection.request(method, path)
        response = connection.getresponse()
        return response.status, dict(response.getheaders()), response.read()
    finally:
        connection.close()


def test_status_publish_allowlists_and_redacts_projection(tmp_path, monkeypatch):
    root = Path(__file__).resolve().parents[2]
    module = _load_status_publish(root)
    data_root = tmp_path / "runtime-data"
    monkeypatch.setenv("SOCIAL_ARCHIVE_DATA_ROOT", str(data_root))
    payload = {
        "project": "untrusted name",
        "version": "0.0.0.6",
        "overall": "healthy",
        "connectors": [{
            "connector_id": "x",
            "display_name": "X",
            "state": "degraded",
            "last_message_zh": "token=must-not-publish cookie=must-not-publish",
            "local_path": "/private/runtime/object",
        }],
        "destinations": [{
            "destination_id": "notion",
            "display_name": "Notion",
            "state": "needs_user_action",
            "capabilities": {"endpoint": "https://private.example"},
            "last_message_zh": "secret=must-not-publish",
        }],
        "storage": [{"store_id": "r2", "measured_bytes": 42, "endpoint": "https://private.example"}],
        "replicas": [{"store_id": "r2", "status": "verified", "object_count": 2, "byte_count": 42, "object_key": "private"}],
        "recovery": {"last_backup": "/private/backup"},
    }

    class FakeResponse:
        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

        def read(self, *_args):
            return json.dumps(payload).encode("utf-8")

    monkeypatch.setattr(module.urllib.request, "urlopen", lambda *_args, **_kwargs: FakeResponse())
    assert module.main() == 0

    output = data_root / "status" / "social-archive.json"
    document = json.loads(output.read_text(encoding="utf-8"))
    serialized = json.dumps(document, ensure_ascii=False)
    assert document["project"] == "Social Archive"
    assert document["overall"] == "healthy"
    assert "must-not-publish" not in serialized
    assert "local_path" not in serialized and "capabilities" not in serialized and "object_key" not in serialized
    assert document["recovery"] == {"last_backup": "unknown", "last_restore_drill": "unknown"}
    assert output.stat().st_mode & 0o777 == 0o640


def test_status_publish_writes_safe_down_document_when_loopback_is_unavailable(tmp_path, monkeypatch):
    root = Path(__file__).resolve().parents[2]
    module = _load_status_publish(root)
    data_root = tmp_path / "down-data"
    monkeypatch.setenv("SOCIAL_ARCHIVE_DATA_ROOT", str(data_root))
    monkeypatch.setattr(module.urllib.request, "urlopen", lambda *_args, **_kwargs: (_ for _ in ()).throw(OSError("token=hidden")))

    assert module.main() == 0
    document = json.loads((data_root / "status" / "social-archive.json").read_text(encoding="utf-8"))
    assert document["overall"] == "down"
    assert document["error_type"] == "OSError"
    assert "token=hidden" not in json.dumps(document, ensure_ascii=False)


def test_status_web_is_loopback_only_and_serves_only_sanitized_readonly_projection(tmp_path, monkeypatch):
    root = Path(__file__).resolve().parents[2]
    module = _load_status_server(root)
    projection = tmp_path / "status" / "social-archive.json"
    projection.parent.mkdir()
    projection.write_text(
        json.dumps(
            {
                "version": "0.0.0.6",
                "overall": "healthy",
                "connectors": [{"connector_id": "x", "last_message_zh": "token=must-not-publish", "private_path": "/private"}],
                "recovery": {"last_backup": "/private"},
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    server = module.make_server("127.0.0.1", 0, projection)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        status, headers, body = _request_status(server, "GET", "/social-archive.json")
        document = json.loads(body)
        assert status == 200
        assert headers["Cache-Control"] == "no-store, max-age=0"
        assert document["project"] == "Social Archive"
        assert document["recovery"] == {"last_backup": "unknown", "last_restore_drill": "unknown"}
        assert "must-not-publish" not in body.decode("utf-8")
        assert "private_path" not in body.decode("utf-8")
        assert _request_status(server, "GET", "/")[0] == 200
        assert _request_status(server, "GET", "/health")[0] == 200
        assert _request_status(server, "GET", "/social-archive-health")[0] == 200
        assert _request_status(server, "GET", "/runtime.sqlite3")[0] == 404
        assert _request_status(server, "POST", "/social-archive.json")[0] == 405
    finally:
        server.shutdown()
        thread.join(timeout=2)
        server.server_close()

    monkeypatch.setenv("SOCIAL_ARCHIVE_STATUS_BIND_HOST", "0.0.0.0")
    try:
        module.server_config_from_env()
    except ValueError as exc:
        assert "loopback" in str(exc)
    else:
        raise AssertionError("状态服务不得接受公网绑定")


def test_status_web_returns_no_internal_detail_when_projection_is_missing(tmp_path):
    root = Path(__file__).resolve().parents[2]
    module = _load_status_server(root)
    server = module.make_server("127.0.0.1", 0, tmp_path / "missing" / "social-archive.json")
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        status, _headers, body = _request_status(server, "GET", "/")
        assert status == 503
        assert json.loads(body) == {"status": "unavailable"}
        assert str(tmp_path) not in body.decode("utf-8")
    finally:
        server.shutdown()
        thread.join(timeout=2)
        server.server_close()
