"""The sync and the cold backup must see EVERY completed content, not the oldest 100.

Production regression (2026-09-30): 211 completed contents, 130 delivered, 81 never
delivered -- and every sync run printed NO_CHANGE, because the candidate list was
``ORDER BY last_observed_at ASC LIMIT 100`` and those same 100 oldest were all
already delivered.  The backup had the same window.
"""
from __future__ import annotations

import hashlib
import importlib.util
import json
import math
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace

from social_archive.db import CompletedScanProgress
from social_archive.encryption import EncryptedObject
from social_archive.private_facts import (
    PRIVATE_DATABASE_EVENT,
    completed_content_facts,
    delivered_completed_content_facts,
    fact_sha256,
    iter_completed_content_facts,
)

ROOT = Path(__file__).resolve().parents[2]
_BASE = datetime(2026, 1, 1, tzinfo=timezone.utc)


def _load(script: str, name: str):
    spec = importlib.util.spec_from_file_location(name, ROOT / "scripts" / script)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader
    spec.loader.exec_module(module)
    return module


def _seed(store, count: int, *, start: int = 0, same_instant: bool = False) -> list[str]:
    """Insert ``count`` fully replicated contents; index i is i seconds after the base instant."""
    ids: list[str] = []
    with store.connection() as con:
        for i in range(start, start + count):
            cid = f"content-{i:05d}"
            seen = (_BASE + timedelta(seconds=0 if same_instant else i)).isoformat()
            con.execute(
                """INSERT INTO content(id,platform,external_content_id,canonical_url,title,
                                       first_observed_at,last_observed_at)
                   VALUES(?,?,?,?,?,?,?)""",
                (cid, "generic-web", f"ext-{i}", f"https://example.test/{i}", f"title {i}", seen, seen),
            )
            con.execute(
                """INSERT INTO artifact(id,content_id,archive_level,artifact_type,sha256,byte_size,created_at,status)
                   VALUES(?,?,?,?,?,?,?,'complete')""",
                (f"artifact-{i:05d}", cid, "L0", "snapshot", f"{i:064x}", 1, seen),
            )
            ids.append(cid)
    return ids


def _deliver(store, facts) -> None:
    for fact in facts:
        event = store.ensure_outbox_event(
            event_type=PRIVATE_DATABASE_EVENT, aggregate_id=str(fact["content"]["id"]), payload=fact,
        )
        store.mark_outbox_delivered(event["id"])


def _deliver_oldest(store, count: int) -> list[str]:
    facts = completed_content_facts(store, limit=count)
    _deliver(store, facts)
    return [f["content"]["id"] for f in facts]


def _sync_module(monkeypatch, settings, tmp_path, argv: list[str]):
    module = _load("sync_private_database.py", "sync_all_completed_test_module")
    client = tmp_path / "private_db_client.py"
    client.write_text("# fixture only\n", encoding="utf-8")
    token = tmp_path / "private_database_token"
    token.write_text("private-database-fixture-token\n", encoding="utf-8")
    token.chmod(0o600)
    monkeypatch.setenv("SOCIAL_ARCHIVE_PRIVATE_DB_CLIENT", str(client))
    monkeypatch.setenv("SOCIAL_ARCHIVE_PRIVATE_DB_TOKEN_FILE", str(token))
    monkeypatch.setattr(module, "Settings", SimpleNamespace(from_env=lambda: settings))
    ingested: list[str] = []

    def fake_run(_client, args):
        if args[0] == "ingest":
            ingested.append(json.loads(Path(args[2]).read_text(encoding="utf-8"))["content"]["id"])
            return 0, ""
        return 0, "Private-MetaDatabase: 账本 1 条，对象在仓 1，缺 0"

    monkeypatch.setattr(module, "_run_client", fake_run)
    monkeypatch.setattr(sys, "argv", ["sync_private_database.py", *argv])
    return module, ingested


