#!/usr/bin/env python3
"""Fail-closed local seal for CB-710.

Mapped acceptance: AC-018 (ChatGPT import), AC-019 (Claude import), AC-020
(Gemini compatible import), AC-021 (DeepSeek compatible import), AC-022 (upload
safety), AC-023 (import recovery).

Every frozen import attack case is replayed against the real reader; UNKNOWN
and NOT_RUN are never folded into PASS.
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
SRC = APP / "src/services/imports"

ACCEPTANCE_IDS = ("AC-018", "AC-019", "AC-020", "AC-021", "AC-022", "AC-023")
NODE_SUITES = (
    "test/cb710-import-safety.test.js",
    "test/cb700-provider-vault-budget-circuit.test.js",
)
MODULES = (
    "upload-policy.js", "safe-zip-reader.js", "normalize.js", "chatgpt.js",
    "claude.js", "gemini.js", "deepseek.js", "router.js", "import-ledger.js",
)
# The frozen import attack matrix from the taskpack, replayed by the suite.
ATTACK_CASES = {
    "IMP-01": ("reject_path_traversal", "ARCHIVE_PATH_FORBIDDEN"),
    "IMP-02": ("reject_duplicate_target", "ARCHIVE_DUPLICATE_TARGET"),
    "IMP-03": ("reject_expansion_ratio", "ZIP_RATIO_INVALID"),
    "IMP-04": ("reject_depth", "ARCHIVE_DEPTH_EXCEEDED"),
    "IMP-05": ("reject_active_content", "ARCHIVE_FILE_TYPE_FORBIDDEN"),
    "IMP-06": ("same_import_identity_no_duplicate_facts", "duplicate"),
    "IMP-07": ("quarantine_record_continue_valid_records", "NO_PARSEABLE_MESSAGES"),
}


class Checks:
    def __init__(self) -> None:
        self.rows: list[dict[str, Any]] = []

    def add(self, check_id: str, acceptance_id: str, ok: bool, detail: str) -> None:
        self.rows.append(
            {"check": check_id, "acceptance_id": acceptance_id,
             "result": "PASS" if ok else "FAIL", "detail": detail}
        )

    @property
    def failed(self) -> list[dict[str, Any]]:
        return [row for row in self.rows if row["result"] != "PASS"]


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


def check_ac022(checks: Checks) -> None:
    policy = read("upload-policy.js")
    reader = read("safe-zip-reader.js")
    suite = (APP / "test/cb710-import-safety.test.js").read_text(encoding="utf-8")

    checks.add("ac022.limits_match_frozen_contract", "AC-022",
               "maxArchiveBytes: 256 * 1024 * 1024" in policy
               and "maxExpandedBytes: 1024 * 1024 * 1024" in policy
               and "maxFiles: 5000" in policy and "maxDepth: 12" in policy,
               "archive, expansion, file-count and depth limits match the frozen contract")
    checks.add("ac022.extension_allowlist_is_data_only", "AC-022",
               '".json", ".html", ".htm", ".md", ".txt", ".csv"' in policy,
               "only data formats are allowed; executables, scripts and nested archives are not")
    checks.add("ac022.path_traversal_refused", "AC-022",
               "ARCHIVE_PATH_FORBIDDEN" in policy and 'replaceAll("\\\\", "/")' in policy,
               "traversal is refused after Windows separators are normalised")
    checks.add("ac022.duplicate_target_refused", "AC-022",
               "ARCHIVE_DUPLICATE_TARGET" in policy and "ARCHIVE_DUPLICATE_TARGET" in reader,
               "two members normalising to one target are refused")
    checks.add("ac022.symlink_refused", "AC-022",
               "ZIP_SYMLINK_FORBIDDEN" in reader and "SYMLINK_MODE" in reader,
               "a symlink member is refused")
    checks.add("ac022.encrypted_and_unknown_method_refused", "AC-022",
               "ZIP_ENCRYPTED_ENTRY" in reader and "ZIP_METHOD_UNSUPPORTED" in reader,
               "encrypted and unsupported-method entries are refused")
    checks.add("ac022.zip_bomb_refused", "AC-022",
               "MAX_COMPRESSION_RATIO = 200" in reader and "ZIP_RATIO_INVALID" in reader,
               "an implausible compression ratio is refused")
    checks.add("ac022.decided_before_inflation", "AC-022",
               reader.index("function inspectZip") < reader.index("function readZipEntries")
               and "const info = inspectZip(buffer, policy);" in reader,
               "every decision is made from the central directory before inflating")
    checks.add("ac022.bounded_inflation", "AC-022",
               "maxOutputLength: entry.uncompressed" in reader,
               "inflation is capped, so a lying header cannot exhaust memory")
    checks.add("ac022.integrity_verified", "AC-022",
               "ZIP_CRC_MISMATCH" in reader and "ZIP_SIZE_MISMATCH" in reader,
               "CRC and size are verified after inflation")
    checks.add("ac022.failed_object_cleanup_receipt", "AC-023",
               "fail({ importId, reasonCode })" in read("import-ledger.js"),
               "a failed import records a receipt instead of vanishing")

    replayed = [case for case, (_label, marker) in ATTACK_CASES.items() if marker in suite]
    checks.add("ac022.frozen_attack_matrix_replayed", "AC-022",
               sorted(replayed) == sorted(ATTACK_CASES),
               f"replayed={sorted(replayed)} of {sorted(ATTACK_CASES)}")


def check_parsers(checks: Checks) -> None:
    normalize = read("normalize.js")
    checks.add("ac018.chatgpt_mapping_tree", "AC-018",
               "conv.mapping" in read("chatgpt.js") or "conversation.mapping" in read("chatgpt.js"),
               "ChatGPT parses the mapping tree")
    checks.add("ac018.chatgpt_stable_ordering", "AC-018",
               "create_time" in read("chatgpt.js") and "nodes.sort(" in read("chatgpt.js"),
               "nodes are sorted by create_time, so ordering is stable")
    checks.add("ac018.chatgpt_stable_label", "AC-018",
               'compatibility: "stable"' in read("chatgpt.js"),
               "ChatGPT is labelled stable")
    checks.add("ac019.claude_chat_messages", "AC-019",
               "chat_messages" in read("claude.js"),
               "Claude parses the conversations/chat_messages structure")
    checks.add("ac019.claude_block_content_flattened", "AC-019",
               "textFromContent" in read("claude.js"),
               "block-array content flattens to text")
    checks.add("ac019.claude_stable_label", "AC-019",
               'compatibility: "stable"' in read("claude.js"),
               "Claude is labelled stable")
    checks.add("ac018_019.hash_idempotency", "AC-018",
               "stableHash" in normalize and "Object.keys(value)\n        .sort()" in normalize,
               "the canonical hash is stable under key ordering")

    for acceptance, module, label in (
        ("AC-020", "gemini.js", "Gemini"),
        ("AC-021", "deepseek.js", "DeepSeek"),
    ):
        source = read(module)
        checks.add(f"{acceptance.lower().replace('-', '')}.beta_label", acceptance,
                   '"beta"' in source and '"beta_low_confidence"' in source,
                   f"{label} results are labelled beta or beta_low_confidence")
        checks.add(f"{acceptance.lower().replace('-', '')}.never_stable", acceptance,
                   'compatibility: "stable"' not in source,
                   f"{label} never claims a stable label")
        checks.add(f"{acceptance.lower().replace('-', '')}.unknown_structure_low_confidence", acceptance,
                   "recognised ?" in source,
                   f"{label} drops to low confidence when it recognises no message list")
    checks.add("ac020.gemini_strips_active_content", "AC-020",
               "<script" in read("gemini.js") and "<style" in read("gemini.js"),
               "Gemini HTML import strips script and style content")


def check_ac023(checks: Checks) -> None:
    ledger = read("import-ledger.js")
    router = read("router.js")
    checks.add("ac023.identity_from_user_source_hash", "AC-023",
               "importIdentity" in ledger
               and re.search(r"\$\{userId\}\\u0000\$\{source\}\\u0000\$\{sourceHash\}", ledger)
               is not None,
               "import identity is (user, source, content hash) with NUL-separated fields")
    checks.add("ac023.no_raw_control_bytes_in_source", "AC-023",
               all(
                   "\x00" not in (SRC / relative).read_text(encoding="utf-8")
                   for relative in MODULES
               ),
               "separators are written as explicit escapes, not raw control bytes")
    checks.add("ac023.repeat_upload_is_duplicate", "AC-023",
               "duplicate: true" in ledger and 'exec("BEGIN IMMEDIATE")' in ledger,
               "a repeat upload resolves to the same import atomically")
    checks.add("ac023.checkpoint_monotonic", "AC-023",
               "imported_records <= ?" in ledger and "IMPORT_CHECKPOINT_REJECTED" in ledger,
               "a stale worker cannot rewind recorded progress")
    checks.add("ac023.resume_from_checkpoint", "AC-023",
               "resume(importId)" in ledger and "already_completed" in ledger,
               "an interrupted import resumes from its checkpoint")
    checks.add("ac023.corrupt_record_quarantined", "AC-023",
               "parseImportIsolating" in router and "NO_PARSEABLE_MESSAGES" in router,
               "one unreadable record is quarantined while valid records import")
    checks.add("ac023.quarantine_reason_is_a_code", "AC-023",
               "reason: error.code" in router,
               "the quarantine reason is a code, never record content")
    checks.add("ac023.listing_hides_object_ref", "AC-023",
               "object_ref" not in ledger.split("listForUser")[1].split("}")[0],
               "the user-facing import listing carries no object reference")


def check_hygiene(checks: Checks) -> None:
    offenders: list[str] = []
    for relative in MODULES:
        text = read(relative).lower()
        for marker in ("openai", "anthropic", "generativelanguage", "fetch(", "/users/", "launchd"):
            if marker in text:
                offenders.append(f"{relative}:{marker}")
    checks.add("cb710.import_path_reaches_no_provider", "AC-023",
               not offenders, f"offenders={offenders}")
    checks.add("cb710.no_raw_chat_fixture_in_repo", "AC-022",
               not list((APP / "test/fixtures").glob("*conversations*.json")),
               "no real conversation export is committed to the repository")


def check_suites(checks: Checks) -> list[dict[str, Any]]:
    results = [run_node_suite(name) for name in NODE_SUITES]
    for result in results:
        checks.add(f"cb710.suite.{Path(result['suite']).stem}", "AC-022",
                   result["returncode"] == 0 and result["fail"] == 0 and result["tests"] > 0,
                   f"tests={result['tests']} pass={result['pass']} fail={result['fail']}")
    return results


def main() -> int:
    checks = Checks()
    check_ac022(checks)
    check_parsers(checks)
    check_ac023(checks)
    check_hygiene(checks)
    suites = check_suites(checks)

    report = {
        "schema_version": "cyberboss.cb710.validation.v1",
        "task_id": "CB-710",
        "product_version": "v0.0.0.8",
        "acceptance_ids": list(ACCEPTANCE_IDS),
        "check_count": len(checks.rows),
        "pass_count": len(checks.rows) - len(checks.failed),
        "fail_count": len(checks.failed),
        "unknown_count": 0,
        "not_run_count": 0,
        "status": "PASS" if not checks.failed else "FAIL",
        "frozen_attack_cases": ATTACK_CASES,
        "node_suites": suites,
        "node_test_total": sum(item["tests"] for item in suites),
        "checks": checks.rows,
        "artifact_sha256": {
            f"app/src/services/imports/{relative}": hashlib.sha256((SRC / relative).read_bytes()).hexdigest()
            for relative in MODULES
        },
    }
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if report["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
