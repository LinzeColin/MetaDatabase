#!/usr/bin/env python3
"""Fail-closed, read-only cumulative validator for MooMooAU Stage 2."""

from __future__ import annotations

import argparse
import hashlib
import io
import json
import sys
import tempfile
from pathlib import Path
from typing import Any

sys.dont_write_bytecode = True

PROJECT_ROOT = Path(__file__).resolve().parents[4]
REPOSITORY_ROOT = PROJECT_ROOT.parents[1]
STAGE1_TOOLS = PROJECT_ROOT / "machine/stages/S1/tools"
STAGE2_TOOLS = PROJECT_ROOT / "machine/stages/S2/tools"
TOOLS = PROJECT_ROOT / "machine/tools"
SRC = PROJECT_ROOT / "src"
STAGE2_WORKFLOW = REPOSITORY_ROOT / ".github/workflows/moomooau-stage2-security.yml"
BASELINE_COMMIT = "932e3970490f87fd46671bc6a461340a339887ef"
BASELINE_MANIFEST_SHA256 = "c2783bd232062ca123a725a3db2cf26a36c4a99a9476c432c36c850f86675c7f"
STAGE2_TASKS = [f"T020{i}" for i in range(1, 8)]
STAGE2_ACCEPTANCES = [f"S2AC-00{i}" for i in range(1, 8)]
IGNORED_PARTS = {
    "__pycache__",
    ".mypy_cache",
    ".pytest_cache",
    ".ruff_cache",
    "build",
    "dist",
}

for import_path in (STAGE1_TOOLS, STAGE2_TOOLS, TOOLS, SRC):
    if str(import_path) not in sys.path:
        sys.path.insert(0, str(import_path))

from validate_publication import (  # noqa: E402
    EMAIL,
    LOCAL_PATH,
    REPOSITORY_TOKEN,
    SECRET_PATTERNS,
    scan_tree,
)
from validate_stage1 import evaluate_stage1  # noqa: E402
from validate_supply_chain import validate_supply_chain  # noqa: E402

from moomooau_archive.age_stream import OfficialAgeStream, is_age_envelope  # noqa: E402
from moomooau_archive.auth import (  # noqa: E402
    GMAIL_MODIFY_SCOPE,
    GMAIL_OAUTH_SECRET_NAME,
    load_gmail_oauth_credential,
)
from moomooau_archive.github_guard import (  # noqa: E402
    GitHubBoundaryError,
    GitHubEndpointGuard,
    RepositoryLocator,
    TargetRepositoryConfig,
    content_url,
)
from moomooau_archive.gmail_guard import (  # noqa: E402
    GmailEndpointGuard,
    GmailEndpointRejected,
    get_message_request,
    list_filters_request,
    list_history_request,
    list_messages_request,
    trash_message_request,
)
from moomooau_archive.http_boundary import HttpRequest, HttpResponse  # noqa: E402
from moomooau_archive.recovery import AgeIdentityGenerator  # noqa: E402
from moomooau_archive.secret_values import SecretText  # noqa: E402


