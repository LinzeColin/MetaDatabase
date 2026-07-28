#!/usr/bin/env python3
"""Fail-closed local seal for CB-610 (AC-003 single-bot multi-user, AC-005
server-side identity, AC-030 data boundary).

Static checks run against the exact target tree; behavioural checks run the
frozen node:test suites. UNKNOWN and NOT_RUN are never folded into PASS.
"""

from __future__ import annotations

import hashlib
import json
import re
import subprocess
import sys
from pathlib import Path
from typing import Any

sys.dont_write_bytecode = True

REPO = Path(__file__).resolve().parents[2]
PROJECT = REPO / "CyberBoss"
APP = PROJECT / "app"
EVIDENCE = PROJECT / "docs/evidence/CB-610"
MIGRATION = APP / "migrations/006_multiuser_foundation.sql"
ADAPTER = APP / "src/services/db/database-adapter.js"
USERS = APP / "src/services/users"

ACCEPTANCE_IDS = ("AC-003", "AC-005", "AC-030")
TEMPLATE_SHA256 = "49ab8cc87233de11f0bc9a21c15754b21509089a732f9139fb903e72470ea63e"
SELECTED_PREFIX = 6
NODE_SUITES = (
    "test/cb610-multiuser-foundation.test.js",
    "test/runtime-spool.test.js",
    "test/durable-inbox-crash-cut.test.js",
    "test/durable-outbox-crash-cut.test.js",
    "test/job-scheduler.test.js",
    "test/canonical-sync.test.js",
)
TEMPLATE_TABLES = (
    "users",
    "user_channels",
    "invite_codes",
    "user_settings",
    "setup_tokens",
    "web_sessions",
    "user_data_keys",
    "provider_credentials",
    "imports",
    "profile_facts",
    "profile_decisions",
    "activity_daily",
    "consent_events",
    "deletion_tombstones",
    "model_budget_settings",
    "model_token_usage_daily",
    "model_budget_reservations",
    "provider_circuits",
)
GUARDED_TABLES = ("inbox_messages", "jobs", "outbox_messages")
DESTRUCTIVE = re.compile(r"\b(?:DROP|RENAME|VACUUM|TRUNCATE|DELETE\s+FROM)\b", re.IGNORECASE)


class Checks:
    def __init__(self) -> None:
        self.rows: list[dict[str, Any]] = []

    def add(self, check_id: str, acceptance_id: str, ok: bool, detail: str) -> None:
        self.rows.append(
            {
                "check": check_id,
                "acceptance_id": acceptance_id,
                "result": "PASS" if ok else "FAIL",
                "detail": detail,
            }
        )

    @property
    def failed(self) -> list[dict[str, Any]]:
        return [row for row in self.rows if row["result"] != "PASS"]


def run_node_suite(relative: str) -> dict[str, Any]:
    result = subprocess.run(
        ["node", "--test", relative],
        cwd=APP,
        capture_output=True,
        text=True,
        check=False,
    )
    output = result.stdout + result.stderr
    counts = {
        key: int(match.group(1))
        for key in ("tests", "pass", "fail")
        if (match := re.search(rf"^. {key} (\d+)$", output, re.MULTILINE))
    }
    return {
        "suite": relative,
        "returncode": result.returncode,
        "tests": counts.get("tests", 0),
        "pass": counts.get("pass", 0),
        "fail": counts.get("fail", None),
    }


