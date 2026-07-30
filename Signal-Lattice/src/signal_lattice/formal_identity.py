from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any

from .receipts import canonical_json_bytes, sha256_file

EXCLUDED_PREFIXES = ("evidence/",)
EXCLUDED = {
    "MANIFEST.json",
    "SUBJECT_LOCK.json",
    "CANONICAL_STATE.json",
    "machine/facts/owner_gate.json",
    "evidence/skill_router/pass_c.json",
}
GARBAGE_PARTS = {".git", "__pycache__", "build", "dist", ".venv", "venv", ".pytest_cache"}
EXCLUDED_SUFFIXES = (".pyc", ".pyo", ".zip", ".whl")

BINDING_PATHS = {
    "quant": "evidence/quant/quant_seal.json",
    "acceptance": "machine/facts/acceptance_contract.json",
    "requirements": "machine/facts/requirements.json",
    "task_dag": "machine/facts/task_dag.json",
    "traceability": "machine/facts/traceability.json",
    "definition_of_done": "machine/facts/definition_of_done.json",
    "release_boundary": "machine/facts/release_boundary.json",
    "candidate_contract_snapshot": "machine/facts/candidate_contract_snapshot.json",
    "freeze_receipt": "evidence/owner_gate/candidate_freeze.json",
    "canonical_state_prepared": "CANONICAL_STATE.json",
}


def subject_rows(root: Path) -> list[dict[str, Any]]:
    root = root.resolve()
    rows: list[dict[str, Any]] = []
    for path in sorted(root.rglob("*")):
        if not path.is_file() or path.is_symlink():
            continue
        rel = path.relative_to(root).as_posix()
        if rel in EXCLUDED or any(rel.startswith(prefix) for prefix in EXCLUDED_PREFIXES):
            continue
        if any(part in GARBAGE_PARTS or part.endswith((".egg-info", ".dist-info")) for part in path.parts):
            continue
        if rel.endswith(EXCLUDED_SUFFIXES):
            continue
        rows.append({"path": rel, "size": path.stat().st_size, "sha256": sha256_file(path)})
    return rows


def subject_identity_sha256(files: list[dict[str, Any]], bindings: dict[str, str]) -> str:
    return hashlib.sha256(canonical_json_bytes({"files": files, "bindings": bindings})).hexdigest()


def verify_subject_against_root(subject: dict[str, Any], root: Path, *, require_frozen: bool = True) -> list[str]:
    findings: list[str] = []
    expected_state = "FROZEN" if require_frozen else subject.get("state")
    if require_frozen and subject.get("state") != expected_state:
        findings.append("SUBJECT_NOT_FROZEN")
    files = subject.get("files")
    bindings = subject.get("bindings")
    if not isinstance(files, list) or not isinstance(bindings, dict):
        findings.append("SUBJECT_STRUCTURE_INVALID")
        return findings
    if subject.get("subject_sha256") != subject_identity_sha256(files, bindings):
        findings.append("SUBJECT_IDENTITY_INVALID")
    binding_paths = dict(BINDING_PATHS)
    binding_paths["upstream"] = (
        "evidence/upstream/upstream_seal.json"
        if subject.get("upstream_binding_kind") == "formal_seal"
        else "evidence/upstream/upstream_precheck.json"
    )
    for name, expected in bindings.items():
        rel = binding_paths.get(str(name))
        if rel is None:
            findings.append("SUBJECT_BINDING_PATH_UNKNOWN:" + str(name))
            continue
        path = root / rel
        if not path.is_file():
            findings.append("SUBJECT_BINDING_MISSING:" + str(name))
        elif sha256_file(path) != expected:
            findings.append("SUBJECT_BINDING_DRIFT:" + str(name))

    actual = subject_rows(root)
    if files != actual:
        expected_by_path = {str(row.get("path")): row for row in files if isinstance(row, dict)}
        actual_by_path = {str(row.get("path")): row for row in actual if isinstance(row, dict)}
        for rel in sorted(set(expected_by_path) - set(actual_by_path)):
            findings.append("SUBJECT_FILE_MISSING:" + rel)
        for rel in sorted(set(actual_by_path) - set(expected_by_path)):
            findings.append("SUBJECT_FILE_UNRECORDED:" + rel)
        for rel in sorted(set(expected_by_path) & set(actual_by_path)):
            if expected_by_path[rel] != actual_by_path[rel]:
                findings.append("SUBJECT_FILE_DRIFT:" + rel)
        if not findings or findings == ["SUBJECT_NOT_FROZEN"]:
            findings.append("SUBJECT_FILE_SET_OR_CONTENT_DRIFT")
    return findings
