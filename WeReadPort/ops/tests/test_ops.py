from __future__ import annotations

import importlib.util
import io
import json
import os
import sqlite3
import subprocess
import sys
import tarfile
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from weread_port_ops.backup import (
    check_snapshot,
    purge_local_snapshots,
    restore_local_snapshot,
    run_backup,
)
from weread_port_ops.cli import selfheal_runtime
from weread_port_ops.config import Settings
from weread_port_ops.db import RuntimeDB
from weread_port_ops.monitor import (
    check_official_source,
    check_site,
    combine_monitor,
    write_atomic_json,
)
from weread_port_ops.private_db import build_fact_batch, sync_daily
from weread_port_ops.sanitize import assert_public_safe, sanitize_public


BUSINESS_LINE_IDS = [
    "public-trust",
    "weread-direct-export",
    "local-import",
    "normalize-export",
    "chatgpt-handoff",
    "release-supply-chain",
    "operations-recovery",
]


def readiness_payload(*, ready: bool = True):
    return {
        "ok": ready,
        "status": "READY" if ready else "NOT_READY",
        "checks": {
            "businessGovernanceContract": {
                "ready": ready,
                "schemaVersion": "1.0.0",
                "errorCodes": [] if ready else ["TEST_FAILURE"],
            }
        },
    }


def version_payload(*, app_version: str = "v0.0.0.1.7", source_version: str = "1.0.4", governance_version: str = "1.0.0"):
    return {
        "appVersion": app_version,
        "sourceSkillVersion": source_version,
        "businessGovernanceSchemaVersion": governance_version,
    }


def public_status_payload(*, operational: bool = True, omit_business_line: str | None = None):
    lines = []
    for line_id in BUSINESS_LINE_IDS:
        if line_id == omit_business_line:
            continue
        state = "READY"
        if line_id in {"weread-direct-export", "release-supply-chain"}:
            state = "NOT_VERIFIED"
        elif line_id == "operations-recovery":
            state = "EXTERNAL"
        lines.append({
            "id": line_id,
            "name": line_id,
            "phase": "Stage 1 / P0",
            "state": state if operational else "BLOCKED",
            "dependsOnAll": [],
            "dependsOnAny": [],
            "reasonCode": "TEST_FIXTURE",
        })
    return {
        "ok": operational,
        "status": "OPERATIONAL" if operational else "DEGRADED",
        "runtimeMode": "production",
        "businessGovernance": {
            "schemaVersion": "1.0.0",
            "graphStatus": "VALID",
            "lines": lines,
        },
        "dataBoundary": {
            "serverSideUserNotePersistence": False,
            "serverSideUserKeyPersistence": False,
            "statusContainsUserContent": False,
            "businessGovernanceContainsUserContent": False,
        },
    }