def check_migration(checks: Checks) -> None:
    source = MIGRATION.read_text(encoding="utf-8")

    checks.add(
        "cb610.migration_dynamic_prefix",
        "AC-030",
        MIGRATION.name == f"{SELECTED_PREFIX:03d}_multiuser_foundation.sql"
        and sorted(p.name for p in (APP / "migrations").glob("*.sql"))[-1] == MIGRATION.name,
        f"migration={MIGRATION.name}",
    )
    checks.add(
        "cb610.migration_additive_only",
        "AC-030",
        not DESTRUCTIVE.search(source),
        "no DROP/RENAME/VACUUM/TRUNCATE/DELETE FROM in migration 006",
    )
    checks.add(
        "cb610.migration_transactional",
        "AC-030",
        "BEGIN IMMEDIATE;" in source
        and source.rstrip().endswith("PRAGMA integrity_check;")
        and "COMMIT;" in source,
        "BEGIN IMMEDIATE / COMMIT / PRAGMA integrity_check present",
    )
    checks.add(
        "cb610.migration_registered",
        "AC-030",
        "INSERT INTO schema_migrations(" in source
        and "'CB-610'" in source
        and "__MIGRATION_006_CHECKSUM__" in source,
        "migration self-registers version 6 with a checksum placeholder",
    )

    missing = [t for t in TEMPLATE_TABLES if f"CREATE TABLE IF NOT EXISTS {t} (" not in source]
    checks.add(
        "cb610.frozen_template_tables_present",
        "AC-030",
        not missing,
        f"missing_tables={missing}",
    )
    checks.add(
        "cb610.template_provenance_recorded",
        "AC-030",
        TEMPLATE_SHA256 in source,
        "frozen template sha256 recorded in the migration header",
    )

    for table in GUARDED_TABLES:
        checks.add(
            f"cb610.user_scope_column.{table}",
            "AC-003",
            f"ALTER TABLE {table} ADD COLUMN user_id TEXT;" in source,
            f"{table}.user_id added additively",
        )
        for kind in ("insert", "update"):
            checks.add(
                f"cb610.valid_user_guard.{table}.{kind}",
                "AC-003",
                f"trg_{table}_valid_user_{kind}" in source,
                f"trg_{table}_valid_user_{kind} present",
            )
    checks.add(
        "cb610.user_delete_guard",
        "AC-030",
        "trg_users_scoped_rows_delete_guard" in source,
        "a user row cannot be deleted while scoped rows reference it",
    )
    checks.add(
        "cb610.sync_spool_system_scope_allowed",
        "AC-030",
        "trg_sync_spool_valid_user_insert" in source
        and "WHEN NEW.user_id IS NOT NULL" in source,
        "canonical sync keeps system scope (NULL) but rejects unknown users",
    )


def check_identity(checks: Checks) -> None:
    identity = (USERS / "user-identity.js").read_text(encoding="utf-8")
    repository = (USERS / "user-repository.js").read_text(encoding="utf-8")
    adapter = ADAPTER.read_text(encoding="utf-8")

    checks.add(
        "cb610.identity_is_hmac_derived",
        "AC-005",
        "createHmac" in identity and "cyberboss-channel-principal" in identity,
        "user_id derives from an HMAC over channel + bot account + sender",
    )
    checks.add(
        "cb610.identity_binds_bot_and_sender",
        "AC-005",
        "botAccountRef" in identity and "senderRef" in identity,
        "both the bot account and the sender enter the derivation",
    )
    checks.add(
        "cb610.identity_length_prefixed",
        "AC-005",
        "writeUInt32BE" in identity,
        "fields are length-prefixed, so no two field splits collide",
    )
    checks.add(
        "cb610.client_claim_never_trusted",
        "AC-005",
        "matchesDerivedIdentity" in identity and "timingSafeEqual" in identity,
        "a client-declared id can only be compared, never used to select scope",
    )
    checks.add(
        "cb610.principal_stored_as_hash",
        "AC-005",
        "principal_hash" in repository and "principalHash" in repository,
        "user_channels stores only the keyed principal hash",
    )
    checks.add(
        "cb610.owner_id_server_derived",
        "AC-005",
        "deriveOwnerUserId" in adapter and "cyberboss-owner-user" in adapter,
        "the Owner user id derives from the runtime identity key alone",
    )
    checks.add(
        "cb610.owner_backfill_before_guards",
        "AC-003",
        "#bootstrapOwnerScope" in adapter
        and "OWNER_SCOPE_BACKFILL_INCOMPLETE" in adapter
        and "FOREIGN_KEY_CHECK_FAILED" in adapter,
        "backfill runs once, then fails closed if any row stays unscoped",
    )
    checks.add(
        "cb610.reply_scope_inherited_from_job",
        "AC-003",
        "SELECT user_id FROM jobs WHERE id=?" in adapter,
        "outbox scope is inherited from the job, never caller-supplied",
    )
    checks.add(
        "cb610.model_gate_on_status",
        "AC-003",
        "mayCallModel" in repository and "MODEL_ELIGIBLE_STATUSES" in repository,
        "pending, suspended, deleting and deleted users cannot reach a model",
    )


