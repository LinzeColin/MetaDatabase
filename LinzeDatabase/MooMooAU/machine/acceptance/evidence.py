"""Deterministic, fail-closed control plane for AC-001 through AC-034 evidence."""

from __future__ import annotations

import ast
import csv
import hashlib
import json
import re
import shlex
import subprocess
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Final, cast

from jsonschema import Draft202012Validator, FormatChecker
from jsonschema.exceptions import SchemaError

PROJECT_ROOT: Final = Path(__file__).resolve().parents[2]
ACCEPTANCE_CONTRACT: Final = Path("machine/contracts/acceptance_contract.json")
REQUIREMENTS_CONTRACT: Final = Path("machine/contracts/requirements.json")
TRACEABILITY_CONTRACT: Final = Path("machine/contracts/traceability_matrix.csv")
RECORD_SCHEMA: Final = Path("machine/acceptance/schemas/acceptance-evidence-v1.schema.json")
SUMMARY_SCHEMA: Final = Path("machine/acceptance/schemas/acceptance-summary-v1.schema.json")
ORACLE_SCHEMA: Final = Path("machine/acceptance/schemas/oracle-observation-v1.schema.json")
SUMMARY_PATH: Final = Path("evidence/acceptance/latest.json")
PORTABLE_SOURCE_PROVENANCE: Final = Path("taskpack/SOURCE_PROVENANCE.v1.0.14.json")
PORTABLE_SOURCE_PROVENANCE_SCHEMA: Final = "moomooau.source-provenance.v13"
PORTABLE_PACKAGE_VERSION: Final = "1.0.14"
CURRENT_MAINLINE_BASE_COMMIT: Final = (
    "9ca3b47eaaa75ef2f6e6650b41960d11545ed04e"  # pragma: allowlist secret
)
ACCEPTANCE_REMEDIATION_BASE_COMMIT: Final = (
    "c860f3880b48b03c3f71ac79e61e278125fb1811"  # pragma: allowlist secret
)
EXPECTED_ACCEPTANCE_IDS: Final = tuple(f"AC-{index:03d}" for index in range(1, 35))
EXPECTED_REQUIREMENT_IDS: Final = tuple(f"RQ-{index:03d}" for index in range(1, 35))
COMMIT: Final = re.compile(r"^[0-9a-f]{40}$")
UTC_TIMESTAMP: Final = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$")
TASK_ID: Final = re.compile(r"^T\d{4}$")
FINAL_CLAIM_STATUSES: Final = {"PASS", "PARTIAL", "NOT_RUN", "BLOCKED"}
PROHIBITION_COUNTERS: Final = (
    "real_gmail_calls",
    "gmail_mutations",
    "private_repository_calls",
    "real_secrets_read",
    "protected_key_deliveries",
    "external_writes",
    "remote_publication",
    "non_moomoo_full_reads",
    "non_moomoo_downloads",
    "non_moomoo_mutations",
    "raw_before_verification",
    "untrusted_content_execution",
    "model_real_data_calls",
    "model_secret_requests",
    "moomoo_portal_calls",
    "persistent_plaintext_objects",
    "thread_trash_calls",
    "permanent_delete_calls",
    "release_assets_above_one",
    "production_workflow_runs",
)


class AcceptanceEvidenceError(RuntimeError):
    """The final Acceptance proof plane is incomplete, inconsistent, or unsafe."""


@dataclass(frozen=True, slots=True)
class ContractBinding:
    acceptance: dict[str, Any]
    requirement: dict[str, Any]
    traceability: dict[str, str]
    test_path: Path
    evidence_path: Path


@dataclass(frozen=True, slots=True)
class AcceptanceEvaluation:
    acceptance_id: str
    valid: bool
    passed: bool
    acceptance_status: str
    oracle_status: str
    blockers: tuple[str, ...]
    errors: tuple[str, ...]
    evidence_path: str

    def failure_message(self) -> str:
        details = self.errors or self.blockers or ("PASS_GATE_FALSE",)
        return (
            f"{self.acceptance_id} is not accepted: status={self.acceptance_status}; "
            f"oracle={self.oracle_status}; reasons={','.join(details)}"
        )


