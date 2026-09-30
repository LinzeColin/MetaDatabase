"""OCI 退役（2026-09-30）：「必须有的远端副本」是可配置的集合，OCI 一挂不再卡死整条备份链。

## 这条测试守的是什么事故

OCI 账号过期之后：

    · 2026-09-05 起 `replicate_objects.py --store all` 每一轮 exit 4；
      它是 oneshot 链的第一条，后面的 github_release_backup.py、backup_runtime_db.py 永远轮不到
      → 运行库索引快照 **25 天没有再做**（索引全世界只有服务器磁盘上一份）。
    · 制品要 R2+OCI+GitHub 三份都验过才算 `complete`；OCI 写不进去，
      2026-09-05 15:57 之后进来的 4,704 个制品全部卡在 `staged`
      → 私有库事实（只认 complete 的内容）不再同步 → `backup.py` 报「没有已验证的完成态事实」。

修法是把「必须有哪些副本」从八个脚本里的字面量改成一个配置
（`SOCIAL_ARCHIVE_REPLICA_STORES=r2,github`），下面逐条证明：配置生效、默认老行为不变、
写错配置会直接报错而不是静默兜底。
"""

from __future__ import annotations

import hashlib
import importlib.util
import json
import sqlite3
import sys
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace

import pytest

from social_archive.encryption import EncryptedObject
from social_archive.models import CaptureRequest
from social_archive.private_facts import completed_content_facts
from social_archive.replica_stores import (
    ENV_NAME,
    ReplicaStoresConfigError,
    oci_enabled,
    parse_replica_stores,
    replica_stores,
    stores_before_github,
)

ROOT = Path(__file__).resolve().parents[2]


# ——— 配置本身 ———

def test_default_is_the_old_three_copies(monkeypatch):
    monkeypatch.delenv(ENV_NAME, raising=False)
    assert replica_stores() == ("r2", "oci", "github")
    assert oci_enabled() is True
    assert stores_before_github() == ("r2", "oci")


def test_retired_configuration_drops_oci_everywhere(monkeypatch):
    monkeypatch.setenv(ENV_NAME, "r2,github")
    assert replica_stores() == ("r2", "github")
    assert oci_enabled() is False
    assert stores_before_github() == ("r2",)


def test_order_is_canonical_not_as_typed():
    assert parse_replica_stores("github, r2") == ("r2", "github")


@pytest.mark.parametrize("raw", ["r2", "github", "oci,github", "r2,oci", "r2,github,github", "r2,github,s3", "r2;github"])
def test_a_wrong_configuration_is_an_error_not_a_silent_fallback(raw):
    """写错了就直接报错。静默兜底成默认值 = OCI 又被要求、整条链又红，而没人知道为什么。"""
    with pytest.raises(ReplicaStoresConfigError):
        parse_replica_stores(raw)


# ——— 制品 complete：R2 + GitHub 就够（OCI 退役后），默认仍要三份 ———

def _artifact(service, store, url):
    response = service.capture(CaptureRequest(platform="generic-web", url=url, requested_levels=["L0", "L1"]))
    return response.content_id, store.get_content(response.content_id)["artifacts"][0]


def _verify(store, artifact, store_id, cipher="d" * 64):
    store.upsert_object_replica(
        artifact_id=artifact["id"], store_id=store_id, object_key=f"{store_id}://object",
        status="verified", verified_sha256=cipher,
        original_sha256=artifact["sha256"], encryption="age-x25519",
    )


def test_artifact_completes_with_r2_and_github_once_oci_is_retired(monkeypatch, service, store):
    monkeypatch.setenv(ENV_NAME, "r2,github")
    content_id, artifact = _artifact(service, store, "https://www.wikipedia.org/oci-retired")
    _verify(store, artifact, "r2")
    assert store.get_content(content_id)["artifacts"][0]["status"] != "complete", "只有 R2 一份就 complete 了"
    _verify(store, artifact, "github")
    assert store.get_content(content_id)["artifacts"][0]["status"] == "complete"
    completion = store.replication_completion()
    assert completion["required_replicas"] == 2
    assert completion["all_three_verified"] == 1 and completion["pending"] == 0


def test_a_mismatched_cipher_still_never_completes_when_oci_is_retired(monkeypatch, service, store):
    """放宽的是「几份」，不是「份与份之间必须一致」。"""
    monkeypatch.setenv(ENV_NAME, "r2,github")
    content_id, artifact = _artifact(service, store, "https://www.wikipedia.org/oci-retired-mismatch")
    _verify(store, artifact, "r2", cipher="a" * 64)
    _verify(store, artifact, "github", cipher="b" * 64)
    assert store.get_content(content_id)["artifacts"][0]["status"] != "complete"