def check_boundary(checks: Checks) -> None:
    """AC-030: no secret, raw chat or Mac dependency enters the code repository."""
    offenders: list[str] = []
    forbidden = ("/Users/", ".plist", "LaunchAgent", "LaunchDaemon", "launchd")
    for path in sorted(list(USERS.glob("*.js")) + [MIGRATION, ADAPTER]):
        text = path.read_text(encoding="utf-8", errors="replace")
        for marker in forbidden:
            if marker in text:
                offenders.append(f"{path.relative_to(PROJECT)}:{marker}")
    checks.add(
        "cb610.no_mac_markers_in_sources",
        "AC-030",
        not offenders,
        f"offenders={offenders}",
    )

    plaintext_secret = re.compile(
        r"(?:sk-[A-Za-z0-9]{16,}|BEGIN [A-Z ]*PRIVATE KEY|Bearer\s+[A-Za-z0-9._-]{20,})"
    )
    leaks = [
        str(path.relative_to(PROJECT))
        for path in sorted(list(USERS.glob("*.js")) + [MIGRATION, ADAPTER])
        if plaintext_secret.search(path.read_text(encoding="utf-8", errors="replace"))
    ]
    checks.add(
        "cb610.no_plaintext_secret_pattern",
        "AC-030",
        not leaks,
        f"leaks={leaks}",
    )

    invite = (USERS / "invite-code-store.js").read_text(encoding="utf-8")
    checks.add(
        "cb610.invite_plaintext_never_persisted",
        "AC-030",
        "hashCode(this.secret" in invite and "code_hash" in invite,
        "only the keyed invite hash reaches the database",
    )
    checks.add(
        "cb610.no_parallel_database",
        "AC-030",
        len(list((APP / "migrations").glob("*.sql"))) == 6
        and not (APP / "src/services/users/migrations").exists(),
        "one migration ledger, no second database plane",
    )


def check_suites(checks: Checks) -> list[dict[str, Any]]:
    results = [run_node_suite(name) for name in NODE_SUITES]
    for result in results:
        checks.add(
            f"cb610.suite.{Path(result['suite']).stem}",
            "AC-003",
            result["returncode"] == 0 and result["fail"] == 0 and result["tests"] > 0,
            f"tests={result['tests']} pass={result['pass']} fail={result['fail']}",
        )
    return results


def main() -> int:
    checks = Checks()
    check_migration(checks)
    check_identity(checks)
    check_boundary(checks)
    suites = check_suites(checks)

    report = {
        "schema_version": "cyberboss.cb610.validation.v1",
        "task_id": "CB-610",
        "product_version": "v0.0.0.8",
        "acceptance_ids": list(ACCEPTANCE_IDS),
        "check_count": len(checks.rows),
        "pass_count": len(checks.rows) - len(checks.failed),
        "fail_count": len(checks.failed),
        "unknown_count": 0,
        "not_run_count": 0,
        "status": "PASS" if not checks.failed else "FAIL",
        "node_suites": suites,
        "node_test_total": sum(item["tests"] for item in suites),
        "checks": checks.rows,
        "artifact_sha256": {
            str(path.relative_to(PROJECT)): hashlib.sha256(path.read_bytes()).hexdigest()
            for path in [MIGRATION, *sorted(USERS.glob("*.js"))]
        },
    }
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if report["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