def load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class OpsTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.settings = Settings.from_env({
            "WEREAD_PORT_STATE_DIR": str(self.root / "state"),
            "WEREAD_PORT_DB_PATH": str(self.root / "state/runtime.sqlite3"),
            "WEREAD_PORT_STATUS_PATH": str(self.root / "status/weread-port.json"),
            "WEREAD_PORT_SITE_URL": "https://status.linzezhang.com",
            "WEREAD_PORT_RETENTION_HOURS": "72",
            "WEREAD_PORT_HTTP_TIMEOUT_SECONDS": "2",
        })
        self.settings.ensure_state_dirs()
        self.db = RuntimeDB(self.settings.db_path)
        self.db.migrate()

    def tearDown(self):
        self.temp.cleanup()

    def test_schema_has_only_operational_fields(self):
        with self.db.connect() as connection:
            tables = ("runtime_events", "health_samples", "outbox", "cursors", "release_state", "backup_state")
            columns = {row[1].lower() for table in tables for row in connection.execute(f"PRAGMA table_info({table})")}
        for forbidden in ("api_key", "credential", "note_text", "book_title", "author", "export_zip", "search_text"):
            self.assertNotIn(forbidden, columns)
        self.assertEqual(self.db.integrity_check(), "ok")

    def test_idempotent_outbox_and_fake_clock_retention(self):
        for _ in range(10):
            self.db.enqueue("release.deployed", {"status": "ok"}, outbox_id="stable")
        self.assertEqual(len(self.db.pending()), 1)
        old = datetime(2025, 1, 1, tzinfo=timezone.utc)
        self.db.record_event("health", "degraded", {"errorCode": "TEST"}, occurred_at=old, event_id="old")
        deleted = self.db.purge_before(old + timedelta(hours=1))
        self.assertEqual(deleted["runtimeEvents"], 1)
        self.assertEqual(len(self.db.pending()), 1)

    def test_public_sanitizer_redacts_credentials_and_content(self):
        candidate = "wrk-" + ("a" * 24)
        bearer = "Bearer " + ("b" * 24)
        value = sanitize_public({"apiKey": candidate, "noteText": "private", "safe": bearer})
        assert_public_safe(value)
        encoded = json.dumps(value)
        self.assertNotIn("a" * 24, encoded)
        self.assertNotIn("private", encoded)
        self.assertNotIn("b" * 24, encoded)

    def test_monitor_and_official_source_are_combined_without_waiting(self):
        def site_fetcher(url: str, timeout: float):
            del timeout
            if url.endswith("/healthz"):
                return 200, {"ok": True, "status": "ALIVE"}, 1.0
            if url.endswith("/readyz"):
                return 200, readiness_payload(), 2.0
            if url.endswith("/api/status"):
                return 200, public_status_payload(), 3.0
            return 200, version_payload(), 4.0

        def source_fetcher(url: str, timeout: float):
            del url, timeout
            return 200, "---\nname: weread-skills\nversion: 1.0.4\n---\n", 2.0

        at = datetime(2026, 7, 26, 1, 2, 3, tzinfo=timezone.utc)
        site = check_site(self.settings, fetcher=site_fetcher, at=at)
        source = check_official_source(self.settings, fetcher=source_fetcher, at=at)
        payload = combine_monitor(site, source)
        self.assertEqual(payload["status"], "operational")
        self.assertEqual(payload["productPlane"]["latencyMs"], 10.0)
        self.assertEqual(payload["officialSource"]["observedVersion"], "1.0.4")
        self.assertTrue(payload["productPlane"]["businessGovernanceOk"])
        self.assertEqual(len(payload["businessLines"]), 7)
        write_atomic_json(self.settings.status_path, payload)
        written = json.loads(self.settings.status_path.read_text(encoding="utf-8"))
        self.assertEqual(written["status"], "operational")
        assert_public_safe(written)

    def test_version_drift_is_degraded_immediately(self):
        def fetcher(url: str, timeout: float):
            del timeout
            if url.endswith("/healthz"):
                return 200, {"ok": True, "status": "ALIVE"}, 1.0
            if url.endswith("/readyz"):
                return 200, readiness_payload(), 1.0
            if url.endswith("/api/status"):
                return 200, public_status_payload(), 1.0
            return 200, version_payload(app_version="0.0.0.0", source_version="0.0.0"), 1.0

        payload = check_site(self.settings, fetcher=fetcher)
        self.assertEqual(payload["status"], "degraded")
        self.assertEqual(payload["productPlane"]["errorCode"], "VERSION_CONTRACT_FAILED")


    def test_business_governance_version_schema_drift_degrades_immediately(self):
        def fetcher(url: str, timeout: float):
            del timeout
            if url.endswith("/healthz"):
                return 200, {"ok": True, "status": "ALIVE"}, 1.0
            if url.endswith("/readyz"):
                return 200, readiness_payload(), 1.0
            if url.endswith("/api/status"):
                return 200, public_status_payload(), 1.0
            return 200, version_payload(governance_version="9.9.9"), 1.0

        payload = check_site(self.settings, fetcher=fetcher)
        self.assertEqual(payload["status"], "degraded")
        self.assertEqual(payload["productPlane"]["errorCode"], "VERSION_CONTRACT_FAILED")


    def test_readiness_or_public_status_failure_degrades_even_when_liveness_and_version_pass(self):
        def fetcher(url: str, timeout: float):
            del timeout
            if url.endswith("/healthz"):
                return 200, {"ok": True, "status": "ALIVE"}, 1.0
            if url.endswith("/readyz"):
                return 503, readiness_payload(ready=False), 1.0
            if url.endswith("/api/status"):
                return 503, public_status_payload(operational=False), 1.0
            return 200, version_payload(), 1.0

        payload = check_site(self.settings, fetcher=fetcher)
        self.assertEqual(payload["status"], "degraded")
        self.assertTrue(payload["productPlane"]["livenessOk"])
        self.assertFalse(payload["productPlane"]["readinessOk"])
        self.assertFalse(payload["productPlane"]["publicStatusOk"])
        self.assertEqual(payload["productPlane"]["errorCode"], "READINESS_CONTRACT_FAILED")


    def test_business_governance_missing_line_degrades_fail_closed(self):
        def fetcher(url: str, timeout: float):
            del timeout
            if url.endswith("/healthz"):
                return 200, {"ok": True, "status": "ALIVE"}, 1.0
            if url.endswith("/readyz"):
                return 200, readiness_payload(), 1.0
            if url.endswith("/api/status"):
                return 200, public_status_payload(omit_business_line="operations-recovery"), 1.0
            return 200, version_payload(), 1.0

        payload = check_site(self.settings, fetcher=fetcher)
        self.assertEqual(payload["status"], "degraded")
        self.assertFalse(payload["productPlane"]["businessGovernanceOk"])
        self.assertEqual(payload["productPlane"]["errorCode"], "BUSINESS_GOVERNANCE_CONTRACT_FAILED")
        self.assertEqual(payload["businessLines"], [])

    def test_snapshot_backup_verify_and_explicit_restore(self):
        self.db.record_event("release", "ok", {"commit": "abc"}, event_id="event")
        result = run_backup(self.settings, self.db, at=datetime(2026, 7, 26, tzinfo=timezone.utc))
        snapshot = Path(result["localRuntimeSnapshot"])
        self.assertTrue(snapshot.is_file())
        self.assertEqual(result["r2Status"], "not_configured")
        self.assertEqual(check_snapshot(snapshot)["sqliteIntegrity"], "ok")
        with self.db.connect() as connection:
            connection.execute("DELETE FROM runtime_events")
        planned = restore_local_snapshot(self.settings, self.db, snapshot)
        self.assertEqual(planned["status"], "verified_not_applied")
        with self.db.connect() as connection:
            self.assertEqual(connection.execute("SELECT COUNT(*) FROM runtime_events").fetchone()[0], 0)
        restored = restore_local_snapshot(self.settings, self.db, snapshot, apply=True)
        self.assertEqual(restored["status"], "restored")
        with self.db.connect() as connection:
            self.assertEqual(connection.execute("SELECT COUNT(*) FROM runtime_events").fetchone()[0], 1)

    def test_canonical_private_database_backup_to_r2_and_oci_is_idempotent(self):
        commit = "a" * 40
        commands: list[list[str]] = []

        def runner(command, **kwargs):
            del kwargs
            commands.append(command)
            if command[:3] == ["gh", "api", "repos/LinzeColin/Private-Database/commits/main"]:
                return subprocess.CompletedProcess(command, 0, commit + "\n", "")
            if command[0] == "restic":
                return subprocess.CompletedProcess(command, 0, '{"message_type":"summary"}\n', "")
            if command[0] == "rclone":
                return subprocess.CompletedProcess(command, 0, "copied", "")
            raise AssertionError(command)

        def archive_fetcher(observed_commit: str, output: Path):
            self.assertEqual(observed_commit, commit)
            payload = b'{"service":"weread-port"}\n'
            with tarfile.open(output, "w:gz") as archive:
                info = tarfile.TarInfo("Private-Database-test/facts/release.json")
                info.size = len(payload)
                archive.addfile(info, io.BytesIO(payload))
            return subprocess.CompletedProcess(["gh", "api", "tarball"], 0, "", "")

        settings = Settings(**{
            **self.settings.__dict__,
            "restic_repository": "s3:https://r2.example.invalid/private-database",
            "r2_remote": "r2:private-database",
            "oci_remote": "oci:private-database",
        })
        tool_lookup = lambda name: f"/usr/bin/{name}"  # noqa: E731
        before = len(self.db.pending())
        first = run_backup(
            settings,
            self.db,
            at=datetime(2026, 7, 26, tzinfo=timezone.utc),
            runner=runner,
            archive_fetcher=archive_fetcher,
            tool_lookup=tool_lookup,
        )
        self.assertEqual(first["r2Status"], "stored")
        self.assertEqual(first["ociStatus"], "replicated")
        self.assertEqual(first["privateDatabaseCommit"], commit)
        self.assertEqual(len(self.db.pending()), before, "routine backup must not create a backup→fact→commit loop")

        second = run_backup(
            settings,
            self.db,
            at=datetime(2026, 7, 26, 1, tzinfo=timezone.utc),
            runner=runner,
            archive_fetcher=archive_fetcher,
            tool_lookup=tool_lookup,
        )
        self.assertEqual(second["r2Status"], "unchanged")
        self.assertEqual(second["ociStatus"], "unchanged")
        self.assertEqual(len([cmd for cmd in commands if cmd and cmd[0] == "restic"]), 1)
        self.assertEqual(len([cmd for cmd in commands if cmd and cmd[0] == "rclone"]), 1)

    def test_restore_refuses_corrupt_snapshot_without_touching_live_db(self):
        self.db.record_event("before", "ok", {}, event_id="before")
        corrupt = self.root / "corrupt.sqlite3"
        corrupt.write_bytes(b"broken")
        with self.assertRaises(sqlite3.DatabaseError):
            restore_local_snapshot(self.settings, self.db, corrupt, apply=True)
        self.assertEqual(self.db.integrity_check(), "ok")
        with self.db.connect() as connection:
            self.assertEqual(connection.execute("SELECT COUNT(*) FROM runtime_events").fetchone()[0], 1)

    def test_selfheal_quarantines_corrupt_rebuildable_runtime_and_recovers(self):
        self.settings.db_path.write_bytes(b"not-a-sqlite-database")
        recovered, result = selfheal_runtime(self.settings, at=datetime(2026, 7, 26, tzinfo=timezone.utc))
        self.assertEqual(result["status"], "recovered")
        self.assertEqual(result["integrity"], "ok")
        self.assertEqual(recovered.integrity_check(), "ok")
        self.assertTrue(result["quarantined"])
        for path in result["quarantined"]:
            self.assertTrue(Path(path).is_file())

    def test_local_snapshot_retention_is_bounded_by_fake_clock(self):
        snapshots = self.settings.state_dir / "snapshots"
        snapshots.mkdir(parents=True, exist_ok=True)
        old = snapshots / "runtime-20250101T000000Z.sqlite3"
        recent = snapshots / "runtime-20260726T000000Z.sqlite3"
        old.write_bytes(b"old")
        recent.write_bytes(b"recent")
        cutoff = datetime(2026, 7, 25, tzinfo=timezone.utc)
        os.utime(old, (cutoff.timestamp() - 1, cutoff.timestamp() - 1))
        os.utime(recent, (cutoff.timestamp() + 1, cutoff.timestamp() + 1))
        self.assertEqual(purge_local_snapshots(self.settings, cutoff), 1)
        self.assertFalse(old.exists())
        self.assertTrue(recent.exists())

    def test_private_database_ingest_is_exact_retry_stable_and_idempotent(self):
        seen: list[list[str]] = []
        payloads: list[dict[str, object]] = []

        def runner(command, **kwargs):
            del kwargs
            seen.append(command)
            if command[-1] == "--help":
                return subprocess.CompletedProcess(command, 0, "commands: ingest get list verify put", "")
            self.assertEqual(command[2], "ingest")
            payload = json.loads(Path(command[4]).read_text(encoding="utf-8"))
            assert_public_safe(payload)
            payloads.append(payload)
            return subprocess.CompletedProcess(command, 0, "ok", "")

        client = self.root / "private_db_client.py"
        client.write_text("# capture-double\n", encoding="utf-8")
        settings = Settings(**{**self.settings.__dict__, "private_db_client": client})
        fake_now = datetime(2026, 7, 26, tzinfo=timezone.utc)
        self.db.enqueue("service.status.changed", {"to": "degraded"}, outbox_id="status-change", at=fake_now)
        first_batch = build_fact_batch(self.db)
        self.assertEqual(first_batch, build_fact_batch(self.db), "same pending rows must produce the same bytes")
        result = sync_daily(settings, self.db, at=datetime(2026, 7, 26, tzinfo=timezone.utc), runner=runner)
        self.assertEqual(result["status"], "delivered")
        self.assertEqual(result["mode"], "ingest")
        ingest = seen[-1]
        self.assertEqual(first_batch["date"], datetime(2026, 7, 26, tzinfo=timezone.utc).date().isoformat())
        self.assertEqual(ingest[:4], ["python3", str(client), "ingest", "Private-MetaDatabase"])
        self.assertEqual(ingest[5:], ["--domain", "weread-port-operations", "--batch", first_batch["date"]])
        self.assertEqual(payloads[0]["batchId"], first_batch["batchId"])
        self.assertEqual(len(self.db.pending()), 0)
        self.assertEqual(sync_daily(settings, self.db, at=datetime(2026, 7, 26, tzinfo=timezone.utc), runner=runner)["status"], "idle")

    def test_release_state_preserves_previous_version(self):
        self.db.set_release(commit="a", saved_version="s1", production_version="p1", production_origin="https://status.linzezhang.com")
        self.db.set_release(commit="b", saved_version="s2", production_version="p2", production_origin="https://status.linzezhang.com")
        state = self.db.release()
        self.assertEqual(state["current_commit"], "b")
        self.assertEqual(state["previous_commit"], "a")
        self.assertEqual(state["previous_production_version"], "p1")

    def test_legacy_v5_schema_migrates_without_user_data(self):
        legacy_path = self.root / "legacy.sqlite3"
        connection = sqlite3.connect(legacy_path)
        connection.executescript(
            """
            CREATE TABLE outbox(outbox_id TEXT PRIMARY KEY,aggregate_type TEXT,aggregate_id TEXT,payload_json TEXT,created_at TEXT,attempts INTEGER,next_attempt_at TEXT,delivered_at TEXT,last_error_code TEXT);
            INSERT INTO outbox VALUES('x','release','v5','{}','2026-07-01T00:00:00Z',1,'2026-07-01T00:00:00Z',NULL,'');
            CREATE TABLE runtime_event(event_id TEXT PRIMARY KEY,occurred_at TEXT,kind TEXT,status TEXT,summary TEXT,details_json TEXT,synced_at TEXT);
            INSERT INTO runtime_event VALUES('e','2026-07-01T00:00:00Z','diagnostic','ok','legacy','{}',NULL);
            """
        )
        connection.commit()
        connection.close()
        migrated = RuntimeDB(legacy_path)
        migrated.migrate()
        with migrated.connect() as connection:
            self.assertEqual(connection.execute("SELECT topic FROM outbox WHERE outbox_id='x'").fetchone()[0], "release")
            self.assertEqual(connection.execute("SELECT event_type FROM runtime_events WHERE event_id='e'").fetchone()[0], "diagnostic")
        self.assertEqual(migrated.integrity_check(), "ok")

    def test_status_adapter_patch_is_idempotent_and_reversible(self):
        install = load_module("status_install", ROOT / "status/install_status_adapter.py")
        remove = load_module("status_remove", ROOT / "status/remove_status_adapter.py")
        source = (
            "import json\nimport os\n\n"
            "PROJECTS = []\n\n"
            "# ---------- 项目实时状态 ----------\n"
            "def projects_live():\n"
            "    rows=[]\n"
            "    for p in PROJECTS:\n"
            "        rows.append(p)\n"
            "    return rows\n"
        )
        patched = install.patch_text(source)
        self.assertIn("external_project_adapters", patched)
        self.assertEqual(install.patch_text(patched), patched)
        import re
        pattern = re.compile(rf"{re.escape(remove.BEGIN)}.*?{re.escape(remove.END)}\n?", re.DOTALL)
        restored = pattern.sub("", patched, count=1).replace(
            "for p in PROJECTS + external_project_adapters():", "for p in PROJECTS:", 1
        )
        compile(restored, "collect.py", "exec")
        self.assertEqual(restored, source)

    def test_monitor_unit_invokes_reconcile_not_fragile_monitor_only(self):
        unit = (ROOT / "systemd/weread-port-ops-monitor.service").read_text(encoding="utf-8")
        self.assertIn("weread-port-ops reconcile", unit)
        self.assertNotIn("weread-port-ops monitor\n", unit)

    def test_ops_installer_prepares_versioned_release_in_synthetic_root(self):
        install = ROOT / "install_ops.py"
        fake_root = self.root / "host"
        result = subprocess.run(
            [sys.executable, str(install), "--root", str(fake_root), "--site-url", "https://status.linzezhang.com"],
            capture_output=True,
            text=True,
            timeout=30,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        payload = json.loads(result.stdout)
        self.assertEqual(payload["status"], "prepared")
        current = fake_root / "opt/weread-port-ops/current"
        self.assertTrue(current.is_symlink())
        self.assertTrue((fake_root / "opt/weread-port-ops/releases/0.0.0.1.7/bin/weread-port-ops").is_file())
        env = (fake_root / "etc/weread-port/ops.env").read_text(encoding="utf-8")
        self.assertIn("WEREAD_PORT_SITE_URL=https://status.linzezhang.com", env)
        adapter = fake_root / "srv/linze/apps/status/data/external-projects/weread-port.json"
        self.assertTrue(os.path.lexists(adapter))
        repeat = subprocess.run(
            [sys.executable, str(install), "--root", str(fake_root), "--site-url", "https://status.linzezhang.com"],
            capture_output=True,
            text=True,
            timeout=30,
        )
        self.assertEqual(repeat.returncode, 0, repeat.stderr)


if __name__ == "__main__":
    unittest.main()
