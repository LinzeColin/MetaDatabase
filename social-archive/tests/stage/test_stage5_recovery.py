from __future__ import annotations

import hashlib
import importlib.util
import json
import os
import re
import subprocess
import sys
from pathlib import Path

from social_archive.db import RuntimeStore
from social_archive.models import CaptureRequest
from social_archive.private_facts import completed_content_facts


ROOT = Path(__file__).resolve().parents[2]


def _backup_module():
    spec = importlib.util.spec_from_file_location("stage5_backup_fixture", ROOT / "scripts/backup.py")
    module = importlib.util.module_from_spec(spec)
    assert spec.loader
    spec.loader.exec_module(module)
    return module


def _completed_fact(service, store):
    response = service.capture(CaptureRequest(
        platform="generic-web",
        url="https://www.wikipedia.org/stage5-recovery-fixture",
        source_account_id="stage5-owner",
        relation_type="saved",
        collection_key="stage5",
        title="Stage 5 recovery fixture",
        text="deterministic recovery fixture",
        requested_levels=["L0", "L1"],
    ))
    artifact = store.get_content(response.content_id)["artifacts"][0]
    for store_id in ("r2", "oci", "github"):
        store.upsert_object_replica(
            artifact_id=artifact["id"],
            store_id=store_id,
            object_key=f"{store_id}://stage5/{artifact['sha256']}.age",
            status="verified",
            verified_sha256="e" * 64,
            original_sha256=artifact["sha256"],
            encryption="age-x25519",
        )
    facts = completed_content_facts(store)
    assert len(facts) == 1
    return response.content_id, facts[0]


def _age_identity(tmp_path: Path) -> tuple[Path, str]:
    identity = tmp_path / "fixture.agekey"
    result = subprocess.run(["age-keygen", "-o", str(identity)], text=True, capture_output=True, check=True)
    match = re.search(r"Public key:\s*(age1[0-9a-z]+)", result.stdout + result.stderr)
    assert match, "age-keygen did not return a public recipient"
    return identity, match.group(1)


def _encrypted_manifest(tmp_path: Path, facts: list[dict], recipient: str) -> tuple[Path, Path]:
    backup = _backup_module()
    bundle_root = tmp_path / "bundle"
    plain = backup._write_snapshot(facts, bundle_root)
    cipher = tmp_path / "fixture.age"
    subprocess.run(["age", "-r", recipient, "-o", str(cipher), str(plain)], text=True, capture_output=True, check=True)
    original_sha = hashlib.sha256(plain.read_bytes()).hexdigest()
    cipher_sha = hashlib.sha256(cipher.read_bytes()).hexdigest()
    receipt = {
        "status": "verified",
        "object_key": "backups/private-database/stage5/fixture.age",
        "original_sha256": original_sha,
        "cipher_sha256": cipher_sha,
        "encryption": "age-x25519",
    }
    manifest_path = tmp_path / "data" / "backups" / "private-database" / "stage5" / "manifest.json"
    manifest_path.parent.mkdir(parents=True)
    manifest_path.write_text(json.dumps({
        "schema_version": "3.0",
        "ciphertext": str(cipher),
        "original_sha256": original_sha,
        "cipher_sha256": cipher_sha,
        "encryption": "age-x25519",
        "receipts": {"r2": receipt, "oci": dict(receipt)},
    }), encoding="utf-8")
    return manifest_path, manifest_path.parents[3]


def _run(args: list[str], env: dict[str, str]) -> tuple[int, dict]:
    result = subprocess.run(args, cwd=ROOT, env=env, text=True, capture_output=True, check=False)
    return result.returncode, json.loads(result.stdout)


def test_fixture_restore_uses_real_age_rebuilds_sqlite_and_refuses_overwrite(service, store, tmp_path):
    content_id, fact = _completed_fact(service, store)
    identity, recipient = _age_identity(tmp_path)
    _manifest, data_root = _encrypted_manifest(tmp_path, [fact], recipient)
    env = os.environ | {
        "SOCIAL_ARCHIVE_DATA_ROOT": str(data_root),
        "SOCIAL_ARCHIVE_AGE_IDENTITY_FILE": str(identity),
        "PYTHONDONTWRITEBYTECODE": "1",
    }

    verify_code, verify = _run([sys.executable, "scripts/restore.py", "--latest", "--verify-only"], env)
    assert verify_code == 0 and verify["status"] == "PASS" and verify["fact_count"] == 1

    recovered = tmp_path / "recovered"
    restore_code, restore = _run([sys.executable, "scripts/restore.py", "--latest", "--target", str(recovered)], env)
    assert restore_code == 0 and restore["mode"] == "restore"
    rebuilt = tmp_path / "rebuilt" / "runtime.sqlite3"
    rebuild_code, rebuild = _run([sys.executable, "scripts/rebuild_runtime.py", str(recovered), "--target", str(rebuilt)], env)
    assert rebuild_code == 0 and rebuild["status"] == "PASS" and rebuild["content_count"] == 1
    projection = RuntimeStore(rebuilt).get_content(content_id)
    assert projection and projection["body"] == "deterministic recovery fixture"
    assert projection["artifacts"][0]["local_path"] is None
    assert {row["store_id"] for row in projection["object_replicas"]} == {"r2", "oci", "github"}

    overwrite_code, overwrite = _run([sys.executable, "scripts/rebuild_runtime.py", str(recovered), "--target", str(rebuilt)], env)
    assert overwrite_code == 1 and overwrite["error_code"] == "RUNTIME_REBUILD_REJECTED"


def test_missing_one_of_three_receipts_fails_before_sqlite_rebuild(service, store, tmp_path):
    _content_id, fact = _completed_fact(service, store)
    incomplete = json.loads(json.dumps(fact))
    incomplete["object_replicas"] = [row for row in incomplete["object_replicas"] if row["store_id"] != "github"]
    identity, recipient = _age_identity(tmp_path)
    _manifest, data_root = _encrypted_manifest(tmp_path, [incomplete], recipient)
    env = os.environ | {
        "SOCIAL_ARCHIVE_DATA_ROOT": str(data_root),
        "SOCIAL_ARCHIVE_AGE_IDENTITY_FILE": str(identity),
        "PYTHONDONTWRITEBYTECODE": "1",
    }
    code, result = _run([sys.executable, "scripts/restore.py", "--latest", "--verify-only"], env)
    assert code == 1 and result["error_code"] == "RECOVERY_BUNDLE_INVALID"
    assert "三副本" in result["message"]


def test_latest_verify_without_backup_is_blocked_without_creating_runtime(tmp_path):
    data_root = tmp_path / "empty-runtime"
    env = os.environ | {"SOCIAL_ARCHIVE_DATA_ROOT": str(data_root), "PYTHONDONTWRITEBYTECODE": "1"}
    code, result = _run([sys.executable, "scripts/restore.py", "--latest", "--verify-only"], env)
    assert code == 3 and result["status"] == "BLOCKED_ENVIRONMENT"
    assert not data_root.exists()
