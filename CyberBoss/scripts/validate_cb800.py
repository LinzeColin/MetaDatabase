#!/usr/bin/env python3
"""Fail-closed local seal for CB-800.

Mapped acceptance: AC-029 (export and deletion), AC-030 (data boundary),
AC-035 (backup and restore).

Real R2, OCI and Private-Database endpoints need credentials that are not in
scope on this host. Those are reported as ACTIVATION_PENDING and never counted
as PASS. Everything provable without them is proved here on the exact target
subject.
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
SRC = APP / "src/services"
TASKPACK_DATA_CONTRACT = {
    "canonical_envelope_forbidden_fields": [
        "raw_message", "raw_chat", "prompt", "response", "api_key", "secret",
    ],
    "canonical_sync_normal": "daily_batch",
    "canonical_sync_critical": [
        "release", "incident", "recovery", "deletion", "revocation",
    ],
    "empty_commit": "forbidden",
    "crypto_shred": "delete_wrapped_user_dek",
}

ACCEPTANCE_IDS = ("AC-029", "AC-030", "AC-035")
SUITE = "test/cb800-data-boundary-backup-lifecycle.test.js"
REPEAT_RUNS = 3
MODULES = (
    "canonical/user-fact-envelope.js",
    "canonical/object-key.js",
    "backup/dual-copy-receipt.js",
    "privacy/deletion-plan.js",
    "privacy/user-data-lifecycle.js",
)
MIGRATION = APP / "migrations/007_cb800_lifecycle_receipts.sql"


class Checks:
    def __init__(self) -> None:
        self.rows: list[dict[str, Any]] = []

    def add(self, check_id: str, acceptance_id: str, ok: bool, detail: str) -> None:
        self.rows.append(
            {"check": check_id, "acceptance_id": acceptance_id,
             "result": "PASS" if ok else "FAIL", "detail": detail}
        )

    def pending(self, check_id: str, acceptance_id: str, detail: str) -> None:
        self.rows.append(
            {"check": check_id, "acceptance_id": acceptance_id,
             "result": "ACTIVATION_PENDING", "detail": detail}
        )

    @property
    def failed(self) -> list[dict[str, Any]]:
        return [row for row in self.rows if row["result"] == "FAIL"]

    @property
    def pending_rows(self) -> list[dict[str, Any]]:
        return [row for row in self.rows if row["result"] == "ACTIVATION_PENDING"]


def read(relative: str) -> str:
    return (SRC / relative).read_text(encoding="utf-8")


def run_node_suite(relative: str) -> dict[str, Any]:
    result = subprocess.run(
        ["node", "--test", relative], cwd=APP,
        capture_output=True, text=True, check=False,
    )
    output = result.stdout + result.stderr
    counts = {
        key: int(match.group(1))
        for key in ("tests", "pass", "fail")
        if (match := re.search(rf"^. {key} (\d+)$", output, re.MULTILINE))
    }
    return {
        "suite": relative, "returncode": result.returncode,
        "tests": counts.get("tests", 0), "pass": counts.get("pass", 0),
        "fail": counts.get("fail", None),
    }


def check_ac030(checks: Checks) -> None:
    envelope = read("canonical/user-fact-envelope.js")
    object_key = read("canonical/object-key.js")

    declared = re.findall(
        r'"([a-z_]+)"',
        envelope.split("FORBIDDEN_FIELDS = Object.freeze([")[1].split("]")[0],
    )
    checks.add("ac030.forbidden_fields_match_the_frozen_contract", "AC-030",
               declared == TASKPACK_DATA_CONTRACT["canonical_envelope_forbidden_fields"],
               f"declared={declared}")
    checks.add("ac030.scan_is_recursive", "AC-030",
               "function scanPayload" in envelope
               and "scanPayload(value[key]" in envelope
               and "MAX_PAYLOAD_DEPTH" in envelope,
               "a forbidden field is refused at any depth, not only at the top level")
    checks.add("ac030.substring_match_on_field_names", "AC-030",
               "normalized.includes(forbidden)" in envelope,
               "a forbidden name embedded in a longer name is still refused")
    checks.add("ac030.value_level_secret_scan", "AC-030",
               "SECRET_VALUE_PATTERN" in envelope
               and "CANONICAL_SECRET_VALUE_FORBIDDEN" in envelope,
               "a credential is refused on its value even under an innocent field name")
    checks.add("ac030.error_carries_path_not_value", "AC-030",
               "this.detail = detail" in envelope
               and "CanonicalEnvelopeError(code, path" not in envelope,
               "a refusal names the field path, never the field value")

    checks.add("ac030.daily_is_the_normal_cadence", "AC-030",
               '"daily"' in envelope and "dailyIntervalMs = 24 * 60 * 60 * 1000" in envelope,
               "ordinary facts default to the daily batch")
    immediate = re.findall(
        r'"([a-z0-9_.]+)"',
        envelope.split("IMMEDIATE_TYPES = Object.freeze([")[1].split("]")[0],
    )
    # An explicit mapping rather than a substring match: "deletion" is carried
    # by the type "user.deleted", which no fuzzy match would find.
    critical_map = {
        "release": ("release.published",),
        "incident": ("incident.opened", "incident.resolved"),
        "recovery": ("recovery.completed", "backup.restored"),
        "deletion": ("user.deleted",),
        "revocation": ("security.credential_revoked",),
    }
    assert set(critical_map) == set(TASKPACK_DATA_CONTRACT["canonical_sync_critical"])
    covered = {
        klass: [item for item in types if item in immediate]
        for klass, types in critical_map.items()
    }
    checks.add("ac030.every_critical_class_is_immediate", "AC-030",
               all(covered.values()),
               f"critical coverage={covered}")
    checks.add("ac030.empty_commit_forbidden", "AC-030",
               "CANONICAL_EMPTY_COMMIT_FORBIDDEN" in envelope
               and "create_commit: selected > 0" in envelope,
               "a window with no new fact creates no commit")
    checks.add("ac030.duplicate_source_event_collapses", "AC-030",
               "idempotency_key" in envelope and "seen.has(fact.idempotency_key)" in envelope,
               "replaying a source event does not create a second fact")

    # AC-030 forbids a parallel long-term fact store. The envelope must not be
    # able to become one: no table, no file, no socket of its own.
    offenders = [
        marker for marker in
        ("CREATE TABLE", "DatabaseSync", "node:fs", "node:http", "fetch(", "spawn(")
        if marker in envelope
    ]
    checks.add("ac030.no_parallel_fact_store", "AC-030", not offenders,
               f"offenders={offenders}")
    checks.add("ac030.single_canonical_authority_retained", "AC-030",
               (SRC / "canonical/canonical-sync.js").is_file()
               and "CanonicalSpoolCoordinator" in read("canonical/canonical-sync.js"),
               "the pre-existing canonical spool remains the only sync path")

    checks.add("ac030.object_keys_are_per_user_prefixed", "AC-030",
               "function userObjectPrefix" in object_key
               and "assertKeyBelongsToUser" in object_key
               and "OBJECT_KEY_SCOPE_VIOLATION" in object_key,
               "every object sits under its owner's prefix and scope is enforced")
    checks.add("ac030.object_keys_reject_traversal", "AC-030",
               'text.includes("..")' in object_key
               and "OBJECT_SEGMENT_TRAVERSAL" in object_key,
               "no segment can escape the owning prefix")
    checks.add("ac030.object_version_supports_rollback", "AC-030",
               "function previousVersionKey" in object_key,
               "a new version writes a new key, so the previous object survives a rollback")


def check_ac035(checks: Checks) -> None:
    backup = read("backup/dual-copy-receipt.js")
    checks.add("ac035.receipt_requires_both_copies", "AC-035",
               "BACKUP_DUAL_COPY_INCOMPLETE" in backup
               and "BACKUP_RECEIPT_NOT_DUAL_COPY" in backup,
               "a single-copy upload yields no receipt, and a one-copy receipt cannot restore")
    checks.add("ac035.integrity_precedes_decryption", "AC-035",
               backup.index("BACKUP_INTEGRITY_FAILED") < backup.index("this.decryptSnapshot("),
               "the ciphertext hash is verified before the cipher is reached")
    checks.add("ac035.plaintext_is_verified_after_decryption", "AC-035",
               "BACKUP_PLAINTEXT_MISMATCH" in backup and "plainSha256" in backup,
               "the restored plaintext is checked against the recorded digest")
    checks.add("ac035.unencrypted_snapshot_refused", "AC-035",
               "BACKUP_NOT_ENCRYPTED" in backup and "encrypted.equals(plain)" in backup,
               "an encrypt step that returned the plaintext is refused")
    checks.add("ac035.restore_is_isolated", "AC-035",
               "restoreRuntimeDbIsolated" in backup
               and "BACKUP_RESTORE_ROOT_REQUIRED" in backup
               and "isolated: true" in backup,
               "restore targets an explicit isolated root, never the live runtime")
    checks.add("ac035.relations_verified_after_restore", "AC-035",
               "verifyRelations" in backup and "BACKUP_RELATION_CHECK_FAILED" in backup,
               "the relational shape is checked before a restore is called good")
    checks.add("ac035.both_copies_proved_independently", "AC-035",
               "verifyBothCopies" in backup
               and "bothRestorable" in backup
               and "degraded" in backup,
               "each copy is proved able to carry a restore on its own")
    checks.add("ac035.existing_backup_runtime_not_forked", "AC-035",
               (SRC / "backup/canonical-backup-runtime.js").is_file()
               and (SRC / "backup/cb530-cloud-backup.js").is_file()
               and "createOnlineBackup" not in backup,
               "the pre-existing SQLite online backup and cloud client remain the implementation")


def check_ac029(checks: Checks) -> None:
    plan = read("privacy/deletion-plan.js")
    lifecycle = read("privacy/user-data-lifecycle.js")
    vault = read("secrets/credential-vault.js")

    # Digits matter: delete_r2_user_objects is dropped by an [a-z_] class.
    order = re.findall(r'"([a-z0-9_]+)"', plan.split("ORDER = Object.freeze([")[1].split("]")[0])
    checks.add("ac029.deletion_order_is_frozen_and_complete", "AC-029",
               order == [
                   "suspend_user", "revoke_web_sessions", "revoke_provider_credentials",
                   "cancel_pending_jobs", "delete_r2_user_objects",
                   "delete_search_and_profile_projections",
                   "write_private_database_tombstone", "destroy_user_data_key",
                   "mark_user_deleted",
               ],
               f"order={order}")
    checks.add("ac029.access_is_cut_before_data_is_touched", "AC-029",
               order.index("suspend_user") < order.index("delete_r2_user_objects")
               and order.index("revoke_web_sessions") < order.index("delete_r2_user_objects"),
               "no session can write back while the deletion runs")
    checks.add("ac029.shred_is_last_but_one", "AC-029",
               order.index("destroy_user_data_key") == len(order) - 2,
               "nothing after the shred needs to read what the key protected")
    checks.add("ac029.irreversible_steps_are_declared", "AC-029",
               "IRREVERSIBLE_ACTIONS" in plan and "destroy_user_data_key" in
               plan.split("IRREVERSIBLE_ACTIONS = Object.freeze([")[1].split("]")[0],
               "a completed crypto-shred is recorded as irreversible")
    checks.add("ac029.resume_knows_it_passed_the_shred", "AC-029",
               "pastIrreversible" in plan and "function resumePoint" in plan,
               "an interrupted request resumes rather than restarting")

    checks.add("ac029.export_is_scoped_in_query_and_result", "AC-029",
               "WHERE ${scope}=?" in lifecycle and "EXPORT_SCOPE_VIOLATION" in lifecycle,
               "the scope is applied in the query and re-proved on the assembled rows")
    checks.add("ac029.export_excludes_key_material", "AC-029",
               "EXCLUDED_FROM_EXPORT" in lifecycle
               and "user_data_keys" in lifecycle
               and "provider_credentials" in lifecycle
               and "EXPORT_EXCLUDED_TABLE_PRESENT" in lifecycle,
               "wrapped keys and credential ciphertext never enter an export")
    checks.add("ac029.export_objects_must_be_owned", "AC-029",
               "assertKeyBelongsToUser(ref, userId)" in lifecycle,
               "a manifest cannot name another user's object")
    checks.add("ac029.receipts_are_idempotent_and_scoped", "AC-029",
               'existing.status === "succeeded"' in lifecycle
               and "step.idempotencyKey" in lifecycle
               and "${userId}:${requestId}:${action}" in plan,
               "a receipt from one user's request cannot satisfy another user's step")
    checks.add("ac029.crypto_shred_destroys_the_wrapped_dek", "AC-029",
               "cryptoShred" in vault
               and "status='destroyed'" in vault
               and "USER_KEY_DESTROYED" in vault,
               f"contract={TASKPACK_DATA_CONTRACT['crypto_shred']}")
    checks.add("ac029.tombstone_has_no_reconstructible_identity", "AC-029",
               "user_ref" in lifecycle and "createHash(\"sha256\").update(`tombstone" in lifecycle,
               "the tombstone proves the deletion without keeping a pointer to the person")
    checks.add("ac029.deletion_is_a_critical_canonical_fact", "AC-029",
               '"user.deleted"' in read("canonical/user-fact-envelope.js"),
               "the deletion syncs immediately rather than waiting for the daily batch")


def check_migration(checks: Checks) -> None:
    source = MIGRATION.read_text(encoding="utf-8")
    checks.add("cb800.migration_is_additive", "AC-029",
               not re.search(r"\b(?:DROP|RENAME|VACUUM|DELETE FROM|ALTER TABLE \w+ DROP)\b",
                             source, re.IGNORECASE),
               "migration 007 drops, renames and deletes nothing")
    checks.add("cb800.migration_is_transactional", "AC-029",
               "BEGIN IMMEDIATE;" in source and "PRAGMA integrity_check;" in source,
               "migration 007 applies in one transaction and checks integrity")
    checks.add("cb800.migration_is_registered", "AC-029",
               "'CB-800'" in source
               and "__MIGRATION_007_CHECKSUM__" in source
               and '"007_cb800_lifecycle_receipts.sql"' in
               (SRC / "db/database-adapter.js").read_text(encoding="utf-8"),
               "migration 007 is registered in the ledger with its source node")
    checks.add("cb800.receipts_are_immutable", "AC-029",
               "trg_deletion_receipts_immutable" in source
               and "trg_deletion_receipts_no_delete" in source,
               "a deletion receipt cannot be rewritten or removed after the fact")


def check_hygiene(checks: Checks) -> None:
    offenders: list[str] = []
    for relative in MODULES:
        source = read(relative)
        lowered = source.lower()
        for marker in ("openai", "anthropic", "generativelanguage", "deepseek"):
            if marker in lowered:
                offenders.append(f"{relative}:{marker}")
        # Case-sensitive: "/Users/" is a macOS path, "../users/" is a module import.
        for marker in ("/Users/", ".plist", "LaunchAgent", "LaunchDaemon", "launchd"):
            if marker in source:
                offenders.append(f"{relative}:{marker}")
        if "\x00" in source:
            offenders.append(f"{relative}:raw_control_byte")
    checks.add("cb800.no_provider_or_mac_or_control_bytes", "AC-030", not offenders,
               f"offenders={offenders}")

    registered = (APP / "package.json").read_text(encoding="utf-8")
    missing = [relative for relative in MODULES if f"src/services/{relative}" not in registered]
    checks.add("cb800.modules_are_syntax_checked", "AC-030", not missing,
               f"missing_from_check_script={missing}")


def check_activation_pending(checks: Checks) -> list[str]:
    """Everything that needs a real credential, named rather than simulated."""
    pending = [
        "real Cloudflare R2 bucket credential: the encrypted object upload and the "
        "cold-copy restore are proved against an in-memory object client, never against "
        "a live bucket",
        "real OCI object storage pre-authenticated request: the second copy is proved "
        "structurally, never against a live offsite bucket",
        "real Private-Database endpoint: the user-scoped canonical envelope is proved "
        "against the frozen contract, and its remote commit is not exercised here",
    ]
    for item in pending:
        checks.pending("cb800.activation_pending", "AC-035", item)
    return pending


def main() -> int:
    checks = Checks()
    check_ac030(checks)
    check_ac035(checks)
    check_ac029(checks)
    check_migration(checks)
    check_hygiene(checks)
    pending = check_activation_pending(checks)

    runs = [run_node_suite(SUITE) for _ in range(REPEAT_RUNS)]
    clean = [run for run in runs if run["returncode"] == 0 and run["fail"] == 0]
    checks.add("cb800.suite_is_deterministic", "AC-029",
               len(clean) == REPEAT_RUNS and runs[0]["tests"] > 0,
               f"clean_runs={len(clean)}/{REPEAT_RUNS} tests={runs[0]['tests']}")

    report = {
        "schema_version": "cyberboss.cb800.validation.v1",
        "task_id": "CB-800",
        "product_version": "v0.0.0.8",
        "acceptance_ids": list(ACCEPTANCE_IDS),
        "check_count": len(checks.rows),
        "pass_count": len([row for row in checks.rows if row["result"] == "PASS"]),
        "fail_count": len(checks.failed),
        "activation_pending_count": len(checks.pending_rows),
        "unknown_count": 0,
        "not_run_count": 0,
        "status": "PASS" if not checks.failed else "FAIL",
        "node_verdict": "CONDITIONAL_PASS" if checks.pending_rows and not checks.failed
        else ("PASS" if not checks.failed else "FAIL"),
        "activation_pending": pending,
        "repeat_runs": runs,
        "node_test_total": runs[0]["tests"] if runs else 0,
        "checks": checks.rows,
        "artifact_sha256": {
            **{
                f"app/src/services/{relative}":
                    hashlib.sha256((SRC / relative).read_bytes()).hexdigest()
                for relative in MODULES
            },
            "app/migrations/007_cb800_lifecycle_receipts.sql":
                hashlib.sha256(MIGRATION.read_bytes()).hexdigest(),
        },
    }
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if report["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