def _load(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _check(check_id: str, passed: bool, detail: str) -> dict[str, str]:
    return {"id": check_id, "status": "PASS" if passed else "FAIL", "detail": detail}


def _tree_digest(root: Path) -> str:
    digest = hashlib.sha256()
    paths = [
        path
        for path in root.rglob("*")
        if path.is_file() and not path.is_symlink() and not (set(path.parts) & IGNORED_PARTS)
    ]
    for workflow in (
        REPOSITORY_ROOT / ".github/workflows/moomooau-stage1-ci.yml",
        STAGE2_WORKFLOW,
    ):
        if workflow.is_file():
            paths.append(workflow)
    for path in sorted(paths, key=str):
        relative = (
            path.relative_to(root).as_posix()
            if path.is_relative_to(root)
            else path.relative_to(REPOSITORY_ROOT).as_posix()
        )
        digest.update(relative.encode() + b"\0" + path.read_bytes() + b"\0")
    return digest.hexdigest()


def _validate_stage2_contracts(root: Path) -> list[str]:
    errors: list[str] = []
    graph = _load(root / "machine/contracts/task_graph.json")
    graph_tasks = {item["id"]: item for item in graph["tasks"] if item["stage_id"] == "S2"}
    local = _load(root / "machine/stages/S2/contracts/stage2_acceptance_contract.json")
    items = local.get("acceptance_contracts", [])
    if [item.get("id") for item in items] != STAGE2_ACCEPTANCES:
        errors.append("Stage 2 acceptance IDs must be ordered and unique")
    if [item.get("task_id") for item in items] != STAGE2_TASKS:
        errors.append("Stage 2 acceptance to task mapping must be one-to-one")
    required_fields = {
        "title",
        "environment",
        "input",
        "oracle",
        "threshold",
        "evidence_required",
        "verification",
        "failure_action",
    }
    for item in items:
        task = graph_tasks.get(item.get("task_id"))
        if task is None or item.get("linked_final_acceptance_ids") != task.get("acceptance_ids"):
            errors.append("Stage 2 final acceptance links drift from the frozen task graph")
        if not required_fields.issubset(item) or any(
            not str(item.get(field, "")).strip() for field in required_fields
        ):
            errors.append("Stage 2 acceptance contract is incomplete")
    if len(graph_tasks) != 7:
        errors.append("Stage 2 must contain exactly seven frozen tasks")
    expected_dependencies = {
        "T0201": ["T0107"],
        "T0202": ["T0201"],
        "T0203": ["T0202"],
        "T0204": ["T0203"],
        "T0205": ["T0204"],
        "T0206": ["T0205"],
        "T0207": ["T0206"],
    }
    if any(
        graph_tasks[task_id].get("dependencies") != dependencies
        for task_id, dependencies in expected_dependencies.items()
    ):
        errors.append("Stage 2 dependency chain drifts from the frozen task graph")
    return errors


class _RecordingTransport:
    def __init__(self) -> None:
        self.requests: list[HttpRequest] = []

    def send(self, request: HttpRequest) -> HttpResponse:
        self.requests.append(request)
        return HttpResponse(200, b"{}")


class _SyntheticSecretSource:
    def __init__(self) -> None:
        self.reads: list[str] = []

    def read(self, name: str) -> SecretText:
        self.reads.append(name)
        payload = {
            "type": "authorized_user",
            "client_id": "synthetic-client-id",
            "client_secret": "synthetic-client-value",
            "refresh_token": "synthetic-refresh-value",
            "token_uri": "https://oauth2.googleapis.com/token",
            "scopes": [GMAIL_MODIFY_SCOPE],
        }
        return SecretText(json.dumps(payload, sort_keys=True))


def _validate_identity_and_endpoint_boundaries() -> list[str]:
    errors: list[str] = []
    source = _SyntheticSecretSource()
    credential = load_gmail_oauth_credential(source)
    if source.reads != [GMAIL_OAUTH_SECRET_NAME] or "synthetic-client-id" in repr(credential):
        errors.append("single OAuth Secret boundary failed")
    credential.destroy()

    gmail_transport = _RecordingTransport()
    gmail = GmailEndpointGuard(gmail_transport)
    for request in (
        list_messages_request((("maxResults", "10"),)),
        get_message_request("synthetic_message", message_format="raw"),
        list_history_request("123"),
        list_filters_request(),
        trash_message_request("synthetic_message"),
    ):
        gmail.send(request)
    forbidden = (
        HttpRequest(
            "POST", "https://gmail.googleapis.com/gmail/v1/users/me/messages/send", body=b"{}"
        ),
        HttpRequest("DELETE", "https://gmail.googleapis.com/gmail/v1/users/me/messages/synthetic"),
        HttpRequest("GET", "https://gmail.googleapis.com/gmail/v1/users/me/threads"),
        HttpRequest("POST", "https://gmail.googleapis.com/batch/gmail/v1", body=b"{}"),
        HttpRequest(
            "POST",
            "https://gmail.googleapis.com/gmail/v1/users/me/messages/synthetic/modify",
            body=b"{}",
        ),
    )
    for request in forbidden:
        try:
            gmail.send(request)
        except GmailEndpointRejected:
            pass
        else:
            errors.append("forbidden Gmail request escaped the endpoint guard")
    if len(gmail_transport.requests) != 5 or gmail.metrics.forbidden_network_calls != 0:
        errors.append("Gmail guard transport cardinality failed")

    config = TargetRepositoryConfig(repository_id=7200001, installation_id=8200001)
    github_transport = _RecordingTransport()
    github = GitHubEndpointGuard(github_transport, config)
    locator = RepositoryLocator(config.repository_id, "synthetic-owner", "synthetic-target")
    github.bind_repository(locator)
    github.send(HttpRequest("GET", content_url(locator, "MooMooAU/Raw/object.age")))
    try:
        github.send(
            HttpRequest(
                "GET",
                "https://api.github.com/repos/synthetic-owner/other-target/contents/"
                "MooMooAU/Raw/object.age",
            )
        )
    except GitHubBoundaryError:
        pass
    else:
        errors.append("cross-repository request escaped the GitHub guard")
    if len(github_transport.requests) != 1 or github.metrics.cross_repository_network_calls != 0:
        errors.append("GitHub guard transport cardinality failed")
    return errors


def _validate_streaming_age() -> list[str]:
    generated = AgeIdentityGenerator().generate()
    payload = b"synthetic-stage2-stream" * 1024
    try:
        with tempfile.TemporaryDirectory(prefix="moomooau-s2-validator-") as directory:
            root = Path(directory)
            identity = root / "synthetic-identity.txt"
            identity.write_bytes(generated.identity.reveal())
            identity.chmod(0o600)
            encrypted = io.BytesIO()
            cipher = OfficialAgeStream(chunk_size=4096)
            cipher.encrypt_stream(generated.recipient, io.BytesIO(payload), encrypted)
            ciphertext = encrypted.getvalue()
            recovered = io.BytesIO()
            cipher.decrypt_stream(
                identity,
                io.BytesIO(ciphertext),
                recovered,
                allowed_tmpfs_roots=(root,),
            )
            if not is_age_envelope(ciphertext) or recovered.getvalue() != payload:
                return ["official age streaming round-trip failed"]
    except Exception as exc:
        return [f"official age streaming boundary failed: {type(exc).__name__}"]
    finally:
        generated.destroy()
    return []


def _validate_public_surfaces(root: Path) -> list[str]:
    errors: list[str] = []
    publication = scan_tree(root)
    if publication["status"] != "PASS":
        errors.append("project publication scan found forbidden values")
    workflow = STAGE2_WORKFLOW.read_text(encoding="utf-8") if STAGE2_WORKFLOW.is_file() else ""
    if (
        EMAIL.search(workflow)
        or LOCAL_PATH.search(workflow)
        or any(pattern.search(workflow) for pattern in SECRET_PATTERNS)
    ):
        errors.append("Stage 2 workflow contains a forbidden sensitive pattern")
    contract = _load(root / "machine/contracts/publication_safety.json")
    forbidden_hashes = set(contract["forbidden_locator_sha256_casefold"])
    if any(
        hashlib.sha256(token.casefold().encode()).hexdigest() in forbidden_hashes
        for token in REPOSITORY_TOKEN.findall(workflow)
    ):
        errors.append("Stage 2 workflow contains a forbidden private locator")
    return errors


def _validate_evidence(root: Path) -> list[str]:
    from jsonschema import Draft202012Validator, FormatChecker

    errors: list[str] = []
    schema = _load(root / "machine/stages/S2/schemas/stage2-evidence-v1.schema.json")
    validator = Draft202012Validator(schema, format_checker=FormatChecker())
    graph = _load(root / "machine/contracts/task_graph.json")
    graph_tasks = {item["id"]: item for item in graph["tasks"] if item["stage_id"] == "S2"}
    for index, task_id in enumerate(STAGE2_TASKS, start=1):
        path = root / "evidence/tasks" / f"{task_id}.json"
        if not path.is_file():
            errors.append(f"missing evidence for {task_id}")
            continue
        record = _load(path)
        if list(validator.iter_errors(record)):
            errors.append(f"invalid evidence schema for {task_id}")
            continue
        if record["stage_acceptance_id"] != f"S2AC-00{index}" or record["record_status"] != "PASS":
            errors.append(f"evidence identity or status mismatch for {task_id}")
        if any(item["status"] != "PASS" for item in record["checks"]):
            errors.append(f"non-passing Stage 2 check for {task_id}")
        linked = record["linked_final_acceptance"]
        if [item["id"] for item in linked] != graph_tasks[task_id]["acceptance_ids"] or any(
            item["status"] not in {"PARTIAL", "NOT_RUN"} for item in linked
        ):
            errors.append(f"final acceptance status is overstated for {task_id}")
        if any(record["prohibition_counters"].values()):
            errors.append(f"prohibition counter is nonzero for {task_id}")

    task_status = _load(root / "machine/stages/S2/contracts/task_status.json")
    if (
        [item.get("id") for item in task_status.get("tasks", [])] != STAGE2_TASKS
        or any(item.get("status") != "completed" for item in task_status.get("tasks", []))
        or task_status.get("baseline_commit") != BASELINE_COMMIT
        or task_status.get("later_stage_status") != "planned_unchanged"
    ):
        errors.append("Stage 2 task status overlay is incomplete")

    latest = _load(root / "evidence/stage2/latest.json")
    supply = latest.get("supply_chain_observation", {})
    if (
        latest.get("stage_id") != "S2"
        or latest.get("status") != "PASS"
        or latest.get("task_pass_count") != 7
        or latest.get("task_total") != 7
        or latest.get("final_acceptance_policy") != "NOT_FINAL"
        or latest.get("final_acceptances_passed") != 0
        or latest.get("protected_oracles_executed") != 0
        or any(latest.get("prohibition_counters", {}).values())
        or supply.get("hash_locked_packages") != 78
        or supply.get("sbom_components") != 78
        or supply.get("sbom_root_direct_edges") != 14
        or supply.get("sbom_dependency_nodes_with_edges") != 34
        or supply.get("native_pip_hash_install") != "PASS"
        or supply.get("digest_pinned_container_build") != "PASS"
        or supply.get("network_none_read_only_container_smoke") != "PASS"
        or supply.get("remote_codeql") != "NOT_RUN"
        or supply.get("remote_dependency_review") != "NOT_RUN"
    ):
        errors.append("Stage 2 aggregate evidence is not a fail-closed PASS record")

    semantic = _load(root / "machine/stages/S2/contracts/semantic_gate.json")
    resolution_statuses = {item.get("status") for item in semantic.get("resolutions", [])}
    if (
        semantic.get("stage_id") != "S2"
        or semantic.get("status") != "PASS"
        or semantic.get("baseline_commit") != BASELINE_COMMIT
        or not semantic.get("resolutions")
        or not resolution_statuses.issubset({"RESOLVED", "CONTROLLED_NOT_RUN"})
        or "CONTROLLED_NOT_RUN" not in resolution_statuses
    ):
        errors.append("Stage 2 semantic gate is incomplete or overstates protected oracles")
    return errors


def evaluate_stage2(
    root: Path = PROJECT_ROOT,
    governance_root: Path | None = None,
    *,
    include_delivery_records: bool = True,
) -> dict[str, Any]:
    root = root.resolve()
    before = _tree_digest(root)
    checks: list[dict[str, str]] = []

    manifest = root / "taskpack/PACKAGE_MANIFEST.v1.0.1.json"
    checks.append(
        _check(
            "baseline.manifest_identity",
            _sha256(manifest) == BASELINE_MANIFEST_SHA256,
            "frozen Stage 0 manifest digest matches the verified handoff",
        )
    )
    stage1 = evaluate_stage1(root, governance_root)
    checks.append(
        _check(
            "baseline.cumulative_stage1",
            stage1["status"] == "PASS",
            f"Stage 1 failed checks {len(stage1['failed_check_ids'])}",
        )
    )

    contract_errors = _validate_stage2_contracts(root)
    checks.append(
        _check(
            "contracts.stage2_overlay",
            not contract_errors,
            f"Stage 2 contract errors {len(contract_errors)}",
        )
    )

    required = [
        root / "src/moomooau_archive/auth.py",
        root / "src/moomooau_archive/gmail_guard.py",
        root / "src/moomooau_archive/github_guard.py",
        root / "src/moomooau_archive/age_stream.py",
        root / "src/moomooau_archive/recovery.py",
        root / "requirements/stage2.lock",
        root / "machine/stages/S2/tools/validate_supply_chain.py",
        STAGE2_WORKFLOW,
    ] + [root / "tests/tasks" / f"test_{task_id.casefold()}.py" for task_id in STAGE2_TASKS]
    checks.append(
        _check(
            "package.stage2_structure",
            all(path.is_file() for path in required),
            f"required Stage 2 paths {len(required)}",
        )
    )

    boundary_errors = _validate_identity_and_endpoint_boundaries()
    checks.append(
        _check(
            "security.identity_endpoint_guards",
            not boundary_errors,
            f"identity or endpoint errors {len(boundary_errors)}",
        )
    )

    age_errors = _validate_streaming_age()
    checks.append(
        _check(
            "security.official_age_streaming",
            not age_errors,
            f"official age streaming errors {len(age_errors)}",
        )
    )

    supply_errors = validate_supply_chain(root, STAGE2_WORKFLOW)
    checks.append(
        _check(
            "security.immutable_supply_chain",
            not supply_errors,
            f"supply-chain errors {len(supply_errors)}",
        )
    )

    publication_errors = _validate_public_surfaces(root)
    checks.append(
        _check(
            "security.publication",
            not publication_errors,
            f"publication errors {len(publication_errors)}",
        )
    )

    source_text = "\n".join(
        path.read_text(encoding="utf-8") for path in sorted((root / "src").rglob("*.py"))
    )
    prohibited_imports = [
        token
        for token in ("googleapiclient", "google.auth", "httpx", "requests", "smtplib")
        if token in source_text
    ]
    run_contract = _load(root / "machine/stages/S2/contracts/run_contract.json")
    scope_ok = (
        not prohibited_imports
        and run_contract.get("baseline_commit") == BASELINE_COMMIT
        and run_contract.get("stage_id") == "S2"
        and all(value == 0 for value in run_contract.get("prohibitions", {}).values())
    )
    checks.append(
        _check(
            "scope.no_stage3_or_external_authority",
            scope_ok,
            f"prohibited runtime imports {len(prohibited_imports)}",
        )
    )

    if include_delivery_records:
        evidence_errors = _validate_evidence(root)
        checks.append(
            _check(
                "evidence.stage2_records",
                not evidence_errors,
                f"Stage 2 evidence errors {len(evidence_errors)}",
            )
        )

    after = _tree_digest(root)
    checks.append(_check("validator.read_only", before == after, "tree digest unchanged"))
    failed = [item["id"] for item in checks if item["status"] != "PASS"]
    return {
        "schema_version": "moomooau.stage2-verification.v1",
        "stage_id": "S2",
        "status": "PASS" if not failed else "BLOCKED",
        "checks": checks,
        "failed_check_ids": failed,
        "signals": {
            "stage2_tasks": 7,
            "stage2_local_acceptances": 7,
            "real_gmail_calls": 0,
            "gmail_mutations": 0,
            "private_repository_calls": 0,
            "real_secrets_read": 0,
            "protected_key_deliveries": 0,
            "external_writes": 0,
            "remote_publication": 0,
            "protected_oracles_executed": 0,
            "final_acceptances_passed": 0,
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, default=PROJECT_ROOT)
    parser.add_argument("--governance-root", type=Path, required=True)
    args = parser.parse_args()
    result = evaluate_stage2(args.root, args.governance_root)
    print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
    return 0 if result["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
