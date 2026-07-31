from __future__ import annotations

import hashlib
import importlib.util
import json
import sys
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace

from social_archive.models import CaptureRequest
from social_archive.private_facts import PRIVATE_DATABASE_EVENT, completed_content_facts, fact_sha256


def _load_script(root: Path):
    spec = importlib.util.spec_from_file_location("private_database_sync_test_module", root / "scripts/sync_private_database.py")
    module = importlib.util.module_from_spec(spec)
    assert spec.loader
    spec.loader.exec_module(module)
    return module


def _set_settings(monkeypatch, module, settings):
    monkeypatch.setattr(module, "Settings", SimpleNamespace(from_env=lambda: settings))


def _completed_content(service, store):
    response = service.capture(CaptureRequest(
        platform="generic-web",
        url="https://www.wikipedia.org/private-fact?access_token=must-not-export&safe=1",
        relation_type="saved",
        title="Private fact",
        text="token=must-not-export body",
        raw_metadata={"api_token": "must-not-export", "nested": {"cookie": "must-not-export", "safe": "kept"}},
        requested_levels=["L0", "L1"],
    ))
    artifact = store.get_content(response.content_id)["artifacts"][0]
    for store_id in ("r2", "oci", "github"):
        store.upsert_object_replica(
            artifact_id=artifact["id"],
            store_id=store_id,
            object_key=f"{store_id}://private-fact",
            status="verified",
            verified_sha256="d" * 64,
            original_sha256=artifact["sha256"],
            encryption="age-x25519",
        )
    return response.content_id


def test_runtime_never_mounts_or_installs_a_private_database_worktree():
    root = Path(__file__).resolve().parents[2]
    compose = (root / "compose.yaml").read_text(encoding="utf-8")
    env_example = (root / ".env.example").read_text(encoding="utf-8")
    install = (root / "scripts/install.sh").read_text(encoding="utf-8")
    sync_service = (root / "deploy/systemd/social-archive-private-database-sync.service").read_text(encoding="utf-8")
    backup_service = (root / "deploy/systemd/social-archive-backup.service").read_text(encoding="utf-8")

    assert "PRIVATE_DATABASE_HOST_PATH" not in compose
    assert ":/var/lib/social-archive/private-database" not in compose
    assert "SOCIAL_ARCHIVE_PRIVATE_DATABASE_ROOT=" not in env_example
    assert "SOCIAL_ARCHIVE_PRIVATE_DB_CLIENT=" in env_example
    assert "private-database" not in install
    assert "sync_private_database.py --once" in sync_service
    assert "ReadWritePaths=/var/lib/social-archive" in backup_service
    assert "/opt/social-archive/runtime" not in backup_service


def test_sync_missing_api_client_fails_before_runtime_or_local_private_copy(monkeypatch, settings, tmp_path, capsys):
    module = _load_script(Path(__file__).resolve().parents[2])
    data_root = tmp_path / "blocked-runtime"
    blocked_settings = replace(
        settings,
        data_root=data_root,
        runtime_db=data_root / "runtime/social-archive.sqlite3",
        staging_root=data_root / "staging",
        private_database_root=data_root / "private-database",
        watch_root=data_root / "import",
        export_root=data_root / "exports",
        cli_output_root=data_root / "vendor-output/cli",
    )
    _set_settings(monkeypatch, module, blocked_settings)
    monkeypatch.delenv("SOCIAL_ARCHIVE_PRIVATE_DB_CLIENT", raising=False)
    monkeypatch.setattr(sys, "argv", ["sync_private_database.py", "--once"])

    assert module.main() == 3
    report = json.loads(capsys.readouterr().out)
    assert report["status"] == "BLOCKED_ENVIRONMENT"
    assert report["error_code"] == "PRIVATE_DATABASE_CLIENT_UNAVAILABLE"
    assert not data_root.exists()
    assert not blocked_settings.private_database_root.exists()


def test_completed_fact_is_sanitized_idempotent_and_delivered_only_after_verify(monkeypatch, service, store, settings, tmp_path, capsys):
    content_id = _completed_content(service, store)
    facts = completed_content_facts(store)
    assert len(facts) == 1
    serialized = json.dumps(facts[0], ensure_ascii=False)
    assert "must-not-export" not in serialized
    assert "local_path" not in serialized
    assert "access_token" not in serialized
    assert facts[0]["content"]["id"] == content_id

    module = _load_script(Path(__file__).resolve().parents[2])
    client = tmp_path / "private_db_client.py"
    client.write_text("# fixture only\n", encoding="utf-8")
    monkeypatch.setenv("SOCIAL_ARCHIVE_PRIVATE_DB_CLIENT", str(client))
    _set_settings(monkeypatch, module, settings)
    calls: list[list[str]] = []

    def fake_run(_client, argv):
        calls.append(list(argv))
        return (0, "Private-MetaDatabase: 账本 1 条，对象在仓 1，缺 0") if argv[0] == "verify" else (0, "")

    monkeypatch.setattr(module, "_run_client", fake_run)
    monkeypatch.setattr(sys, "argv", ["sync_private_database.py", "--once"])

    assert module.main() == 0
    report = json.loads(capsys.readouterr().out)
    assert report["status"] == "PASS"
    assert calls[-1] == ["verify", "Private-MetaDatabase"]
    assert calls[0][:3] == ["ingest", "Private-MetaDatabase", calls[0][2]]
    assert calls[0][3:5] == ["--domain", "SocialArchive"]
    event = store.get_outbox_event(
        event_type=PRIVATE_DATABASE_EVENT,
        aggregate_id=content_id,
        payload_sha256=fact_sha256(facts[0]),
    )
    assert event and event["status"] == "delivered"
    assert not settings.private_database_root.exists()

    calls.clear()
    assert module.main() == 0
    repeat = json.loads(capsys.readouterr().out)
    assert repeat["status"] == "NO_CHANGE"
    assert calls == []