def _load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _load_object(path: Path) -> dict[str, Any]:
    value = _load_json(path)
    if not isinstance(value, dict):
        raise AcceptanceEvidenceError(f"JSON root is not an object: {path.name}")
    return cast(dict[str, Any], value)


def _sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _sha256_file(path: Path) -> str:
    return _sha256_bytes(path.read_bytes())


def _canonical_sha256(value: object) -> str:
    rendered = json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return _sha256_bytes(rendered)


def render_json(value: object) -> str:
    return json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n"


def _validate_timestamp(value: str) -> None:
    if UTC_TIMESTAMP.fullmatch(value) is None:
        raise AcceptanceEvidenceError("observed_at_utc must be second-precision RFC 3339 UTC")
    parsed = datetime.fromisoformat(value.removesuffix("Z") + "+00:00")
    if parsed.tzinfo != UTC:
        raise AcceptanceEvidenceError("observed_at_utc must use UTC")


def _validate_commit_ancestor(root: Path, value: str, field: str) -> None:
    if COMMIT.fullmatch(value) is None:
        raise AcceptanceEvidenceError(f"{field} must be a lowercase Git commit")
    completed = subprocess.run(
        ["git", "-C", str(root), "merge-base", "--is-ancestor", value, "HEAD"],
        check=False,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    if completed.returncode != 0:
        raise AcceptanceEvidenceError(f"{field} is not an ancestor of HEAD")


def _is_shallow_repository(root: Path) -> bool:
    completed = subprocess.run(
        ["git", "-C", str(root), "rev-parse", "--is-shallow-repository"],
        check=False,
        capture_output=True,
        text=True,
        encoding="utf-8",
    )
    return completed.returncode == 0 and completed.stdout.strip() == "true"


def _portable_remediation_base_is_bound(root: Path, value: str) -> bool:
    provenance_path = root / PORTABLE_SOURCE_PROVENANCE
    if not provenance_path.is_file() or provenance_path.is_symlink():
        return False
    try:
        provenance = _load_object(provenance_path)
    except (AcceptanceEvidenceError, OSError, UnicodeDecodeError, json.JSONDecodeError):
        return False
    return (
        provenance.get("schema_version") == PORTABLE_SOURCE_PROVENANCE_SCHEMA
        and provenance.get("effective_package", {}).get("version") == PORTABLE_PACKAGE_VERSION
        and provenance.get("candidate_snapshot")
        == {
            "repository": "LinzeColin/MetaDatabase",
            "mainline_base_commit": CURRENT_MAINLINE_BASE_COMMIT,
            "acceptance_remediation_base_commit": ACCEPTANCE_REMEDIATION_BASE_COMMIT,
            "shallow_checkout_fallback": "EXACT_PIN_ONLY",
        }
        and value == ACCEPTANCE_REMEDIATION_BASE_COMMIT
    )


def _validate_remediation_base(root: Path, value: str) -> None:
    try:
        _validate_commit_ancestor(root, value, "remediation_base_commit")
    except AcceptanceEvidenceError:
        # actions/checkout intentionally fetches only the candidate tip. In that
        # environment, accept only the exact current-package provenance tuple; a
        # full repository still requires the ordinary ancestry gate.
        if _is_shallow_repository(root) and _portable_remediation_base_is_bound(root, value):
            return
        raise


def _safe_relative(root: Path, relative: str) -> Path:
    path = (root / relative).resolve()
    try:
        path.relative_to(root.resolve())
    except ValueError as exc:
        raise AcceptanceEvidenceError(f"path escapes project root: {relative}") from exc
    return path


def _contract_items(root: Path) -> tuple[dict[str, Any], ...]:
    value = _load_object(root / ACCEPTANCE_CONTRACT).get("acceptance_contracts")
    if not isinstance(value, list) or not all(isinstance(item, dict) for item in value):
        raise AcceptanceEvidenceError("acceptance contract collection is invalid")
    return tuple(cast(dict[str, Any], item) for item in value)


def _requirement_items(root: Path) -> tuple[dict[str, Any], ...]:
    value = _load_object(root / REQUIREMENTS_CONTRACT).get("requirements")
    if not isinstance(value, list) or not all(isinstance(item, dict) for item in value):
        raise AcceptanceEvidenceError("requirements contract collection is invalid")
    return tuple(cast(dict[str, Any], item) for item in value)


def _traceability_rows(root: Path) -> tuple[dict[str, str], ...]:
    with (root / TRACEABILITY_CONTRACT).open(encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        rows = tuple(dict(row) for row in reader)
    required = {
        "requirement_id",
        "requirement_title",
        "acceptance_id",
        "task_ids",
        "test",
        "evidence",
        "artifact",
        "pass_gate",
    }
    if len(rows) != 34 or reader.fieldnames is None or set(reader.fieldnames) != required:
        raise AcceptanceEvidenceError("traceability matrix shape is invalid")
    return rows


def _verification_test_path(command: object, acceptance_id: str) -> Path:
    if not isinstance(command, str):
        raise AcceptanceEvidenceError(f"{acceptance_id} verification is not a command")
    tokens = shlex.split(command)
    expected = [
        "python",
        "-m",
        "pytest",
        "-q",
        f"tests/acceptance/test_ac_{acceptance_id[-3:]}.py",
    ]
    if tokens != expected:
        raise AcceptanceEvidenceError(f"{acceptance_id} verification command drifted")
    return Path(tokens[-1])


def contract_bindings(root: Path = PROJECT_ROOT) -> dict[str, ContractBinding]:
    root = root.resolve()
    acceptances = _contract_items(root)
    requirements = _requirement_items(root)
    traces = _traceability_rows(root)
    acceptance_map = {str(item.get("id")): item for item in acceptances}
    requirement_map = {str(item.get("id")): item for item in requirements}
    trace_map = {row["acceptance_id"]: row for row in traces}
    if (
        tuple(sorted(acceptance_map)) != EXPECTED_ACCEPTANCE_IDS
        or tuple(sorted(requirement_map)) != EXPECTED_REQUIREMENT_IDS
        or len(acceptance_map) != len(acceptances)
        or len(requirement_map) != len(requirements)
        or len(trace_map) != len(traces)
        or tuple(sorted(trace_map)) != EXPECTED_ACCEPTANCE_IDS
    ):
        raise AcceptanceEvidenceError("34-item contract identity is incomplete or duplicated")

    bindings: dict[str, ContractBinding] = {}
    for acceptance_id in EXPECTED_ACCEPTANCE_IDS:
        acceptance = acceptance_map[acceptance_id]
        requirement_id = acceptance.get("requirement_id")
        requirement = requirement_map.get(str(requirement_id))
        trace = trace_map[acceptance_id]
        if requirement is None or trace["requirement_id"] != requirement_id:
            raise AcceptanceEvidenceError(f"{acceptance_id} requirement binding is invalid")
        test_path = _verification_test_path(acceptance.get("verification"), acceptance_id)
        evidence_value = acceptance.get("evidence_required")
        expected_prefix = f"evidence/acceptance/{acceptance_id}-"
        if (
            not isinstance(evidence_value, str)
            or trace["evidence"] != evidence_value
            or not evidence_value.startswith(expected_prefix)
            or not evidence_value.endswith(".json")
        ):
            raise AcceptanceEvidenceError(f"{acceptance_id} evidence binding is invalid")
        _safe_relative(root, evidence_value)
        if (
            trace["test"] != acceptance.get("verification")
            or trace["pass_gate"] != acceptance.get("pass_gate")
            or trace["requirement_title"] != requirement.get("title")
        ):
            raise AcceptanceEvidenceError(f"{acceptance_id} traceability drifted")
        task_ids = trace["task_ids"].split(";")
        if (
            not task_ids
            or len(task_ids) != len(set(task_ids))
            or any(TASK_ID.fullmatch(task_id) is None for task_id in task_ids)
        ):
            raise AcceptanceEvidenceError(f"{acceptance_id} task binding is invalid")
        bindings[acceptance_id] = ContractBinding(
            acceptance=acceptance,
            requirement=requirement,
            traceability=trace,
            test_path=test_path,
            evidence_path=Path(evidence_value),
        )
    return bindings


def _assert_test_entry(root: Path, binding: ContractBinding) -> dict[str, str]:
    acceptance_id = str(binding.acceptance["id"])
    path = _safe_relative(root, binding.test_path.as_posix())
    if not path.is_file() or path.is_symlink():
        raise AcceptanceEvidenceError(f"{acceptance_id} test entry is missing or unsafe")
    try:
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=path.as_posix())
    except (OSError, UnicodeDecodeError, SyntaxError) as exc:
        raise AcceptanceEvidenceError(f"{acceptance_id} test entry is unreadable") from exc
    imports = [node for node in tree.body if isinstance(node, ast.ImportFrom)]
    if (
        len(tree.body) != 2
        or tree.type_ignores
        or len(imports) != 1
        or imports[0].module != "_assertions"
        or imports[0].level != 0
        or [(item.name, item.asname) for item in imports[0].names]
        != [("assert_final_acceptance", None)]
    ):
        raise AcceptanceEvidenceError(f"{acceptance_id} test entry imports an unsafe gate")
    expected_function = f"test_ac_{acceptance_id[-3:]}_pass_gate"
    functions = [node for node in tree.body if isinstance(node, ast.FunctionDef)]
    target = next((node for node in functions if node.name == expected_function), None)
    if (
        target is None
        or tree.body != [imports[0], target]
        or target.decorator_list
        or not isinstance(target.returns, ast.Constant)
        or target.returns.value is not None
        or target.type_comment is not None
        or getattr(target, "type_params", [])
        or target.args.posonlyargs
        or target.args.args
        or target.args.vararg is not None
        or target.args.kwonlyargs
        or target.args.kw_defaults
        or target.args.kwarg is not None
        or target.args.defaults
        or len(target.body) != 1
    ):
        raise AcceptanceEvidenceError(f"{acceptance_id} test entry does not enforce its pass gate")
    statement = target.body[0]
    call = statement.value if isinstance(statement, ast.Expr) else None
    if (
        not isinstance(call, ast.Call)
        or not isinstance(call.func, ast.Name)
        or call.func.id != "assert_final_acceptance"
        or len(call.args) != 1
        or call.keywords
        or not isinstance(call.args[0], ast.Constant)
        or call.args[0].value != acceptance_id
    ):
        raise AcceptanceEvidenceError(f"{acceptance_id} test entry is not fail-closed")
    return {
        "path": binding.test_path.as_posix(),
        "entrypoint": expected_function,
        "sha256": _sha256_file(path),
    }


def _linked_claim(record: dict[str, Any], acceptance_id: str) -> tuple[str, str]:
    values = record.get("linked_final_acceptance")
    if not isinstance(values, list):
        return "NO_FINAL_CLAIM", "The source task evidence has no final Acceptance claim."
    matches = [
        item for item in values if isinstance(item, dict) and item.get("id") == acceptance_id
    ]
    if not matches:
        return "NO_FINAL_CLAIM", "The source task evidence has no claim for this Acceptance."
    if len(matches) != 1:
        raise AcceptanceEvidenceError(f"duplicate linked final claim for {acceptance_id}")
    item = cast(dict[str, Any], matches[0])
    status = item.get("status")
    reason = item.get("reason")
    if status not in FINAL_CLAIM_STATUSES or not isinstance(reason, str) or not reason:
        raise AcceptanceEvidenceError(f"invalid linked final claim for {acceptance_id}")
    return str(status), reason


def _task_evidence(
    root: Path,
    acceptance_id: str,
    task_ids: tuple[str, ...],
) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    for task_id in task_ids:
        relative = Path("evidence/tasks") / f"{task_id}.json"
        path = _safe_relative(root, relative.as_posix())
        if not path.is_file() or path.is_symlink():
            raise AcceptanceEvidenceError(f"linked task evidence is missing: {task_id}")
        record = _load_object(path)
        if record.get("task_id") != task_id:
            raise AcceptanceEvidenceError(f"linked task evidence identity drifted: {task_id}")
        status, reason = _linked_claim(record, acceptance_id)
        source_status = record.get("record_status")
        if not isinstance(source_status, str) or not source_status:
            raise AcceptanceEvidenceError(f"linked task record status is invalid: {task_id}")
        result.append(
            {
                "task_id": task_id,
                "evidence_ref": relative.as_posix(),
                "evidence_sha256": _sha256_file(path),
                "source_record_status": source_status,
                "final_claim_status": status,
                "reason": reason,
            }
        )
    return result


def _schema_validator(root: Path, relative: Path) -> Draft202012Validator:
    schema = _load_object(root / relative)
    Draft202012Validator.check_schema(schema)
    return Draft202012Validator(schema, format_checker=FormatChecker())


def _oracle_contract_binding(binding: ContractBinding) -> dict[str, str]:
    acceptance = binding.acceptance
    return {
        "acceptance_contract_sha256": _canonical_sha256(acceptance),
        "environment_sha256": _canonical_sha256(acceptance["environment"]),
        "input_sha256": _canonical_sha256(acceptance["input"]),
        "oracle_sha256": _canonical_sha256(acceptance["oracle"]),
        "threshold_sha256": _canonical_sha256(acceptance["threshold"]),
        "pass_gate_sha256": _canonical_sha256(acceptance["pass_gate"]),
    }


def _oracle_observations(root: Path, binding: ContractBinding) -> list[dict[str, Any]]:
    acceptance_id = str(binding.acceptance["id"])
    validator = _schema_validator(root, ORACLE_SCHEMA)
    directory = root / "evidence/acceptance/oracles"
    result: list[dict[str, Any]] = []
    for path in sorted(directory.glob(f"{acceptance_id}-*.json")) if directory.is_dir() else ():
        if not path.is_file() or path.is_symlink():
            raise AcceptanceEvidenceError(f"unsafe Oracle observation: {path.name}")
        record = _load_object(path)
        errors = sorted(validator.iter_errors(record), key=lambda item: list(item.path))
        if errors:
            raise AcceptanceEvidenceError(
                f"Oracle observation schema failed: {path.name}:{errors[0].message}"
            )
        if record.get("acceptance_id") != acceptance_id:
            raise AcceptanceEvidenceError(f"Oracle observation identity drifted: {path.name}")
        if record.get("contract_binding") != _oracle_contract_binding(binding):
            raise AcceptanceEvidenceError(f"Oracle observation contract drifted: {path.name}")
        _validate_commit_ancestor(root, str(record.get("source_commit", "")), "source_commit")
        for evidence in cast(list[dict[str, Any]], record["evidence_refs"]):
            evidence_path = _safe_relative(root, str(evidence["path"]))
            if (
                not evidence_path.is_file()
                or evidence_path.is_symlink()
                or _sha256_file(evidence_path) != evidence["sha256"]
            ):
                raise AcceptanceEvidenceError(
                    f"Oracle observation evidence is missing or changed: {path.name}"
                )
        result.append(
            {
                "observation_ref": path.relative_to(root).as_posix(),
                "observation_sha256": _sha256_file(path),
                "oracle_id": record["oracle_id"],
                "environment": record["environment"],
                "status": record["status"],
                "observed_at_utc": record["observed_at_utc"],
            }
        )
    return result


def _oracle_status(observations: list[dict[str, Any]]) -> str:
    if not observations:
        return "NOT_RUN"
    return "PASS" if all(item["status"] == "PASS" for item in observations) else "FAIL"


def _blockers(
    linked: list[dict[str, Any]],
    oracle_status: str,
) -> list[str]:
    blockers: set[str] = set()
    explicit = [
        item["final_claim_status"]
        for item in linked
        if item["final_claim_status"] != "NO_FINAL_CLAIM"
    ]
    if not explicit:
        blockers.add("NO_LINKED_FINAL_ACCEPTANCE_CLAIMS")
    if any(status == "PARTIAL" for status in explicit):
        blockers.add("LINKED_TASK_CLAIMS_PARTIAL")
    if any(status in {"NOT_RUN", "BLOCKED"} for status in explicit):
        blockers.add("LINKED_TASK_CLAIMS_NOT_RUN")
    if oracle_status == "NOT_RUN":
        blockers.add("FINAL_ORACLE_NOT_EXECUTED")
    elif oracle_status == "FAIL":
        blockers.add("FINAL_ORACLE_FAILED")
    return sorted(blockers)


def build_record(
    root: Path,
    binding: ContractBinding,
    *,
    observed_at_utc: str,
    remediation_base_commit: str,
) -> dict[str, Any]:
    root = root.resolve()
    acceptance_id = str(binding.acceptance["id"])
    _validate_timestamp(observed_at_utc)
    if COMMIT.fullmatch(remediation_base_commit) is None:
        raise AcceptanceEvidenceError("remediation_base_commit must be a lowercase Git commit")
    test_entry = _assert_test_entry(root, binding)
    task_ids = tuple(binding.traceability["task_ids"].split(";"))
    linked = _task_evidence(root, acceptance_id, task_ids)
    observations = _oracle_observations(root, binding)
    oracle_status = _oracle_status(observations)
    blockers = _blockers(linked, oracle_status)
    explicit_claims = [
        item["final_claim_status"]
        for item in linked
        if item["final_claim_status"] != "NO_FINAL_CLAIM"
    ]
    passed = bool(
        oracle_status == "PASS"
        and explicit_claims
        and all(status == "PASS" for status in explicit_claims)
        and not blockers
    )
    acceptance_status = "PASS" if passed else "BLOCKED"
    evidence_id = f"{acceptance_id}-RMD01-{observed_at_utc[:10].replace('-', '')}"
    return {
        "schema_version": "moomooau.acceptance-evidence.v1",
        "evidence_id": evidence_id,
        "acceptance_id": acceptance_id,
        "requirement_id": binding.acceptance["requirement_id"],
        "observed_at_utc": observed_at_utc,
        "remediation_base_commit": remediation_base_commit,
        "scope": "LOCAL_ACCEPTANCE_CONTROL_PLANE",
        "record_status": "VALID",
        "delivery_status": "LOCAL_ONLY_NOT_PUBLISHED",
        "acceptance_status": acceptance_status,
        "oracle_status": oracle_status,
        "pass_gate": passed,
        "contract_binding": {
            "contract_ref": ACCEPTANCE_CONTRACT.as_posix(),
            "contract_sha256": _canonical_sha256(binding.acceptance),
            "verification": binding.acceptance["verification"],
            "evidence_required": binding.acceptance["evidence_required"],
            "pass_gate_text": binding.acceptance["pass_gate"],
        },
        "traceability_binding": {
            "traceability_ref": TRACEABILITY_CONTRACT.as_posix(),
            "traceability_row_sha256": _canonical_sha256(binding.traceability),
            "task_ids": list(task_ids),
        },
        "test_entry": test_entry,
        "linked_task_evidence": linked,
        "oracle_observations": observations,
        "checks": [
            {"id": "FROZEN_ACCEPTANCE_CONTRACT_BOUND", "status": "PASS"},
            {"id": "TRACEABILITY_ROW_BOUND", "status": "PASS"},
            {"id": "FAIL_CLOSED_TEST_ENTRY_BOUND", "status": "PASS"},
            {"id": "LINKED_TASK_EVIDENCE_HASH_BOUND", "status": "PASS"},
            {
                "id": "FINAL_ORACLE_AND_THRESHOLD",
                "status": "PASS" if passed else "BLOCKED",
            },
        ],
        "blockers": blockers,
        "prohibition_counters": {name: 0 for name in PROHIBITION_COUNTERS},
        "next_action": (
            "Acceptance is proven; retain immutable evidence and include it in the final review."
            if passed
            else (
                "Execute the exact final Oracle and close every linked PARTIAL/NOT_RUN "
                "claim; do not enable production from this control-plane record."
            )
        ),
    }


def _record_root(rendered_records: dict[Path, str]) -> str:
    payload = b"".join(
        relative.as_posix().encode("utf-8")
        + b"\0"
        + _sha256_bytes(rendered.encode("utf-8")).encode("ascii")
        + b"\n"
        for relative, rendered in sorted(
            rendered_records.items(), key=lambda item: item[0].as_posix()
        )
    )
    return _sha256_bytes(payload)


def build_bundle(
    root: Path = PROJECT_ROOT,
    *,
    observed_at_utc: str,
    remediation_base_commit: str,
) -> dict[Path, str]:
    root = root.resolve()
    _validate_remediation_base(root, remediation_base_commit)
    bindings = contract_bindings(root)
    records: dict[Path, str] = {}
    statuses: dict[str, str] = {}
    blockers: dict[str, list[str]] = {}
    for acceptance_id in EXPECTED_ACCEPTANCE_IDS:
        binding = bindings[acceptance_id]
        record = build_record(
            root,
            binding,
            observed_at_utc=observed_at_utc,
            remediation_base_commit=remediation_base_commit,
        )
        records[binding.evidence_path] = render_json(record)
        statuses[acceptance_id] = str(record["acceptance_status"])
        blockers[acceptance_id] = cast(list[str], record["blockers"])
    passed_ids = [item for item in EXPECTED_ACCEPTANCE_IDS if statuses[item] == "PASS"]
    blocked_ids = [item for item in EXPECTED_ACCEPTANCE_IDS if statuses[item] != "PASS"]
    summary = {
        "schema_version": "moomooau.acceptance-summary.v1",
        "observed_at_utc": observed_at_utc,
        "remediation_base_commit": remediation_base_commit,
        "scope": "LOCAL_ACCEPTANCE_CONTROL_PLANE",
        "delivery_status": "LOCAL_ONLY_NOT_PUBLISHED",
        "status": "PASS" if not blocked_ids else "BLOCKED",
        "total_acceptances": 34,
        "final_acceptances_passed": len(passed_ids),
        "final_acceptances_blocked": len(blocked_ids),
        "passed_acceptance_ids": passed_ids,
        "blocked_acceptance_ids": blocked_ids,
        "blockers_by_acceptance": {item: blockers[item] for item in blocked_ids},
        "record_root_sha256": _record_root(records),
        "prohibition_counters": {name: 0 for name in PROHIBITION_COUNTERS},
        "next_action": (
            "All 34 final Acceptance contracts are proven; proceed only through the "
            "remaining release gates."
            if not blocked_ids
            else (
                "Keep the final release blocked until every exact Acceptance Oracle and "
                "linked claim passes."
            )
        ),
    }
    records[SUMMARY_PATH] = render_json(summary)
    return records


def _schema_errors(validator: Draft202012Validator, value: object) -> tuple[str, ...]:
    return tuple(
        f"schema:{'/'.join(str(part) for part in error.path)}:{error.message}"
        for error in sorted(validator.iter_errors(value), key=lambda item: list(item.path))
    )


def validate_bundle(root: Path = PROJECT_ROOT) -> tuple[str, ...]:
    root = root.resolve()
    summary_path = root / SUMMARY_PATH
    if not summary_path.is_file() or summary_path.is_symlink():
        return ("acceptance summary is missing or unsafe",)
    try:
        summary = _load_object(summary_path)
        observed_at = str(summary.get("observed_at_utc", ""))
        remediation_base = str(summary.get("remediation_base_commit", ""))
        expected = build_bundle(
            root,
            observed_at_utc=observed_at,
            remediation_base_commit=remediation_base,
        )
        record_validator = _schema_validator(root, RECORD_SCHEMA)
        summary_validator = _schema_validator(root, SUMMARY_SCHEMA)
    except (
        AcceptanceEvidenceError,
        OSError,
        UnicodeDecodeError,
        json.JSONDecodeError,
        SchemaError,
    ) as exc:
        return (f"acceptance bundle cannot be derived: {type(exc).__name__}:{exc}",)

    errors: list[str] = []
    expected_paths = set(expected)
    actual_record_paths = {
        path.relative_to(root)
        for path in (root / "evidence/acceptance").glob("AC-*.json")
        if path.is_file() and not path.is_symlink()
    }
    if actual_record_paths != expected_paths - {SUMMARY_PATH}:
        errors.append("acceptance evidence file set differs from the frozen 34 paths")
    for relative, rendered in expected.items():
        path = root / relative
        if not path.is_file() or path.is_symlink():
            errors.append(f"missing or unsafe evidence: {relative.as_posix()}")
            continue
        try:
            actual_text = path.read_text(encoding="utf-8")
            actual = json.loads(actual_text)
        except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
            errors.append(f"invalid evidence JSON: {relative.as_posix()}:{type(exc).__name__}")
            continue
        validator = summary_validator if relative == SUMMARY_PATH else record_validator
        errors.extend(f"{relative.as_posix()}:{item}" for item in _schema_errors(validator, actual))
        if actual_text != rendered:
            errors.append(f"evidence is stale or non-deterministic: {relative.as_posix()}")
    return tuple(errors)


def evaluate_acceptance(
    acceptance_id: str,
    root: Path = PROJECT_ROOT,
    *,
    bundle_errors: tuple[str, ...] | None = None,
) -> AcceptanceEvaluation:
    if acceptance_id not in EXPECTED_ACCEPTANCE_IDS:
        raise AcceptanceEvidenceError(f"unknown final Acceptance: {acceptance_id}")
    root = root.resolve()
    errors = validate_bundle(root) if bundle_errors is None else bundle_errors
    binding = contract_bindings(root)[acceptance_id]
    path = root / binding.evidence_path
    record: dict[str, Any] = {}
    local_errors = list(errors)
    if path.is_file() and not path.is_symlink():
        try:
            record = _load_object(path)
        except (OSError, UnicodeDecodeError, json.JSONDecodeError, AcceptanceEvidenceError) as exc:
            local_errors.append(f"record cannot be read: {type(exc).__name__}")
    else:
        local_errors.append("record is missing or unsafe")
    status = str(record.get("acceptance_status", "INVALID"))
    oracle = str(record.get("oracle_status", "INVALID"))
    blocker_value = record.get("blockers", [])
    blockers = tuple(str(item) for item in blocker_value) if isinstance(blocker_value, list) else ()
    valid = not local_errors
    passed = valid and status == "PASS" and oracle == "PASS" and record.get("pass_gate") is True
    return AcceptanceEvaluation(
        acceptance_id=acceptance_id,
        valid=valid,
        passed=passed,
        acceptance_status=status,
        oracle_status=oracle,
        blockers=blockers,
        errors=tuple(local_errors),
        evidence_path=binding.evidence_path.as_posix(),
    )


def evaluate_all(root: Path = PROJECT_ROOT) -> tuple[AcceptanceEvaluation, ...]:
    errors = validate_bundle(root)
    return tuple(
        evaluate_acceptance(acceptance_id, root, bundle_errors=errors)
        for acceptance_id in EXPECTED_ACCEPTANCE_IDS
    )