def _run(module, capsys) -> dict:
    code = module.main()
    report = json.loads(capsys.readouterr().out)
    assert code == (0 if report["status"] in {"PASS", "NO_CHANGE", "READY"} else 4), report
    return report


# ── (a) ────────────────────────────────────────────────────────────────────
def test_the_150_contents_beyond_the_oldest_100_are_picked_up_and_delivered(
    monkeypatch, store, settings, tmp_path, capsys
):
    ids = _seed(store, 250)
    assert _deliver_oldest(store, 100) == ids[:100]

    dry, _ = _sync_module(monkeypatch, settings, tmp_path, ["--dry-run"])
    before = _run(dry, capsys)
    assert before["completed_total"] == 250
    assert before["already_delivered_count"] == 100
    assert before["pending_total"] == 150
    assert before["would_deliver_this_run"] == 100

    module, ingested = _sync_module(monkeypatch, settings, tmp_path, ["--once"])
    report = _run(module, capsys)
    assert report["status"] == "PASS"
    assert report["completed_total"] == 250
    assert report["pending_before_run"] == 150
    assert report["delivered_this_run"] == 100
    assert report["pending_total"] == 50
    assert ingested == ids[100:200], "the oldest of the never-delivered come first"
    assert report["candidate_fact_count"] == 250, "the whole archive was scanned, not 100 rows"


# ── (b) ────────────────────────────────────────────────────────────────────
def test_limit_40_drains_the_backlog_in_ceil_150_over_40_rounds_without_repeats(
    monkeypatch, store, settings, tmp_path, capsys
):
    ids = _seed(store, 250)
    _deliver_oldest(store, 100)
    module, ingested = _sync_module(monkeypatch, settings, tmp_path, ["--once", "--limit", "40"])

    rounds = math.ceil(150 / 40)
    reports = [_run(module, capsys) for _ in range(rounds)]
    assert [r["delivered_this_run"] for r in reports] == [40, 40, 40, 30]
    assert [r["pending_total"] for r in reports] == [110, 70, 30, 0]
    assert reports[-1]["pending_total"] == 0
    assert len(ingested) == 150 and len(set(ingested)) == 150, "no fact is delivered twice"
    assert ingested == ids[100:], "oldest first, across rounds"

    after = _run(module, capsys)
    assert after["status"] == "NO_CHANGE"
    assert after["pending_total"] == 0 and after["completed_total"] == 250
    assert len(ingested) == 150


# ── (c) ────────────────────────────────────────────────────────────────────
def test_changed_after_delivery_is_redelivered_but_after_the_never_delivered(
    monkeypatch, store, settings, tmp_path, capsys
):
    ids = _seed(store, 10)
    _deliver_oldest(store, 10)
    # The OLDEST already-delivered content changes, then three brand-new ones complete.
    with store.connection() as con:
        con.execute("UPDATE content SET title='edited after delivery' WHERE id=?", (ids[0],))
    new_ids = _seed(store, 3, start=10)

    module, ingested = _sync_module(monkeypatch, settings, tmp_path, ["--once", "--limit", "2"])
    first = _run(module, capsys)
    assert first["pending_before_run"] == 4
    assert first["never_delivered_count"] == 3 and first["changed_since_delivery_count"] == 1
    assert ingested == new_ids[:2], "never-delivered beat the older-but-changed one"
    assert first["pending_total"] == 2

    second = _run(module, capsys)
    assert ingested[2:] == [new_ids[2], ids[0]], "the changed content follows the last never-delivered"
    assert second["pending_total"] == 0
    changed = next(f for f in completed_content_facts(store, limit=1) if f["content"]["id"] == ids[0])
    assert changed["content"]["title"] == "edited after delivery"
    event = store.get_outbox_event(
        event_type=PRIVATE_DATABASE_EVENT, aggregate_id=ids[0], payload_sha256=fact_sha256(changed),
    )
    assert event and event["status"] == "delivered"
    assert _run(module, capsys)["status"] == "NO_CHANGE"