def test_default_configuration_still_needs_all_three(monkeypatch, service, store):
    monkeypatch.delenv(ENV_NAME, raising=False)
    content_id, artifact = _artifact(service, store, "https://www.wikipedia.org/oci-default")
    _verify(store, artifact, "r2")
    _verify(store, artifact, "github")
    assert store.get_content(content_id)["artifacts"][0]["status"] != "complete"
    assert store.replication_completion()["required_replicas"] == 3


def test_completed_content_flows_to_private_facts_again(monkeypatch, service, store):
    """卡在 staged 的内容进不了私有库事实——这是 25 天里真正断掉的那条数据流。"""
    monkeypatch.setenv(ENV_NAME, "r2,github")
    content_id, artifact = _artifact(service, store, "https://www.wikipedia.org/oci-retired-facts")
    assert content_id not in {f["content"]["id"] for f in completed_content_facts(store)}
    _verify(store, artifact, "r2")
    _verify(store, artifact, "github")
    assert content_id in {f["content"]["id"] for f in completed_content_facts(store)}


# ——— GitHub 副本只要求「前面的副本」都已验证 ———

def _load(name):
    spec = importlib.util.spec_from_file_location(f"_oci_retired_{name}", ROOT / f"scripts/{name}.py")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    assert spec.loader
    spec.loader.exec_module(module)
    return module


def _encrypted(artifact, cipher="d" * 64):
    return EncryptedObject(
        original_sha256=artifact["sha256"], cipher_sha256=cipher, original_byte_size=1,
        cipher_byte_size=1, path=Path("/nonexistent"), media_type=None,
    )


def test_github_leg_needs_only_r2_when_oci_is_retired(monkeypatch, service, store):
    module = _load("github_release_backup")
    _content_id, artifact = _artifact(service, store, "https://www.wikipedia.org/oci-retired-github-leg")
    _verify(store, artifact, "r2")
    encrypted = _encrypted(artifact)

    monkeypatch.delenv(ENV_NAME, raising=False)
    assert module.required_prior_receipt_error(store, artifact["id"], encrypted) == "OCI_REPLICA_MISSING"

    monkeypatch.setenv(ENV_NAME, "r2,github")
    assert module.required_prior_receipt_error(store, artifact["id"], encrypted) is None


def test_github_leg_still_refuses_an_unverified_r2_copy_when_oci_is_retired(monkeypatch, service, store):
    module = _load("github_release_backup")
    _content_id, artifact = _artifact(service, store, "https://www.wikipedia.org/oci-retired-no-r2")
    monkeypatch.setenv(ENV_NAME, "r2,github")
    assert module.required_prior_receipt_error(store, artifact["id"], _encrypted(artifact)) == "R2_REPLICA_MISSING"


def test_replication_pass_selects_only_r2_when_oci_is_retired(monkeypatch):
    """`--store all` 在 OCI 退役后只剩 R2；否则那条 systemd 链每 15 分钟还去撞一次 OCI。"""
    source = (ROOT / "scripts/replicate_objects.py").read_text(encoding="utf-8")
    assert 'selected = [store for store in replica_stores() if store != "github"] if args.store == "all" else [args.store]' in source


# ——— 索引快照：R2 + 每天一份 GitHub，不再碰 OCI ———

class _FakeEncryptor:
    def __init__(self, *, recipient, root, **_):
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)

    def encrypt(self, obj):
        path = self.root / "fixture.age"
        path.write_bytes(b"fixture-age:" + obj.path.read_bytes())
        return EncryptedObject(
            original_sha256=obj.sha256,
            cipher_sha256=hashlib.sha256(path.read_bytes()).hexdigest(),
            original_byte_size=obj.byte_size, cipher_byte_size=path.stat().st_size,
            path=path, media_type=obj.media_type,
        )