def test_verify_failure_keeps_fact_pending_for_a_safe_retry(monkeypatch, service, store, settings, tmp_path, capsys):
    content_id = _completed_content(service, store)
    fact = completed_content_facts(store)[0]
    module = _load_script(Path(__file__).resolve().parents[2])
    client = tmp_path / "private_db_client.py"
    client.write_text("# fixture only\n", encoding="utf-8")
    monkeypatch.setenv("SOCIAL_ARCHIVE_PRIVATE_DB_CLIENT", str(client))
    _set_settings(monkeypatch, module, settings)

    def fake_run(_client, argv):
        return (7, "verify failed") if argv[0] == "verify" else (0, "")

    monkeypatch.setattr(module, "_run_client", fake_run)
    monkeypatch.setattr(sys, "argv", ["sync_private_database.py", "--once"])

    assert module.main() == 4
    report = json.loads(capsys.readouterr().out)
    assert report["status"] == "DEGRADED"
    event = store.get_outbox_event(
        event_type=PRIVATE_DATABASE_EVENT,
        aggregate_id=content_id,
        payload_sha256=fact_sha256(fact),
    )
    assert event and event["status"] == "pending"
    assert event["last_error_code"] == "PRIVATE_DATABASE_VERIFY_FAILED"


def test_zero_exit_verify_with_missing_objects_is_not_an_acknowledgement(monkeypatch, service, store, settings, tmp_path, capsys):
    content_id = _completed_content(service, store)
    fact = completed_content_facts(store)[0]
    module = _load_script(Path(__file__).resolve().parents[2])
    client = tmp_path / "private_db_client.py"
    client.write_text("# fixture only\n", encoding="utf-8")
    monkeypatch.setenv("SOCIAL_ARCHIVE_PRIVATE_DB_CLIENT", str(client))
    _set_settings(monkeypatch, module, settings)

    def fake_run(_client, argv):
        return (0, "Private-MetaDatabase: 账本 1 条，对象在仓 0，缺 1") if argv[0] == "verify" else (0, "")

    monkeypatch.setattr(module, "_run_client", fake_run)
    monkeypatch.setattr(sys, "argv", ["sync_private_database.py", "--once"])

    assert module.main() == 4
    report = json.loads(capsys.readouterr().out)
    assert report["failures"][0]["error_code"] == "PRIVATE_DATABASE_VERIFY_FAILED"
    event = store.get_outbox_event(
        event_type=PRIVATE_DATABASE_EVENT,
        aggregate_id=content_id,
        payload_sha256=fact_sha256(fact),
    )
    assert event and event["status"] == "pending"


def test_legacy_prefixed_manifest_is_strictly_read_back_before_acknowledgement(monkeypatch, tmp_path):
    module = _load_script(Path(__file__).resolve().parents[2])
    client = tmp_path / "private_db_client.py"
    client.write_text("# fixture only\n", encoding="utf-8")
    payload = b'{"legacy":true}\n'
    digest = hashlib.sha256(payload).hexdigest()
    name = "eei_facts_2026-07-26.ndjson.gz"
    relative = f"objects/{digest[:2]}/{digest}_{name}"
    manifest_entry = {
        "sha256": digest,
        "original_name": name,
        "size_bytes": len(payload),
        "object_path": f"Private-MetaDatabase/{relative}",
    }
    calls: list[list[str]] = []

    def fake_run(_client, argv):
        calls.append(list(argv))
        if argv[:3] == ["get", "Private-MetaDatabase", "manifest.jsonl"]:
            Path(argv[3]).write_text(json.dumps(manifest_entry) + "\n", encoding="utf-8")
            return 0, ""
        assert argv[:3] == ["get", "Private-MetaDatabase", relative]
        Path(argv[3]).write_bytes(payload)
        return 0, ""

    monkeypatch.setattr(module, "_run_client", fake_run)

    passed, detail = module._verify_legacy_prefixed_manifest(
        client,
        "Private-MetaDatabase: 账本 1 条，对象在仓 0，缺 1",
    )

    assert passed
    assert "读回并核哈希" in detail
    assert calls[0][:3] == ["get", "Private-MetaDatabase", "manifest.jsonl"]
    assert calls[1][:3] == ["get", "Private-MetaDatabase", relative]


def test_legacy_prefixed_manifest_rejects_a_readback_sha_mismatch(monkeypatch, tmp_path):
    module = _load_script(Path(__file__).resolve().parents[2])
    client = tmp_path / "private_db_client.py"
    client.write_text("# fixture only\n", encoding="utf-8")
    expected_payload = b'{"legacy":true}\n'
    digest = hashlib.sha256(expected_payload).hexdigest()
    name = "eei_facts_2026-07-26.ndjson.gz"
    relative = f"objects/{digest[:2]}/{digest}_{name}"
    manifest_entry = {
        "sha256": digest,
        "original_name": name,
        "size_bytes": len(expected_payload),
        "object_path": f"Private-MetaDatabase/{relative}",
    }

    def fake_run(_client, argv):
        if argv[:3] == ["get", "Private-MetaDatabase", "manifest.jsonl"]:
            Path(argv[3]).write_text(json.dumps(manifest_entry) + "\n", encoding="utf-8")
            return 0, ""
        Path(argv[3]).write_bytes(b'{"legacy":false}\n')
        return 0, ""

    monkeypatch.setattr(module, "_run_client", fake_run)

    passed, detail = module._verify_legacy_prefixed_manifest(
        client,
        "Private-MetaDatabase: 账本 1 条，对象在仓 0，缺 1",
    )

    assert not passed
    assert "不一致" in detail