# ── (d) ────────────────────────────────────────────────────────────────────
def test_backup_covers_delivered_facts_beyond_the_oldest_100(monkeypatch, store, settings, tmp_path, capsys):
    from dataclasses import replace

    _seed(store, 250)
    _deliver(store, list(iter_completed_content_facts(store)))
    assert len(delivered_completed_content_facts(store)) == 250

    module = _load("backup.py", "backup_all_completed_test_module")
    monkeypatch.setattr(
        module, "Settings", SimpleNamespace(from_env=lambda: replace(settings, age_recipient="age1testrecipient"))
    )

    class FakeEncryptor:
        def __init__(self, *, recipient, root, **_kwargs):
            self.root = root
            self.root.mkdir(parents=True, exist_ok=True)

        recipient_fingerprint = "fixture-recipient"

        def encrypt(self, obj):
            path = self.root / "fixture.age"
            path.write_bytes(b"fixture:" + obj.path.read_bytes())
            return EncryptedObject(
                original_sha256=obj.sha256, cipher_sha256=hashlib.sha256(path.read_bytes()).hexdigest(),
                original_byte_size=obj.byte_size, cipher_byte_size=path.stat().st_size,
                path=path, media_type=obj.media_type,
            )

    monkeypatch.setattr(module, "AgeEncryptor", FakeEncryptor)
    monkeypatch.setattr(module.shutil, "which", lambda _name: "/fixture/age")
    monkeypatch.setattr(module, "_s3_config", lambda sid: {"id": sid, "endpoint": "x", "bucket": "b", "access": "a", "secret": "s"})
    monkeypatch.setattr(module, "_upload_and_verify", lambda c, ct, key, enc, _r: {"status": "verified", "object_key": key})
    monkeypatch.setattr(module, "_upload_recovery_descriptor_and_verify", lambda c, d, k: {"status": "verified"})
    output = tmp_path / "cold"
    monkeypatch.setattr(sys, "argv", ["backup.py", "--once", "--output", str(output)])

    assert module.main() == 0
    report = json.loads(capsys.readouterr().out)
    assert report["status"] == "PASS"
    assert report["fact_count"] == 250 and report["completed_total"] == 250
    assert report["scan_truncated_count"] == 0
    manifest = json.loads((output / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["fact_count"] == 250 and len(manifest["fact_sha256s"]) == 250


# ── store-level guarantees ─────────────────────────────────────────────────
def test_keyset_paging_visits_each_content_once_even_when_timestamps_tie(store):
    ids = _seed(store, 23, same_instant=True)
    progress = CompletedScanProgress()
    seen = [b["id"] for b in store.iter_completed_content_bundles(batch_size=5, progress=progress)]
    assert seen == ids
    assert progress.scanned == 23 and progress.completed_total == 23 and not progress.truncated


def test_a_truncated_scan_says_how_much_it_left_out(store, settings, monkeypatch, tmp_path, capsys):
    _seed(store, 12)
    progress = CompletedScanProgress()
    assert len(list(store.iter_completed_content_bundles(batch_size=5, max_scan=7, progress=progress))) == 7
    assert progress.truncated and progress.truncated_count == 5 and progress.scanned == 7

    exact = CompletedScanProgress()
    assert len(list(store.iter_completed_content_bundles(batch_size=5, max_scan=12, progress=exact))) == 12
    assert not exact.truncated and exact.truncated_count == 0

    module, _ = _sync_module(monkeypatch, settings, tmp_path, ["--dry-run"])
    monkeypatch.setattr(
        module, "plan_sync",
        lambda s, limit: __import__("social_archive.private_facts", fromlist=["plan_sync"]).plan_sync(s, limit=limit, max_scan=7),
    )
    report = _run(module, capsys)
    assert report["scan_truncated_count"] == 5 and "另有 5 条" in report["message"]
