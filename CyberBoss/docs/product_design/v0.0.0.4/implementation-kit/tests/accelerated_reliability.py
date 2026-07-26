#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import sqlite3
import tempfile
from pathlib import Path


def digest_rows(conn: sqlite3.Connection) -> str:
    h = hashlib.sha256()
    for table, cols in (
        ("inbox_messages", "id,source_message_id,status,payload_sha256"),
        ("jobs", "id,correlation_id,status,state_version,input_sha256"),
        ("outbox_messages", "id,dedupe_key,status,attempt_count,payload_sha256"),
    ):
        for row in conn.execute(f"SELECT {cols} FROM {table} ORDER BY 1"):
            h.update(json.dumps(row, separators=(",", ":"), ensure_ascii=False).encode())
            h.update(b"\n")
    return h.hexdigest()


def open_db(path: Path) -> sqlite3.Connection:
    conn = sqlite3.connect(path)
    conn.execute("PRAGMA foreign_keys=ON")
    conn.execute("PRAGMA busy_timeout=5000")
    return conn


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--schema", required=True, type=Path)
    parser.add_argument("--replays", type=int, default=1000)
    parser.add_argument("--restarts", type=int, default=100)
    parser.add_argument("--send-faults", type=int, default=100)
    parser.add_argument("--restore-cycles", type=int, default=20)
    args = parser.parse_args()
    for name in ("replays", "restarts", "send_faults", "restore_cycles"):
        if getattr(args, name) < 1:
            raise SystemExit(f"{name} must be >= 1")

    with tempfile.TemporaryDirectory(prefix="cyberboss-accelerated-") as td:
        root = Path(td)
        db = root / "runtime.db"
        conn = open_db(db)
        conn.executescript(args.schema.read_text(encoding="utf-8"))

        # Replays: ten unique source messages repeatedly presented. UNIQUE + transactional job creation
        # must leave one inbox and one job per unique source message.
        unique_messages = 10
        for i in range(args.replays):
            u = i % unique_messages
            inbox_id = f"inbox-{u}"
            correlation_id = f"corr-{u}"
            payload_hash = hashlib.sha256(f"message-{u}".encode()).hexdigest()
            with conn:
                conn.execute(
                    """INSERT OR IGNORE INTO inbox_messages
                    (id,source,source_account_hash,source_message_id,correlation_id,user_ref_hash,message_type,
                     payload_sha256,status,received_at,durable_at)
                    VALUES (?,?,?,?,?,?, 'text',?,'accepted','2026-07-26T00:00:00Z','2026-07-26T00:00:00Z')""",
                    (inbox_id, "weixin", "acct-hash", f"source-{u}", correlation_id, "user-hash", payload_hash),
                )
                conn.execute(
                    """INSERT OR IGNORE INTO jobs
                    (id,correlation_id,inbox_id,workspace_alias,runtime,operation_class,status,input_sha256,
                     created_at,updated_at)
                    VALUES (?,?,?,'cyberboss','codex','read_only','queued',?,
                            '2026-07-26T00:00:00Z','2026-07-26T00:00:00Z')""",
                    (f"job-{u}", correlation_id, inbox_id, payload_hash),
                )
        inbox_count = conn.execute("SELECT COUNT(*) FROM inbox_messages").fetchone()[0]
        job_count = conn.execute("SELECT COUNT(*) FROM jobs").fetchone()[0]
        assert inbox_count == unique_messages, (inbox_count, unique_messages)
        assert job_count == unique_messages, (job_count, unique_messages)

        # Transaction cut: an exception before commit must not persist a cursor/message fragment.
        try:
            conn.execute("BEGIN IMMEDIATE")
            conn.execute(
                """INSERT INTO inbox_messages
                (id,source,source_account_hash,source_message_id,correlation_id,user_ref_hash,message_type,
                 payload_sha256,status,received_at,durable_at)
                VALUES ('cut-inbox','weixin','acct-hash','cut-source','cut-corr','user-hash','text',
                        'cut-hash','accepted','2026-07-26T00:00:00Z','2026-07-26T00:00:00Z')"""
            )
            raise RuntimeError("injected crash before commit")
        except RuntimeError:
            conn.rollback()
        assert conn.execute("SELECT COUNT(*) FROM inbox_messages WHERE id='cut-inbox'").fetchone()[0] == 0

        # Send faults update one durable outbox row. Repeated attempts must never create a second dedupe key.
        with conn:
            conn.execute(
                """INSERT INTO outbox_messages
                (id,job_id,correlation_id,target_type,dedupe_key,message_kind,payload_ciphertext,payload_sha256,
                 status,created_at,updated_at)
                VALUES ('out-0','job-0','corr-0','weixin','job-0:terminal','result',X'01','out-hash',
                        'pending','2026-07-26T00:00:00Z','2026-07-26T00:00:00Z')"""
            )
        for attempt in range(1, args.send_faults + 1):
            with conn:
                conn.execute(
                    """UPDATE outbox_messages SET status='retry',attempt_count=?,last_error_class='injected',
                    updated_at='2026-07-26T00:00:00Z' WHERE dedupe_key='job-0:terminal'""",
                    (attempt,),
                )
                conn.execute(
                    """INSERT OR IGNORE INTO outbox_messages
                    (id,job_id,correlation_id,target_type,dedupe_key,message_kind,payload_ciphertext,payload_sha256,
                     status,created_at,updated_at)
                    VALUES (?,?,?,?,?,?,?,?,?,?,?)""",
                    (f"duplicate-{attempt}", "job-0", "corr-0", "weixin", "job-0:terminal", "result", b"x", "out-hash", "retry", "2026-07-26T00:00:00Z", "2026-07-26T00:00:00Z"),
                )
        with conn:
            conn.execute(
                """UPDATE outbox_messages SET status='confirmed',confirmed_at='2026-07-26T00:00:00Z',
                provider_receipt_hash='receipt-hash' WHERE dedupe_key='job-0:terminal'"""
            )
        assert conn.execute("SELECT COUNT(*) FROM outbox_messages WHERE dedupe_key='job-0:terminal'").fetchone()[0] == 1

        baseline_digest = digest_rows(conn)
        conn.close()

        # Process restart loop: close/open is the durable-state boundary; no elapsed-time wait is used.
        for _ in range(args.restarts):
            conn = open_db(db)
            assert conn.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
            assert digest_rows(conn) == baseline_digest
            conn.close()

        # Isolated online-backup/restore cycles.
        restore_mismatches = 0
        for cycle in range(args.restore_cycles):
            source = open_db(db)
            restored_path = root / f"restore-{cycle}.db"
            target = open_db(restored_path)
            source.backup(target)
            source.close()
            target.close()
            restored = open_db(restored_path)
            if restored.execute("PRAGMA integrity_check").fetchone()[0] != "ok" or digest_rows(restored) != baseline_digest:
                restore_mismatches += 1
            restored.close()
            restored_path.unlink()

        assert restore_mismatches == 0
        print(
            "ACCELERATED_RELIABILITY=PASS "
            f"replays={args.replays} unique_messages={unique_messages} duplicate_executions=0 "
            f"restarts={args.restarts} send_faults={args.send_faults} duplicate_terminal_replies=0 "
            f"restore_cycles={args.restore_cycles} restore_mismatches=0 digest={baseline_digest}"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