@pytest.fixture
def snapshot_env(monkeypatch, settings):
    """把 backup_runtime_db 的边界（配置、age、S3、gh）换成可记录的替身，OCI 一碰就炸。"""
    monkeypatch.setenv(ENV_NAME, "r2,github")
    configured = replace(settings, age_recipient="age1testrecipient",
                         github_archive_repository="Owner/Private", github_token_file="/nonexistent-token")
    con = sqlite3.connect(configured.runtime_db)
    con.execute("CREATE TABLE IF NOT EXISTS marker(id INTEGER)")
    con.commit()
    con.close()

    module = _load("backup_runtime_db")
    calls: dict[str, list] = {"s3": [], "gh": []}
    state = {"r2_fails": False, "github_fails": False, "minute": 0}

    def fake_utcnow():
        # 每一轮拨快 15 分钟：真实的定时器就是这个间隔，同一秒内两轮会撞同一个快照目录。
        total = 10 * 60 + state["minute"]
        return f"2026-09-30T{total // 60:02d}:{total % 60:02d}:00.000000Z"

    def fake_s3_config(store_id):
        assert store_id != "oci", "OCI 已退役，不该再有人去读 OCI 配置"
        return {"bucket": store_id}

    def fake_upload(config, ciphertext, key, encrypted, readback):
        calls["s3"].append(config["bucket"])
        if state["r2_fails"]:
            raise RuntimeError("r2 down")
        return {"status": "verified", "object_key": key, "cipher_sha256": encrypted.cipher_sha256}

    def fake_run_gh(argv, env=None):
        calls["gh"].append(argv[1:3])
        if state["github_fails"] and argv[1:3] == ["release", "upload"]:
            raise RuntimeError("github down")
        if argv[1:3] == ["release", "download"]:
            target = Path(argv[argv.index("--dir") + 1])
            source = sorted((configured.data_root / "backups/runtime-db").glob("*/encrypted/*"))[-1]
            (target / source.name).write_bytes(source.read_bytes())
        return ""

    monkeypatch.setattr(module, "Settings", SimpleNamespace(from_env=lambda: configured))
    monkeypatch.setattr(module, "AgeEncryptor", _FakeEncryptor)
    monkeypatch.setattr(module, "utcnow", fake_utcnow)
    monkeypatch.setattr(module, "_s3_config", fake_s3_config)
    monkeypatch.setattr(module, "_upload_and_verify", fake_upload)
    monkeypatch.setattr(module, "run_gh", fake_run_gh)
    monkeypatch.setattr(module, "verify_private_repository", lambda *_a, **_k: None)
    monkeypatch.setattr(module, "verify_draft_release", lambda *_a, **_k: None)
    monkeypatch.setattr(module, "github_cli_environment", lambda _f: {"GH_TOKEN": "fixture"})
    monkeypatch.setattr(module.shutil, "which", lambda name: "/usr/bin/gh" if name == "gh" else None)
    return SimpleNamespace(module=module, settings=configured, calls=calls, state=state)


def _run(env, *flags, capsys):
    monkeypatch_argv = ["backup_runtime_db.py", *flags]
    old = sys.argv
    sys.argv = monkeypatch_argv
    try:
        code = env.module.main()
    finally:
        sys.argv = old
        env.state["minute"] += 15
    out = capsys.readouterr().out.strip().splitlines()[-1]
    return code, json.loads(out)


def _touch_db(settings):
    con = sqlite3.connect(settings.runtime_db)
    con.execute("INSERT INTO marker VALUES (1)")
    con.commit()
    con.close()


def test_first_run_of_the_day_writes_r2_and_github_and_never_oci(snapshot_env, capsys):
    code, result = _run(snapshot_env, "--skip-if-unchanged", "--github-daily", capsys=capsys)
    assert code == 0 and result["status"] == "PASS"
    assert set(result["receipts"]) == {"r2", "github"}, "回执里出现了 R2/GitHub 之外的目标"
    assert result["verified_remote_copies"] == 2 and result["required_verified_copies"] == 2
    assert snapshot_env.calls["s3"] == ["r2"]
    assert ["release", "create"] in snapshot_env.calls["gh"]


def test_later_runs_the_same_day_only_write_r2(snapshot_env, capsys):
    _run(snapshot_env, "--skip-if-unchanged", "--github-daily", capsys=capsys)
    releases_before = snapshot_env.calls["gh"].count(["release", "create"])
    _touch_db(snapshot_env.settings)
    code, result = _run(snapshot_env, "--skip-if-unchanged", "--github-daily", capsys=capsys)
    assert code == 0 and result["status"] == "PASS"
    assert set(result["receipts"]) == {"r2"}
    assert result["required_verified_copies"] == 1
    assert snapshot_env.calls["gh"].count(["release", "create"]) == releases_before, (
        "当天已经有 GitHub 副本，却又建了一个 Draft Release——每刻钟一个会把仓刷爆"
    )


