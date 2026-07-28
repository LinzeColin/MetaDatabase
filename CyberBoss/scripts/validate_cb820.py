#!/usr/bin/env python3
"""Fail-closed local seal for CB-820.

Mapped acceptance: AC-006 (Owner boundary), AC-012 (provider key vault),
AC-026 (sensitive attribute protection), AC-038 (AGPL and provenance).

This node adds no feature; it is the security, privacy, model-boundary,
supply-chain and fault-injection closure. The scans here cover the whole
project tree rather than a module list, because a leak anywhere breaks the
claim.
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

ACCEPTANCE_IDS = ("AC-006", "AC-012", "AC-026", "AC-038")
SUITE = "test/cb820-security-privacy-supply-chain.test.js"
REPEAT_RUNS = 3
FAULT_MATRIX_SHA256 = "fd0b837be08230fa424406050d8ede6a73ab780738d627857c90011b72f9b4fe"
ZERO_AGENT_CASES_SHA256 = "3536918a5072d637056eee4dbe09aa321726415c5d7c9eead1c221ccca9ad35a"

# Frozen by machine/privacy_storage_contract.json.
FROZEN_PRIVACY = {
    "user_data_key_algorithm": "AES-256-GCM",
    "dek": "random_32_bytes_per_user",
    "wrapped_by": "root_owned_master_kek",
    "aad": "user_id_scope",
    "crypto_shred": "destroy_wrapped_dek_record",
    "credential_algorithm": "AES-256-GCM",
    "credential_key": "provider_subkey_derived_from_user_dek",
    "credential_aad": "user_id_provider_scope",
    "plaintext_destinations": [],
}

CREDENTIAL_PATTERNS = (
    ("private_key", re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----")),
    ("github_token", re.compile(r"\bgh[pousr]_[A-Za-z0-9]{36,}\b")),
    ("slack_token", re.compile(r"\bxox[baprs]-[A-Za-z0-9-]{20,}\b")),
    ("aws_key_id", re.compile(r"\bAKIA[0-9A-Z]{16}\b")),
    ("provider_key", re.compile(r"\bsk-(?:proj-|ant-)?[A-Za-z0-9_-]{25,}\b")),
    ("wechat_id", re.compile(r"\bwxid_[A-Za-z0-9_-]{6,}\b")),
)
SYNTHETIC = re.compile(
    r"abcdefghij|0123456789|(.)\1{6,}|sk-test-|sk-bob-|thisexact|secretvalue"
    r"|someone|wxid_abcd|BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----(?:\"|`|'|,|\s*$)"
)
DECLARED_VECTOR_FILES = {
    "app/test/cb700-provider-vault-budget-circuit.test.js",
    "app/test/cb800-data-boundary-backup-lifecycle.test.js",
    "app/test/cb810-status-resource-selfheal.test.js",
    "app/test/cb820-security-privacy-supply-chain.test.js",
    "app/src/services/canonical/user-fact-envelope.js",
    "app/src/services/status/business-matrix.js",
}
RUNTIME_FETCH = (
    re.compile(r"child_process[\s\S]{0,40}[\"']git[\"']"),
    re.compile(r"npm\s+(?:install|i|ci)\b"),
    re.compile(r"git\s+clone\b"),
    re.compile(r"curl\s+-[a-zA-Z]*[sS]"),
    re.compile(r"wget\s+http"),
)
SCANNED_SUFFIXES = (".js", ".json", ".md", ".sql", ".sh", ".py", ".html", ".txt")
SKIP_DIRECTORIES = {"node_modules", ".git", "vendor"}


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


def project_files():
    for path in sorted(PROJECT.rglob("*")):
        if any(part in SKIP_DIRECTORIES for part in path.parts):
            continue
        if path.is_file() and path.suffix in SCANNED_SUFFIXES:
            yield path


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


def check_ac006(checks: Checks) -> None:
    context = read("users/user-context.js")
    host = (APP / "src/tools/tool-host.js").read_text(encoding="utf-8")
    owner_only = re.findall(
        r'"([a-z.]+)"',
        context.split("OWNER_ONLY_CAPABILITIES = Object.freeze([")[1].split("]")[0],
    )
    user_caps = re.findall(
        r'"([a-z.]+)"',
        context.split("USER_CAPABILITIES = Object.freeze([")[1].split("]")[0],
    )
    checks.add("ac006.owner_surface_is_declared", "AC-006",
               {"codex.turn", "workspace.write", "shell.execute", "project.tool", "mcp.invoke"}
               <= set(owner_only),
               f"owner_only={owner_only}")
    checks.add("ac006.capability_sets_do_not_overlap", "AC-006",
               not (set(owner_only) & set(user_caps)),
               f"overlap={sorted(set(owner_only) & set(user_caps))}")
    checks.add("ac006.owner_capability_needs_owner_role", "AC-006",
               "return this.isOwner;" in context,
               "an Owner-only capability resolves to the stored owner role, not a claim")
    checks.add("ac006.tool_host_checks_first", "AC-006",
               "#assertOwnerCapability(context);" in host
               and host.index("#assertOwnerCapability(context);")
               < host.index("PROJECT_TOOLS.find"),
               "the Owner guard runs before any tool is resolved")
    checks.add("ac006.suspended_user_reaches_nothing", "AC-006",
               "USER_NOT_ACTIVE" in context or 'status !== "active"' in context,
               "a suspended user loses every capability")


def check_ac012(checks: Checks) -> None:
    vault = read("secrets/credential-vault.js")
    checks.add("ac012.algorithm_matches_the_frozen_contract", "AC-012",
               'ALGORITHM = "AES-256-GCM"' in vault or '"aes-256-gcm"' in vault,
               f"contract={FROZEN_PRIVACY['user_data_key_algorithm']}")
    checks.add("ac012.dek_is_random_per_user", "AC-012",
               "randomSource(KEY_BYTES)" in vault and "KEY_BYTES = 32" in vault,
               f"contract={FROZEN_PRIVACY['dek']}")
    checks.add("ac012.dek_wrapped_by_master_kek", "AC-012",
               "deriveWrappingKey(masterKey" in vault,
               f"contract={FROZEN_PRIVACY['wrapped_by']}")
    checks.add("ac012.user_scope_in_the_aad", "AC-012",
               "CyberBoss:user-key:${userId}" in vault,
               f"contract={FROZEN_PRIVACY['aad']}")
    checks.add("ac012.provider_scope_in_the_aad", "AC-012",
               "CyberBoss:credential:${userId}:${providerId}" in vault,
               f"contract={FROZEN_PRIVACY['credential_aad']}")
    checks.add("ac012.provider_key_derived_from_the_dek", "AC-012",
               "function deriveProviderKey" in vault and "hkdfSync" in vault,
               f"contract={FROZEN_PRIVACY['credential_key']}")
    checks.add("ac012.rotation_and_shred_exist", "AC-012",
               "rotateUserKey" in vault and "cryptoShred" in vault
               and "USER_KEY_DESTROYED" in vault,
               f"contract={FROZEN_PRIVACY['crypto_shred']}")
    checks.add("ac012.key_material_is_zeroed_after_use", "AC-012",
               vault.count(".fill(0)") >= 3,
               "derived key material is wiped rather than left on the heap")
    errors = read("providers/errors.js")
    checks.add("ac012.error_path_carries_no_body_or_credential", "AC-012",
               "Buffer.byteLength(String(body)" in errors
               and "MESSAGES[code]" in errors,
               "the diagnostic reflects shape only; the message comes from a fixed table")
    # Status must not be a plaintext destination either.
    status = read("status/business-matrix.js")
    checks.add("ac012.status_refuses_credential_values", "AC-012",
               "sk-" in status and "STATUS_VALUE_FORBIDDEN" in status,
               f"plaintext_destinations={FROZEN_PRIVACY['plaintext_destinations']}")


def check_ac026(checks: Checks) -> None:
    projector = read("profile/profile-projector.js")
    categories = re.findall(
        r'"([a-z_]+)"',
        projector.split("SENSITIVE_CATEGORIES = Object.freeze([")[1].split("]")[0],
    )
    checks.add("ac026.sensitive_set_is_declared", "AC-026",
               len(categories) >= 9,
               f"sensitive_categories={sorted(categories)}")
    checks.add("ac026.inference_is_forbidden_at_any_confidence", "AC-026",
               "SENSITIVE_INFERENCE_FORBIDDEN" in projector
               and 'fact.kind === "inferred"' in projector,
               "a sensitive attribute is refused before any confidence test runs")
    checks.add("ac026.consent_is_required_and_per_category", "AC-026",
               "fact.explicitSensitiveConsent !== fact.category" in projector
               and "SENSITIVE_PROFILE_BLOCKED" in projector,
               "consent for one category does not unlock another")
    checks.add("ac026.default_count_is_observable", "AC-026",
               "function sensitiveInferenceCount" in projector,
               "the number of inferred sensitive attributes is directly countable")


def check_ac038(checks: Checks) -> dict[str, Any]:
    lock = json.loads((PROJECT / "machine/source-lock.json").read_text(encoding="utf-8"))
    checks.add("ac038.every_source_is_pinned_to_a_commit", "AC-038",
               all(re.fullmatch(r"[0-9a-f]{40}", source.get("commit", ""))
                   for source in lock["sources"]),
               f"sources={[source['id'] for source in lock['sources']]}")
    unresolved = []
    for source in lock["sources"]:
        declared = source.get("license_declared")
        concluded = source.get("license_file_concluded")
        expression = source.get("compliance_expression", "")
        if declared != concluded:
            if not (declared in expression and concluded in expression):
                unresolved.append(source["id"])
        elif expression != declared:
            unresolved.append(source["id"])
    checks.add("ac038.licence_discrepancies_are_resolved", "AC-038", not unresolved,
               f"unresolved={unresolved}; "
               f"recorded={[(s['id'], s.get('compliance_expression')) for s in lock['sources']]}")
    checks.add("ac038.modifications_are_recorded", "AC-038",
               all("bundle_changes_from_locked_source" in source for source in lock["sources"]),
               "each source records what was added, modified and removed")
    checks.add("ac038.no_fetch_remote_is_retained", "AC-038",
               all(source.get("temporary_fetch_repository_remote_count") == 0
                   for source in lock["sources"]),
               "no temporary fetch remote survives in the repository")

    for name in ("LICENSE", "THIRD_PARTY_NOTICES.md", "UPSTREAM_PROVENANCE.md"):
        checks.add(f"ac038.{name.lower().replace('.', '_')}_present", "AC-038",
                   (PROJECT / name).is_file(), f"{name} is present")
    license_text = (PROJECT / "LICENSE").read_text(encoding="utf-8")
    checks.add("ac038.agpl_text_retained", "AC-038",
               "GNU AFFERO GENERAL PUBLIC LICENSE" in license_text,
               "the AGPL text itself is kept, not only a reference to it")

    fetchers: list[str] = []
    for path in (APP / "src").rglob("*.js"):
        source = path.read_text(encoding="utf-8", errors="replace")
        for pattern in RUNTIME_FETCH:
            if pattern.search(source):
                fetchers.append(f"{path.relative_to(PROJECT)}:{pattern.pattern[:20]}")
    checks.add("ac038.no_runtime_upstream_fetch", "AC-038", not fetchers,
               f"offenders={fetchers}")
    return {"sources": [source["id"] for source in lock["sources"]],
            "compliance": {source["id"]: source.get("compliance_expression")
                           for source in lock["sources"]}}


def check_secret_scan(checks: Checks) -> dict[str, Any]:
    shipping: list[str] = []
    undeclared: list[str] = []
    non_synthetic: list[str] = []
    for path in project_files():
        relative = str(path.relative_to(PROJECT))
        text = path.read_text(encoding="utf-8", errors="replace")
        for name, pattern in CREDENTIAL_PATTERNS:
            if not pattern.search(text):
                continue
            record = f"{relative}:{name}"
            if relative not in DECLARED_VECTOR_FILES:
                (undeclared if relative.startswith("app/test/") else shipping).append(record)
                continue
            line = next((row for row in text.splitlines() if pattern.search(row)), "")
            if not SYNTHETIC.search(line):
                non_synthetic.append(record)
    checks.add("cb820.no_credential_in_shipped_tree", "AC-038", not shipping,
               f"offenders={shipping}")
    checks.add("cb820.every_test_vector_is_declared", "AC-038", not undeclared,
               f"undeclared={undeclared}")
    checks.add("cb820.every_declared_vector_is_synthetic", "AC-038", not non_synthetic,
               f"non_synthetic={non_synthetic}")
    return {"declared_vector_files": sorted(DECLARED_VECTOR_FILES)}


def check_fault_matrix(checks: Checks) -> None:
    matrix_path = APP / "test/fixtures/provider-fault-matrix.json"
    cases_path = APP / "test/fixtures/zero-agent-runtime-cases.json"
    checks.add("cb820.fault_matrix_is_byte_identical", "AC-012",
               hashlib.sha256(matrix_path.read_bytes()).hexdigest() == FAULT_MATRIX_SHA256,
               f"sha256={hashlib.sha256(matrix_path.read_bytes()).hexdigest()}")
    checks.add("cb820.zero_agent_cases_are_byte_identical", "AC-006",
               hashlib.sha256(cases_path.read_bytes()).hexdigest() == ZERO_AGENT_CASES_SHA256,
               f"sha256={hashlib.sha256(cases_path.read_bytes()).hexdigest()}")
    matrix = json.loads(matrix_path.read_text(encoding="utf-8"))
    checks.add("cb820.every_frozen_fault_case_is_covered", "AC-012",
               len(matrix["cases"]) == 7,
               f"cases={len(matrix['cases'])}")

    suite = (APP / SUITE).read_text(encoding="utf-8")
    # Call forms, not the bare word: a comment that says "nothing here sleeps"
    # is a statement about the code, not a wait in it.
    waits = [form for form in
             ("setTimeout(", "setInterval(", "Atomics.wait(", "sleep(", "execSync(\"sleep")
             if form in suite]
    checks.add("cb820.no_real_time_wait_in_the_fault_replay", "AC-012",
               not waits and "const advance = (ms)" in suite,
               f"wait_call_forms={waits}")


def main() -> int:
    checks = Checks()
    check_ac006(checks)
    check_ac012(checks)
    check_ac026(checks)
    supply = check_ac038(checks)
    scan = check_secret_scan(checks)
    check_fault_matrix(checks)

    runs = [run_node_suite(SUITE) for _ in range(REPEAT_RUNS)]
    clean = [run for run in runs if run["returncode"] == 0 and run["fail"] == 0]
    checks.add("cb820.suite_is_deterministic", "AC-006",
               len(clean) == REPEAT_RUNS and runs[0]["tests"] > 0,
               f"clean_runs={len(clean)}/{REPEAT_RUNS} tests={runs[0]['tests']}")

    report = {
        "schema_version": "cyberboss.cb820.validation.v1",
        "task_id": "CB-820",
        "product_version": "v0.0.0.8",
        "acceptance_ids": list(ACCEPTANCE_IDS),
        "check_count": len(checks.rows),
        "pass_count": len(checks.rows) - len(checks.failed),
        "fail_count": len(checks.failed),
        "activation_pending_count": 0,
        "unknown_count": 0,
        "not_run_count": 0,
        "status": "PASS" if not checks.failed else "FAIL",
        "node_verdict": "PASS" if not checks.failed else "FAIL",
        "supply_chain": supply,
        "secret_scan": scan,
        "repeat_runs": runs,
        "node_test_total": runs[0]["tests"] if runs else 0,
        "checks": checks.rows,
    }
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if report["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