def test_an_unchanged_database_is_skipped_once_the_days_github_copy_exists(snapshot_env, capsys):
    _run(snapshot_env, "--skip-if-unchanged", "--github-daily", capsys=capsys)
    uploads_before = len(snapshot_env.calls["s3"])
    code, result = _run(snapshot_env, "--skip-if-unchanged", "--github-daily", capsys=capsys)
    assert code == 0 and result.get("skipped") is True and result["reason"] == "RUNTIME_DB_UNCHANGED"
    assert len(snapshot_env.calls["s3"]) == uploads_before


def test_an_unchanged_database_still_gets_todays_github_copy(snapshot_env, capsys):
    """库没变，但当天还欠一份 GitHub 副本时不能跳过——否则「每天一份异地副本」会在库静止的日子里断掉。"""
    _run(snapshot_env, "--skip-if-unchanged", capsys=capsys)          # 只放了 R2
    code, result = _run(snapshot_env, "--skip-if-unchanged", "--github-daily", capsys=capsys)
    assert code == 0 and not result.get("skipped")
    assert set(result["receipts"]) == {"r2", "github"}


def test_a_failed_github_copy_makes_the_daily_run_fail_loudly(snapshot_env, capsys):
    """带 GitHub 的那一轮，R2 成功而 GitHub 失败也必须退非零——定时器才会红，而不是悄悄少一份异地副本。"""
    snapshot_env.state["github_fails"] = True
    code, result = _run(snapshot_env, "--skip-if-unchanged", "--github-daily", capsys=capsys)
    assert code == 4 and result["status"] == "FAIL"
    assert result["receipts"]["github"]["status"] == "failed"


def test_a_failed_r2_copy_fails_the_run_and_skips_github(snapshot_env, capsys):
    snapshot_env.state["r2_fails"] = True
    code, result = _run(snapshot_env, "--skip-if-unchanged", "--github-daily", capsys=capsys)
    assert code == 4
    assert "github" not in result["receipts"], "R2 没验成，GitHub 那一份不该继续（免得两边都是坏的还各自报成功）"


def test_default_configuration_keeps_the_old_r2_plus_oci_standard(monkeypatch, snapshot_env, capsys):
    monkeypatch.delenv(ENV_NAME, raising=False)
    monkeypatch.setattr(snapshot_env.module, "_s3_config", lambda store_id: {"bucket": store_id})
    code, result = _run(snapshot_env, capsys=capsys)
    assert code == 0
    assert set(result["receipts"]) == {"r2", "oci"}
    assert result["required_verified_copies"] == 2


# ——— R2 上旧快照的清理：OCI 退役后改认「GitHub 那条腿是活的」 ———

def _prune_module():
    return _load("prune_r2_backup_replicas")


def _write_manifest(root: Path, stamp: str, github: str | None):
    directory = root / "backups/runtime-db" / stamp
    directory.mkdir(parents=True)
    receipts = {"r2": {"status": "verified"}}
    if github:
        receipts["github"] = {"status": github}
    (directory / "manifest.json").write_text(json.dumps({"receipts": receipts}), encoding="utf-8")


def test_github_copy_freshness_gate(monkeypatch, tmp_path):
    from datetime import datetime, timezone

    module = _prune_module()
    monkeypatch.setenv("SOCIAL_ARCHIVE_DATA_ROOT", str(tmp_path))
    now = datetime(2026, 9, 30, 12, 0, tzinfo=timezone.utc)
    assert module._github_copy_is_fresh(now) is False, "没有任何快照却判 GitHub 副本是活的"

    _write_manifest(tmp_path, "20260930T040000Z", "failed")
    assert module._github_copy_is_fresh(now) is False, "GitHub 副本没验成也算活的"

    _write_manifest(tmp_path, "20260928T040000Z", "verified")
    assert module._github_copy_is_fresh(now) is False, "两天前的 GitHub 副本不该算今天是活的"

    _write_manifest(tmp_path, "20260930T010000Z", "verified")
    assert module._github_copy_is_fresh(now) is True


def test_prune_never_touches_the_only_copy_of_the_facts_backup(monkeypatch, tmp_path, capsys):
    """OCI 退役后 backups/private-database/ 只有 R2 一份——一个都不许删，哪怕过了保留期。"""
    from datetime import datetime, timezone

    module = _prune_module()
    monkeypatch.setenv(ENV_NAME, "r2,github")
    monkeypatch.setenv("SOCIAL_ARCHIVE_DATA_ROOT", str(tmp_path))
    _write_manifest(tmp_path, "20260930T010000Z", "verified")   # GitHub 副本是活的

    old_runtime = "backups/runtime-db/20260901T000000Z/a.age"
    new_runtime = "backups/runtime-db/20260930T000000Z/b.age"
    old_facts = "backups/private-database/20260901T000000Z/a.age"
    keys = [(old_runtime, 10), (new_runtime, 10), (old_facts, 5)]
    deleted: list[str] = []

    class FakeR2:
        def get_paginator(self, _name):
            return SimpleNamespace(paginate=lambda **_k: [{"Contents": [{"Key": k, "Size": s} for k, s in keys]}])

        def delete_object(self, Bucket, Key):
            deleted.append(Key)

    monkeypatch.setattr(module, "_client", lambda store_id: (FakeR2(), "bucket") if store_id == "r2" else (None, None))
    monkeypatch.setattr(sys, "argv", ["prune", "--apply", "--now", "2026-09-30T12:00:00"])
    assert module.main() == 0
    result = json.loads(capsys.readouterr().out)
    assert deleted == [old_runtime], f"删了不该删的：{deleted}"
    assert result["oci_retired"] is True and result["github_copy_fresh"] is True


def test_prune_deletes_nothing_when_the_github_leg_is_not_alive(monkeypatch, tmp_path, capsys):
    module = _prune_module()
    monkeypatch.setenv(ENV_NAME, "r2,github")
    monkeypatch.setenv("SOCIAL_ARCHIVE_DATA_ROOT", str(tmp_path))
    _write_manifest(tmp_path, "20260930T010000Z", "failed")     # 没有已验证的 GitHub 副本
    deleted: list[str] = []

    class FakeR2:
        def get_paginator(self, _name):
            return SimpleNamespace(paginate=lambda **_k: [{"Contents": [
                {"Key": "backups/runtime-db/20260901T000000Z/a.age", "Size": 10},
                {"Key": "backups/runtime-db/20260930T000000Z/b.age", "Size": 10}]}])

        def delete_object(self, Bucket, Key):
            deleted.append(Key)

    monkeypatch.setattr(module, "_client", lambda store_id: (FakeR2(), "bucket") if store_id == "r2" else (None, None))
    monkeypatch.setattr(sys, "argv", ["prune", "--apply", "--now", "2026-09-30T12:00:00"])
    assert module.main() == 0
    result = json.loads(capsys.readouterr().out)
    assert deleted == []
    assert result["skipped_no_verified_replica"][0]["reason"] == "GITHUB_DAILY_COPY_NOT_FRESH"


# ——— 私有库事实冷备：OCI 退役后只写 R2 ———

def test_private_database_backup_is_r2_only_when_oci_is_retired():
    source = (ROOT / "scripts/backup.py").read_text(encoding="utf-8")
    code = "\n".join(l for l in source.splitlines() if not l.lstrip().startswith("#"))
    assert 'oci_config = _s3_config("oci") if oci_enabled() else None' in code
    assert "for store_id, store_config in cold_stores:" in code
    assert 'for store_id in ("r2", "oci")' not in code, "还有写死 OCI 的核对没改"


# ——— systemd：索引快照是独立单元 ———

def test_the_index_snapshot_is_its_own_unit_and_not_chained_behind_anything():
    unit = (ROOT / "deploy/systemd/social-archive-runtime-db-backup.service").read_text(encoding="utf-8")
    timer = (ROOT / "deploy/systemd/social-archive-runtime-db-backup.timer").read_text(encoding="utf-8")
    execs = [l for l in unit.splitlines() if l.startswith("ExecStart=")]
    assert any("backup_runtime_db.py --skip-if-unchanged --github-daily" in l for l in execs)
    assert "Unit=social-archive-runtime-db-backup.service" in timer
    for other in ("social-archive-backup.service", "social-archive-replication.service"):
        text = (ROOT / "deploy/systemd" / other).read_text(encoding="utf-8")
        code = "\n".join(l for l in text.splitlines() if l.startswith("ExecStart="))
        assert "backup_runtime_db.py" not in code, f"{other} 又把索引快照排在自己后面了：前面一失败它就永远轮不到"


def test_no_unit_loads_oci_credentials_any_more():
    for path in (ROOT / "deploy/systemd").glob("*"):
        if path.is_file():
            text = path.read_text(encoding="utf-8")
            assert "oci_access_key_id" not in text and "oci_secret_access_key" not in text, path.name


def test_env_example_declares_the_retired_configuration():
    assert "SOCIAL_ARCHIVE_REPLICA_STORES=r2,github" in (ROOT / ".env.example").read_text(encoding="utf-8")
