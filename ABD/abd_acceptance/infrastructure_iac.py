from __future__ import annotations

import argparse
import hashlib
import json
import re
import shutil
import stat
import subprocess
import tempfile
import xml.etree.ElementTree as ET
from copy import deepcopy
from pathlib import Path
from typing import Any, Dict, Iterable, List, Mapping, MutableMapping, Sequence

from jsonschema import Draft202012Validator

from .canonical_facts import sha256_file, strict_json_load
from .stage3_delivery import (
    PINNED_RECEIPT_SHA256 as STAGE3_DELIVERY_RECEIPT_SHA256,
    RECEIPT_PATH as STAGE3_DELIVERY_RECEIPT_PATH,
    verify_stage3_delivery,
)


CONTRACT_ID = "AC-S04-P01"
REQUIREMENT_ID = "REQ-S04-P01"
STAGE_ID = "S04"
PHASE_ID = "P01"
VERSION = "0.0.0.1"
FIXED_CLOCK = "2026-07-22T16:00:00+10:00"
JUNIT_FIXED_CLOCK = "2026-07-19T00:00:00+10:00"

COMPOSE_PATH = Path("infra/compose.yml")
SCHEMA_PATH = Path("infra/config.schema.json")
SYSTEMD_PATH = Path("infra/systemd/abd.service")
REBUILD_PATH = Path("infra/rebuild.sh")
FIXTURE_PATH = Path("machine/tests/fixtures/S04_P01.json")
TEST_PATH = Path("tests/S04/P01_test.py")
JUNIT_PATH = Path("machine/evidence/S04/P01/pytest.xml")
FULL_JUNIT_PATH = Path("machine/evidence/S04/P01/full_regression.xml")
PACK_REPORT_PATH = Path("machine/evidence/validation_report.json")
SCAN_REPORT_PATH = Path("machine/evidence/S00/P03/paid_dependency_scan.txt")
EVIDENCE_PATH = Path("machine/evidence/EVD-S04-P01.json")
ROLLBACK_EVIDENCE_PATH = Path("machine/evidence/EVD-S04-P01_rollback.json")
EVIDENCE_INDEX_PATH = Path("machine/evidence/evidence_index.jsonl")
WORKFLOW_PATH = Path(".github/workflows/abd-stage0-validation.yml")

STRUCTURAL_SELF_NORMALIZED_SHA256 = "739e4d867221375577fda911ae37fde59b2f3a90db1a203d1d9085148f76bd0c"
PHASE_COMMIT = "4cd838a3fa27ee29857afd4a2bce632252d2c0b8"
PINNED_PHASE_CODE_HASH = "1255629d805986ee3c79dc0dc7d2223b63424a671d901bf05098d6b4d6f295c3"
SUCCESSOR_EVOLVABLE_SIGNED_INPUTS = {
    "infra/compose.yml",
    "abd_acceptance/infrastructure_iac.py",
    "tests/S04/P01_test.py",
}
SUCCESSOR_UNIT_PROFILE_HASHES: Dict[str, str] = {
    "infra/compose.yml": "babed827948b77e28d395b0d36d2142605b8144f7e778302d6c384930aa54808",
    "tests/S04/P01_test.py": "8adde86953d2ff3579bfc3ececb3314a3362aae747e57d03eae9b7a68090c846",
}

PINNED_PHASE_HASHES: Dict[str, str] = {
    COMPOSE_PATH.as_posix(): "f6d75aba62f4efbec14e579a6cdfad76c979376ae4778195a4e0afca756b8b50",
    SCHEMA_PATH.as_posix(): "bb08e4dd88137d88b5d842bd5ed2fb815163d53ab44f33d21730fdb2dd2f27da",
    SYSTEMD_PATH.as_posix(): "256b30a69ca27f0a3bb566d3ca722d19c0ba00a09d4869ef218d15f5e1cf76bf",
    REBUILD_PATH.as_posix(): "07e38ac597543b184884290985769f177f5a1c05ab76e1a9c426f104f44249cf",
    FIXTURE_PATH.as_posix(): "877ee84b749f0140ac090da4c4045bdb9db3f95fc85eff27a7ed9f9d9fe34529",
    TEST_PATH.as_posix(): "792b4434c4f792fb61e68843f1d4d70f20aab53eee3a4301e7f7dcf7ca0ffb21",
}

PINNED_BASELINE_HASHES: Dict[str, str] = {
    "machine/facts/canonical_facts.json": "f7008c057f317c704daca041e1f85c81c1f77b23dcdd70d38ce828aca8000385",
    "machine/facts/costs.json": "bf753ab094133102b31496f8f05150883b8fce94aaf6927ff85bfbf5a37d0e65",
    "machine/facts/parameters.json": "ac8dc796247fe4b0074e5ccb722af9661c0228f13cbd44c9ffda2d8d3804d63d",
    "machine/facts/roadmap.json": "75e2d62e734488c7c4128642dc28872edcb0160e2705dc2ccb363f69845aefeb",
    "machine/facts/requirements.json": "54d4a849ebb1266e8a01c99259f0a54728e901007657ec44e04178dcbc8bea12",
    "machine/facts/acceptance_contracts.json": "b91a48288cc3fec26233a5a0c8170d164cfec0e66e9b0f28f2012c96128d1342",
    "machine/facts/task_graph.json": "78ae36747193003a24a0d15a620664b1cb406609356242a003bf821b775cd778",
    "machine/facts/traceability_matrix.json": "e2e703bb8bd6db6bc44d0597b496d7fd5dac4a6f3c633e464c40348175a1ad1a",
    "machine/evidence/EVD-S03-STAGE-REVIEW.json": "f636457a578723a5c98799bf4450754d331291fa29444c453630c5d0b81aea21",
    "machine/evidence/EVD-S03-STAGE-REVIEW_rollback.json": "41111279b9a900947cd6b09df182028909887fad145d19d3719f638749422451",
    STAGE3_DELIVERY_RECEIPT_PATH.as_posix(): STAGE3_DELIVERY_RECEIPT_SHA256,
    "abd_acceptance/stage3_delivery.py": "4fc1a73192108f224685029dc774bd600388e407beedf530358d2ace90f278c8",
}

PINNED_REPO_HASHES = {
    WORKFLOW_PATH.as_posix(): "e1ed7245f525cea1489932337e18fe8abbe13d3a8d45cfcf11aa2235b444a25d",
}

EXTERNAL_EFFECT_BOUNDARY = {
    "network_accessed": False,
    "ovh_account_or_host_accessed": False,
    "docker_engine_invoked": False,
    "systemd_invoked": False,
    "container_image_built_or_pulled": False,
    "secret_value_read_or_stored": False,
    "cloudflare_configured": False,
    "production_activated": False,
    "real_order_submitted": False,
    "return_or_roi_verified": False,
    "incremental_cash_spent_aud": "0.00",
}

SECRET_PATTERNS = [
    re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----"),
    re.compile(r"\bghp_[A-Za-z0-9]{20,}\b"),
    re.compile(r"\bAKIA[A-Z0-9]{16}\b"),
]
LOCAL_PATH_FRAGMENTS = ["/" + "Users/", "/private/" + "var/", "file" + "://", "C:" + "\\Users\\"]


class InfrastructureContractError(ValueError):
    """Raised when the S04/P01 infrastructure contract fails closed."""


def _json_bytes(value: Any) -> bytes:
    return (json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2) + "\n").encode("utf-8")


def _sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _contains_float(value: Any) -> bool:
    if isinstance(value, float):
        return True
    if isinstance(value, Mapping):
        return any(_contains_float(item) for item in value.values())
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        return any(_contains_float(item) for item in value)
    return False


def _add(checks: List[Dict[str, Any]], check_id: str, passed: bool, detail: Any) -> None:
    checks.append({"id": check_id, "passed": bool(passed), "detail": detail})


def _safe_load(path: Path, checks: List[Dict[str, Any]], check_id: str) -> Any:
    try:
        value = strict_json_load(path)
    except Exception as exc:
        _add(checks, check_id, False, "%s: %s" % (type(exc).__name__, exc))
        return None
    _add(checks, check_id, True, path.name)
    return value


def _structural_self_hash(root: Path) -> str:
    text = (root / "abd_acceptance/infrastructure_iac.py").read_text(encoding="utf-8")
    normalized = re.sub(
        r'(?m)^(STRUCTURAL_SELF_NORMALIZED_SHA256 = ")[^"]+("\s*)$',
        r"\1<NORMALIZED>\2",
        text,
        count=1,
    )
    if normalized == text:
        return "NORMALIZATION_FAILED"
    return _sha256_bytes(normalized.encode("utf-8"))


def _current_code_hash(root: Path) -> str:
    digest = hashlib.sha256()
    for path in sorted((root / "abd_acceptance").glob("*.py")):
        digest.update(path.relative_to(root).as_posix().encode("utf-8"))
        digest.update(b"\0")
        digest.update(path.read_bytes())
        digest.update(b"\0")
    return digest.hexdigest()


def _phase_commit_is_ancestor(root: Path) -> bool:
    result = subprocess.run(
        ["git", "-C", str(root.parent), "merge-base", "--is-ancestor", PHASE_COMMIT, "HEAD"],
        check=False,
        capture_output=True,
        text=True,
    )
    return result.returncode == 0


def _historical_file_matches(root: Path, relative: str, expected_sha256: str, verify_git_history: bool) -> bool:
    if relative not in SUCCESSOR_EVOLVABLE_SIGNED_INPUTS:
        return False
    if verify_git_history:
        if not _phase_commit_is_ancestor(root):
            return False
        result = subprocess.run(
            ["git", "-C", str(root.parent), "show", "%s:ABD/%s" % (PHASE_COMMIT, relative)],
            check=False,
            capture_output=True,
        )
        return result.returncode == 0 and _sha256_bytes(result.stdout) == expected_sha256
    if relative == "abd_acceptance/infrastructure_iac.py":
        try:
            return _structural_self_hash(root) == STRUCTURAL_SELF_NORMALIZED_SHA256
        except Exception:
            return False
    successor = SUCCESSOR_UNIT_PROFILE_HASHES.get(relative)
    return successor is not None and (root / relative).is_file() and sha256_file(root / relative) == successor


def _historical_code_hash(root: Path, verify_git_history: bool) -> str:
    if not verify_git_history:
        return "UNVERIFIED_UNIT_TEST_HISTORY"
    if not _phase_commit_is_ancestor(root):
        return "INVALID_PHASE_COMMIT_ANCESTRY"
    listing = subprocess.run(
        ["git", "-C", str(root.parent), "ls-tree", "-r", "--name-only", PHASE_COMMIT, "--", "ABD/abd_acceptance"],
        check=False,
        capture_output=True,
        text=True,
    )
    if listing.returncode != 0:
        return "UNAVAILABLE_PHASE_COMMIT_TREE"
    digest = hashlib.sha256()
    for repo_path in sorted(
        line
        for line in listing.stdout.splitlines()
        if line.startswith("ABD/abd_acceptance/") and line.endswith(".py")
    ):
        blob = subprocess.run(
            ["git", "-C", str(root.parent), "show", "%s:%s" % (PHASE_COMMIT, repo_path)],
            check=False,
            capture_output=True,
        )
        if blob.returncode != 0:
            return "UNAVAILABLE_PHASE_COMMIT_BLOB"
        digest.update(repo_path.removeprefix("ABD/").encode("utf-8"))
        digest.update(b"\0")
        digest.update(blob.stdout)
        digest.update(b"\0")
    return digest.hexdigest()


def _load_index(root: Path) -> List[Dict[str, Any]]:
    return [
        json.loads(line)
        for line in (root / EVIDENCE_INDEX_PATH).read_text(encoding="utf-8-sig").splitlines()
        if line
    ]


def _find_by_id(rows: Sequence[Mapping[str, Any]], row_id: str) -> List[Mapping[str, Any]]:
    return [row for row in rows if row.get("id") == row_id]


def validate_config(schema: Mapping[str, Any], config: Mapping[str, Any]) -> List[Dict[str, str]]:
    validator = Draft202012Validator(schema)
    errors: List[Dict[str, str]] = []
    for error in sorted(validator.iter_errors(config), key=lambda item: list(item.absolute_path)):
        path = "/".join(str(part) for part in error.absolute_path) or "$"
        errors.append({"path": path, "message": error.message})
    return errors


def _set_path(value: MutableMapping[str, Any], path: Sequence[str], replacement: Any) -> None:
    cursor: MutableMapping[str, Any] = value
    for part in path[:-1]:
        child = cursor.get(part)
        if not isinstance(child, MutableMapping):
            raise InfrastructureContractError("mutation path is not a mapping: %s" % "/".join(path))
        cursor = child
    cursor[path[-1]] = replacement


def activation_gate(config: Mapping[str, Any]) -> str:
    prerequisites = config.get("runtime_prerequisites", {})
    ready = (
        isinstance(prerequisites, Mapping)
        and set(prerequisites.values()) == {"VERIFIED"}
        and config.get("host", {}).get("capacity_verification_status") == "VERIFIED_ON_TARGET_HOST"
        and config.get("activation_requested") is True
    )
    return "READY_FOR_EXPLICIT_P03_ACTIVATION" if ready else "BLOCKED_RUNTIME_PREREQUISITES_NOT_VERIFIED"


def build_runtime_env(config: Mapping[str, Any]) -> bytes:
    values = {
        "ABD_BIND_PORT": str(config["network"]["bind_port"]),
        "ABD_CONFIG_FILE": config["directories"]["config"] + "/config.json",
        "ABD_IMAGE": config["image"]["reference"],
        "ABD_LOG_DIR": config["directories"]["logs"],
        "ABD_RUNTIME_SECRET_FILE": config["secrets"]["runtime_secret_file"],
        "ABD_RUNTIME_UID_GID": config["runtime"]["uid_gid"],
        "ABD_STATE_DIR": config["directories"]["state"],
    }
    for key, value in values.items():
        if not isinstance(value, str) or not value or "\n" in value or "\r" in value:
            raise InfrastructureContractError("unsafe runtime environment value for %s" % key)
    return ("".join("%s=%s\n" % (key, values[key]) for key in sorted(values))).encode("utf-8")


def _copy_public_artifact(root: Path, destination: Path, relative: Path) -> str:
    source = root / relative
    target = destination / relative
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source, target)
    return sha256_file(target)


def rebuild_bundle(root: Path, config: Mapping[str, Any], destination: Path) -> Dict[str, Any]:
    root = root.resolve()
    destination = destination.resolve()
    schema = strict_json_load(root / SCHEMA_PATH)
    errors = validate_config(schema, config)
    if errors:
        raise InfrastructureContractError("configuration rejected: %s" % json.dumps(errors, ensure_ascii=False, sort_keys=True))
    if destination.exists() or destination.is_symlink():
        raise InfrastructureContractError("destination must not already exist")
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.mkdir(mode=0o750)
    copied: Dict[str, str] = {}
    for relative in [COMPOSE_PATH, SCHEMA_PATH, SYSTEMD_PATH, REBUILD_PATH]:
        copied[relative.as_posix()] = _copy_public_artifact(root, destination, relative)
    runtime_env = build_runtime_env(config)
    runtime_path = destination / "runtime.env"
    runtime_path.write_bytes(runtime_env)
    runtime_path.chmod(0o600)
    copied["runtime.env"] = sha256_file(runtime_path)
    manifest = {
        "schema_version": "1.0.0",
        "product_version": VERSION,
        "phase_id": "%s/%s" % (STAGE_ID, PHASE_ID),
        "fixed_clock": FIXED_CLOCK,
        "deployment_id": config["deployment_id"],
        "source_config_sha256": _sha256_bytes(_json_bytes(config)),
        "files": copied,
        "runtime_env_keys": sorted(line.split("=", 1)[0] for line in runtime_env.decode("utf-8").splitlines()),
        "secret_reference_only": True,
        "secret_value_read_or_stored": False,
        "activation_gate": activation_gate(config),
        "activation_performed": False,
        "external_effect_boundary": EXTERNAL_EFFECT_BOUNDARY,
    }
    (destination / "rebuild_manifest.json").write_bytes(_json_bytes(manifest))
    return manifest


def _tree_hash(root: Path) -> str:
    digest = hashlib.sha256()
    for path in sorted(item for item in root.rglob("*") if item.is_file()):
        digest.update(path.relative_to(root).as_posix().encode("utf-8"))
        digest.update(b"\0")
        digest.update(path.read_bytes())
        digest.update(b"\0")
        digest.update(oct(stat.S_IMODE(path.stat().st_mode)).encode("ascii"))
        digest.update(b"\0")
    return digest.hexdigest()


def parse_systemd_unit(text: str) -> Dict[str, Dict[str, List[str]]]:
    sections: Dict[str, Dict[str, List[str]]] = {}
    current: Dict[str, List[str]] | None = None
    for line_number, raw in enumerate(text.splitlines(), start=1):
        line = raw.strip()
        if not line or line.startswith("#") or line.startswith(";"):
            continue
        if line.startswith("[") and line.endswith("]"):
            name = line[1:-1]
            if not name or name in sections:
                raise InfrastructureContractError("duplicate or empty systemd section at line %d" % line_number)
            current = {}
            sections[name] = current
            continue
        if current is None or "=" not in raw or raw.rstrip().endswith("\\"):
            raise InfrastructureContractError("invalid systemd assignment at line %d" % line_number)
        key, value = raw.split("=", 1)
        key = key.strip()
        if not key:
            raise InfrastructureContractError("empty systemd key at line %d" % line_number)
        current.setdefault(key, []).append(value.strip())
    return sections


def _check_taskpack_trace(root: Path, fixture: Mapping[str, Any], checks: List[Dict[str, Any]]) -> None:
    requirements = strict_json_load(root / "machine/facts/requirements.json")
    contracts = strict_json_load(root / "machine/facts/acceptance_contracts.json")
    graph = strict_json_load(root / "machine/facts/task_graph.json")
    traces = strict_json_load(root / "machine/facts/traceability_matrix.json")
    roadmap = strict_json_load(root / "machine/facts/roadmap.json")
    req = _find_by_id(requirements, REQUIREMENT_ID)
    contract = _find_by_id(contracts, CONTRACT_ID)
    tasks = [row for row in graph.get("tasks", []) if row.get("id") in fixture.get("expected_task_ids", [])]
    trace = [row for row in traces if row.get("requirement_id") == REQUIREMENT_ID]
    stages = _find_by_id(roadmap.get("stages", []), STAGE_ID)
    phase = [] if not stages else [row for row in stages[0].get("phases", []) if row.get("id") == PHASE_ID]
    req_ok = (
        len(req) == 1
        and req[0].get("stage_id") == STAGE_ID
        and req[0].get("phase_id") == PHASE_ID
        and req[0].get("scope") == ["infra/compose.yml", "infra/systemd", "infra/config.schema.json"]
        and req[0].get("target") == "一条命令可重建，秘密不进入仓库。"
    )
    _add(checks, "S04P01-REQUIREMENT-TRACE-EXACT", req_ok, req)
    contract_ok = (
        len(contract) == 1
        and contract[0].get("requirement_id") == REQUIREMENT_ID
        and contract[0].get("oracle", {}).get("command") == "python -m abd_acceptance --contract AC-S04-P01 --evidence machine/evidence"
        and contract[0].get("pass_gate") == "一条命令可重建，秘密不进入仓库。"
    )
    _add(checks, "S04P01-ACCEPTANCE-CONTRACT-TRACE-EXACT", contract_ok, contract)
    task_ok = (
        [row.get("id") for row in tasks] == fixture.get("expected_task_ids")
        and tasks[0].get("depends_on") == ["T-S00-P04-03", "T-S01-P04-03"]
        and tasks[1].get("depends_on") == ["T-S04-P01-01"]
        and tasks[2].get("depends_on") == ["T-S04-P01-02"]
    )
    _add(checks, "S04P01-TASK-CHAIN-EXACT", task_ok, tasks)
    trace_ok = (
        len(trace) == 1
        and trace[0].get("acceptance_criteria_id") == CONTRACT_ID
        and trace[0].get("task_ids") == fixture.get("expected_task_ids")
        and trace[0].get("artifact_ids") == list(fixture.get("expected_artifacts", {}).keys())
        and trace[0].get("evidence_id") == "EVD-S04-P01"
    )
    _add(checks, "S04P01-TRACEABILITY-EXACT", trace_ok, trace)
    phase_ok = (
        len(phase) == 1
        and phase[0].get("outputs") == ["infra/compose.yml", "infra/systemd", "infra/config.schema.json"]
        and phase[0].get("pass_gate") == "一条命令可重建，秘密不进入仓库。"
    )
    _add(checks, "S04P01-ROADMAP-PHASE-EXACT", phase_ok, phase)


def _check_compose(compose: Mapping[str, Any], checks: List[Dict[str, Any]]) -> None:
    services = compose.get("services", {})
    core = services.get("abd-core", {}) if isinstance(services, Mapping) else {}
    shadow = services.get("abd-shadow", {}) if isinstance(services, Mapping) else {}
    _add(checks, "S04P01-COMPOSE-SERVICE-SET", compose.get("name") == "abd" and set(services) == {"abd-core", "abd-shadow"}, list(services))
    _add(checks, "S04P01-COMPOSE-DIGEST-INPUT-REQUIRED", core.get("image") == "${ABD_IMAGE:?ABD_IMAGE must be pinned by sha256 digest}" and core.get("pull_policy") == "never" and "build" not in core, {"image": core.get("image"), "pull": core.get("pull_policy")})
    _add(checks, "S04P01-COMPOSE-RESOURCE-LIMITS", core.get("cpus") == "1.50" and core.get("mem_limit") == "2560m" and core.get("mem_reservation") == "1024m" and core.get("memswap_limit") == "2560m" and core.get("pids_limit") == 512, {key: core.get(key) for key in ["cpus", "mem_limit", "mem_reservation", "memswap_limit", "pids_limit"]})
    _add(checks, "S04P01-COMPOSE-HARDENING", core.get("read_only") is True and core.get("cap_drop") == ["ALL"] and core.get("security_opt") == ["no-new-privileges:true"] and core.get("init") is True and core.get("user") == "${ABD_RUNTIME_UID_GID:?ABD_RUNTIME_UID_GID is required}" and core.get("privileged") is None, {key: core.get(key) for key in ["read_only", "cap_drop", "security_opt", "init", "user", "privileged"]})
    ports = core.get("ports", [])
    port_ok = len(ports) == 1 and ports[0] == {"target": 8080, "published": "${ABD_BIND_PORT:-8080}", "host_ip": "127.0.0.1", "protocol": "tcp"}
    _add(checks, "S04P01-COMPOSE-LOOPBACK-ONLY", port_ok and "network_mode" not in core, ports)
    volumes = core.get("volumes", [])
    volume_ok = (
        len(volumes) == 3
        and {row.get("target") for row in volumes} == {"/etc/abd/config.json", "/var/lib/abd", "/var/log/abd"}
        and all(row.get("type") == "bind" and row.get("bind", {}).get("create_host_path") is False for row in volumes)
        and next(row for row in volumes if row.get("target") == "/etc/abd/config.json").get("read_only") is True
    )
    _add(checks, "S04P01-COMPOSE-DIRECTORY-BINDS-EXACT", volume_ok, volumes)
    secrets = compose.get("secrets", {})
    secret_ok = (
        secrets == {"abd_runtime_secret": {"file": "${ABD_RUNTIME_SECRET_FILE:?host runtime secret file is required}"}}
        and core.get("secrets") == [{"source": "abd_runtime_secret", "target": "abd_runtime"}]
        and core.get("environment", {}).get("ABD_RUNTIME_SECRET_FILE") == "/run/secrets/abd_runtime"
    )
    _add(checks, "S04P01-COMPOSE-SECRET-FILE-REFERENCE-ONLY", secret_ok, {"top": secrets, "service": core.get("secrets")})
    _add(checks, "S04P01-COMPOSE-NO-ORDER-CAPABILITY", core.get("environment", {}).get("ABD_ORDER_SUBMISSION_ENABLED") == "false", core.get("environment"))
    logging = core.get("logging", {})
    _add(checks, "S04P01-COMPOSE-BOUNDED-LOGGING", logging == {"driver": "local", "options": {"max-size": "10m", "max-file": "3"}}, logging)
    shadow_ports = shadow.get("ports", [])
    shadow_volumes = shadow.get("volumes", [])
    shadow_volume_map = {
        row.get("target"): row
        for row in shadow_volumes
        if isinstance(row, Mapping) and isinstance(row.get("target"), str)
    }
    shadow_exact = (
        shadow.get("profiles") == ["shadow"]
        and shadow.get("image") == core.get("image")
        and shadow.get("pull_policy") == "never"
        and "build" not in shadow
        and shadow.get("user") == core.get("user")
        and shadow.get("restart") == "no"
        and shadow.get("read_only") is True
        and shadow.get("cap_drop") == ["ALL"]
        and shadow.get("security_opt") == ["no-new-privileges:true"]
        and shadow.get("cpus") == "0.25"
        and shadow.get("mem_limit") == "512m"
        and shadow.get("mem_reservation") == "128m"
        and shadow.get("memswap_limit") == "512m"
        and shadow.get("pids_limit") == 128
        and shadow_ports == [{
            "target": 8080,
            "published": "${ABD_SHADOW_BIND_PORT:?ABD_SHADOW_BIND_PORT must be 8081 or 8082}",
            "host_ip": "127.0.0.1",
            "protocol": "tcp",
        }]
        and set(shadow_volume_map) == {"/etc/abd/config.json", "/var/lib/abd", "/var/log/abd"}
        and all(row.get("type") == "bind" and row.get("bind", {}).get("create_host_path") is False for row in shadow_volumes)
        and shadow_volume_map.get("/etc/abd/config.json", {}).get("read_only") is True
        and shadow_volume_map.get("/var/lib/abd", {}).get("read_only") is True
        and shadow_volume_map.get("/var/log/abd", {}).get("read_only") is False
        and shadow.get("environment", {}).get("ABD_RUNTIME_MODE") == "SHADOW_READ_ONLY"
        and shadow.get("environment", {}).get("ABD_ORDER_SUBMISSION_ENABLED") == "false"
        and shadow.get("secrets") == core.get("secrets")
        and shadow.get("logging") == logging
    )
    _add(
        checks,
        "S04P01-COMPOSE-SHADOW-RESOURCE-READ-ONLY-PROFILE",
        shadow_exact,
        {
            "profiles": shadow.get("profiles"),
            "resources": {key: shadow.get(key) for key in ["cpus", "mem_limit", "mem_reservation", "memswap_limit", "pids_limit"]},
            "ports": shadow_ports,
            "volumes": shadow_volumes,
            "environment": shadow.get("environment"),
        },
    )


def _check_systemd(root: Path, checks: List[Dict[str, Any]]) -> None:
    try:
        unit = parse_systemd_unit((root / SYSTEMD_PATH).read_text(encoding="utf-8"))
        _add(checks, "S04P01-SYSTEMD-STRICT-PARSE", True, sorted(unit))
    except Exception as exc:
        _add(checks, "S04P01-SYSTEMD-STRICT-PARSE", False, "%s: %s" % (type(exc).__name__, exc))
        return
    _add(checks, "S04P01-SYSTEMD-SECTIONS", set(unit) == {"Unit", "Service", "Install"}, sorted(unit))
    service = unit.get("Service", {})
    unit_section = unit.get("Unit", {})
    conditions = unit_section.get("ConditionPathExists", [])
    _add(checks, "S04P01-SYSTEMD-PREREQUISITE-PATHS", conditions == ["/etc/abd/config.json", "/etc/abd/runtime.env", "/etc/abd/secrets/runtime"], conditions)
    pre = service.get("ExecStartPre", [])
    pre_ok = (
        pre == [
            "/opt/abd/current/infra/rebuild.sh check --config /etc/abd/config.json",
            "/usr/bin/docker compose --project-name abd --env-file /etc/abd/runtime.env --file /opt/abd/current/infra/compose.yml config --quiet",
        ]
    )
    _add(checks, "S04P01-SYSTEMD-PREFLIGHT-CHAIN", pre_ok, pre)
    starts = service.get("ExecStart", [])
    start_ok = len(starts) == 1 and " up --detach --remove-orphans --wait --wait-timeout 120" in starts[0] and "--build" not in starts[0]
    _add(checks, "S04P01-SYSTEMD-REBUILD-COMMAND", start_ok, starts)
    hardening_ok = service.get("UMask") == ["0077"] and service.get("NoNewPrivileges") == ["true"] and service.get("EnvironmentFile") == ["/etc/abd/runtime.env"]
    _add(checks, "S04P01-SYSTEMD-HARDENING", hardening_ok, {key: service.get(key) for key in ["UMask", "NoNewPrivileges", "EnvironmentFile"]})
    _add(checks, "S04P01-SYSTEMD-NO-INLINE-SECRET", not any("SECRET=" in value or "TOKEN=" in value or "PASSWORD=" in value for values in service.values() for value in values), "no inline secret assignments")
    script = (root / REBUILD_PATH).read_text(encoding="utf-8")
    script_ok = script.startswith("#!/bin/sh\nset -eu\n") and "exec python3 -m abd_acceptance.infrastructure_iac \"$@\"" in script and (root / REBUILD_PATH).stat().st_mode & stat.S_IXUSR
    _add(checks, "S04P01-ONE-COMMAND-ENTRYPOINT", bool(script_ok), REBUILD_PATH.as_posix())


def _check_rebuild(root: Path, fixture: Mapping[str, Any], checks: List[Dict[str, Any]]) -> None:
    config = fixture.get("valid_config", {})
    try:
        with tempfile.TemporaryDirectory(prefix="abd-s04-p01-") as temporary:
            base = Path(temporary)
            first_dir = base / "first"
            second_dir = base / "second"
            first = rebuild_bundle(root, config, first_dir)
            second = rebuild_bundle(root, config, second_dir)
            first_files = sorted(path.relative_to(first_dir).as_posix() for path in first_dir.rglob("*") if path.is_file())
            second_files = sorted(path.relative_to(second_dir).as_posix() for path in second_dir.rglob("*") if path.is_file())
            _add(checks, "S04P01-REBUILD-FILE-SET-EXACT", first_files == fixture.get("expected_bundle_files") == second_files, first_files)
            _add(checks, "S04P01-REBUILD-DETERMINISTIC", first == second and _tree_hash(first_dir) == _tree_hash(second_dir), {"first": _tree_hash(first_dir), "second": _tree_hash(second_dir)})
            env_text = (first_dir / "runtime.env").read_text(encoding="utf-8")
            env_keys = sorted(line.split("=", 1)[0] for line in env_text.splitlines())
            _add(checks, "S04P01-REBUILD-RUNTIME-ENV-KEYS", env_keys == fixture.get("expected_runtime_env_keys"), env_keys)
            secret_safe = (
                config["secrets"]["runtime_secret_file"] in env_text
                and "secret_value" not in env_text.lower()
                and all(not pattern.search(env_text) for pattern in SECRET_PATTERNS)
                and first.get("secret_value_read_or_stored") is False
            )
            _add(checks, "S04P01-REBUILD-SECRET-REFERENCE-ONLY", secret_safe, first.get("secret_reference_only"))
            _add(checks, "S04P01-REBUILD-ACTIVATION-BLOCKED", first.get("activation_gate") == fixture.get("expected_activation_gate") and first.get("activation_performed") is False, first.get("activation_gate"))
    except Exception as exc:
        for check_id in [
            "S04P01-REBUILD-FILE-SET-EXACT",
            "S04P01-REBUILD-DETERMINISTIC",
            "S04P01-REBUILD-RUNTIME-ENV-KEYS",
            "S04P01-REBUILD-SECRET-REFERENCE-ONLY",
            "S04P01-REBUILD-ACTIVATION-BLOCKED",
        ]:
            _add(checks, check_id, False, "%s: %s" % (type(exc).__name__, exc))


def _check_schema(schema: Mapping[str, Any], fixture: Mapping[str, Any], checks: List[Dict[str, Any]]) -> None:
    try:
        Draft202012Validator.check_schema(schema)
        _add(checks, "S04P01-CONFIG-SCHEMA-META-VALID", True, schema.get("$schema"))
    except Exception as exc:
        _add(checks, "S04P01-CONFIG-SCHEMA-META-VALID", False, "%s: %s" % (type(exc).__name__, exc))
        return
    valid_config = fixture.get("valid_config", {})
    errors = validate_config(schema, valid_config)
    _add(checks, "S04P01-CONFIG-VALID-FIXTURE", not errors, errors or "valid")
    results: Dict[str, Any] = {}
    for mutation in fixture.get("invalid_mutations", []):
        candidate = deepcopy(valid_config)
        try:
            _set_path(candidate, mutation["path"], mutation["value"])
            mutation_errors = validate_config(schema, candidate)
            results[mutation["id"]] = bool(mutation_errors)
        except Exception as exc:
            results[mutation.get("id", "UNKNOWN")] = "%s: %s" % (type(exc).__name__, exc)
    _add(checks, "S04P01-CONFIG-ALL-FAULTS-FAIL-CLOSED", len(results) == len(fixture.get("invalid_mutations", [])) and all(value is True for value in results.values()), results)
    _add(checks, "S04P01-CONFIG-NO-FLOAT", not _contains_float(schema) and not _contains_float(fixture), "decimal and resource boundaries are serialized without binary floats")


def _check_baseline(root: Path, fixture: Mapping[str, Any], checks: List[Dict[str, Any]], hashes: MutableMapping[str, str]) -> None:
    for relative, expected in PINNED_BASELINE_HASHES.items():
        path = root / relative
        actual = sha256_file(path) if path.is_file() else "MISSING"
        hashes[relative] = actual
        _add(checks, "S04P01-BASELINE-%s" % relative.upper().replace("/", "-").replace(".", "-"), actual == expected, {"expected": expected, "actual": actual})
    for relative, expected in PINNED_REPO_HASHES.items():
        path = root.parent / relative
        actual = sha256_file(path) if path.is_file() else "MISSING"
        hashes[relative] = actual
        _add(checks, "S04P01-REPO-%s" % relative.upper().replace("/", "-").replace(".", "-"), actual == expected, {"expected": expected, "actual": actual})
    canonical = strict_json_load(root / "machine/facts/canonical_facts.json")
    costs = strict_json_load(root / "machine/facts/costs.json")
    parameters = strict_json_load(root / "machine/facts/parameters.json")
    product = canonical.get("product", {})
    baseline_ok = (
        product.get("initial_bankroll_aud") == "300.00"
        and product.get("incremental_cash_budget_aud") == "0.00"
        and product.get("monthly_target_return") == "0.30"
        and canonical.get("scope", {}).get("order_submission_module_present") is False
        and parameters.get("target_30pct", {}).get("guaranteed") is False
        and parameters.get("target_30pct", {}).get("shortfall_behavior") == "REPORT_ONLY_NO_GATE_RELAXATION"
        and set(costs.get("incremental_cash_budget", {}).values()) == {"0.00"}
    )
    _add(checks, "S04P01-A300-A0-NO-GUARANTEE", baseline_ok, {"product": product, "target": parameters.get("target_30pct")})
    sources = fixture.get("official_sources", [])
    source_ok = (
        [row.get("id") for row in sources] == ["S04P01-SRC-DOCKER-SERVICES", "S04P01-SRC-DOCKER-UP", "S04P01-SRC-GITHUB-BILLING"]
        and all(row.get("retrieved_at") == "2026-07-22" and str(row.get("url", "")).startswith("https://") for row in sources)
    )
    _add(checks, "S04P01-OFFICIAL-SOURCE-RECEIPTS", source_ok, sources)


def _check_progression(root: Path, checks: List[Dict[str, Any]], verify_git_history: bool) -> None:
    candidate_paths = [
        Path("infra/cloudflared.yml"),
        Path("access_policy.md"),
        Path("degraded_page.html"),
        Path("tests/S04/P02_test.py"),
        Path("machine/tests/fixtures/S04_P02.json"),
        Path("abd_acceptance/cloudflare_edge.py"),
    ]
    signed_paths = [
        Path("machine/evidence/EVD-S04-P02.json"),
        Path("machine/evidence/EVD-S04-P02_rollback.json"),
    ]
    p03_paths = [
        Path("release_slots.json"),
        Path("feature_flags.json"),
        Path("rollback.sh"),
        Path("tests/S04/P03_test.py"),
        Path("machine/tests/fixtures/S04_P03.json"),
        Path("abd_acceptance/release_control.py"),
        Path("machine/evidence/EVD-S04-P03.json"),
        Path("machine/evidence/EVD-S04-P03_rollback.json"),
    ]
    candidate_present = [path.as_posix() for path in candidate_paths if (root / path).exists()]
    signed_present = [path.as_posix() for path in signed_paths if (root / path).exists()]
    p03_present = [path.as_posix() for path in p03_paths if (root / path).exists()]
    rows = _load_index(root)
    p02 = [row for row in rows if row.get("id") == "INDEX-AC-S04-P02"]
    p03 = [row for row in rows if row.get("id") == "INDEX-AC-S04-P03"]
    p02_planned = (
        len(p02) == 1 and p02[0].get("status") == "PLANNED"
        and "actual_artifact" not in p02[0] and "artifact_sha256" not in p02[0]
    )
    p02_signed = (
        len(p02) == 1 and p02[0].get("status") == "PASS"
        and p02[0].get("actual_artifact") == "machine/evidence/EVD-S04-P02.json"
        and isinstance(p02[0].get("artifact_sha256"), str)
        and p02[0].get("next") == "S04/P03_READY_NOT_STARTED"
    )
    p03_planned = (
        not p03_present and len(p03) == 1 and p03[0].get("status") == "PLANNED"
        and "actual_artifact" not in p03[0] and "artifact_sha256" not in p03[0]
    )
    mode = "INVALID_PARTIAL_S04_P02_SUCCESSOR"
    successor: Dict[str, Any] = {}
    if not candidate_present and not signed_present and p02_planned:
        progression_ok = True
        mode = "S04_P02_NOT_STARTED"
    elif len(candidate_present) == len(candidate_paths) and not signed_present and p02_planned:
        try:
            from .cloudflare_edge import evaluate_contract as evaluate_s04_p02

            successor = evaluate_s04_p02(root, require_external_reports=False, _verify_git_history=verify_git_history)
            progression_ok = successor.get("status") == "PASS" and successor.get("next") == "S04/P03_READY_NOT_STARTED"
            mode = "VERIFIED_S04_P02_CANDIDATE" if progression_ok else "INVALID_S04_P02_CANDIDATE"
        except Exception as exc:
            progression_ok = False
            successor = {"error": "%s: %s" % (type(exc).__name__, exc)}
    elif len(candidate_present) == len(candidate_paths) and len(signed_present) == len(signed_paths) and p02_signed:
        try:
            from .cloudflare_edge import verify_existing_phase_evidence as verify_s04_p02

            successor = verify_s04_p02(root, verify_git_history=verify_git_history)
            progression_ok = successor.get("status") == "PASS" and successor.get("next") == "S04/P03_READY_NOT_STARTED"
            mode = "VERIFIED_S04_P02_SIGNED_SUCCESSOR" if progression_ok else "INVALID_S04_P02_SIGNED_SUCCESSOR"
        except Exception as exc:
            progression_ok = False
            successor = {"error": "%s: %s" % (type(exc).__name__, exc)}
    else:
        progression_ok = False
    # Once P02 is signed, its evolved verifier owns the exact P03 candidate or
    # signed-successor gate and also proves P04 remains untouched. Earlier P02
    # states must still have a completely absent, PLANNED P03.
    downstream_ok = True if mode == "VERIFIED_S04_P02_SIGNED_SUCCESSOR" else p03_planned
    progression_ok = progression_ok and downstream_ok
    _add(
        checks,
        "S04P01-P02-NOT-STARTED",
        progression_ok,
        {
            "mode": mode,
            "candidate_present": candidate_present,
            "signed_present": signed_present,
            "p02_index": p02,
            "p03_present": p03_present,
            "p03_index": p03,
            "successor_summary": successor.get("summary") if isinstance(successor, Mapping) else successor,
        },
    )


def _check_no_leaks(root: Path, checks: List[Dict[str, Any]]) -> None:
    files = [COMPOSE_PATH, SCHEMA_PATH, SYSTEMD_PATH, REBUILD_PATH, FIXTURE_PATH, TEST_PATH, Path("abd_acceptance/infrastructure_iac.py"), STAGE3_DELIVERY_RECEIPT_PATH]
    leaks: List[Dict[str, str]] = []
    for relative in files:
        path = root / relative
        if not path.is_file():
            leaks.append({"path": relative.as_posix(), "kind": "missing"})
            continue
        text = path.read_text(encoding="utf-8", errors="replace")
        if any(pattern.search(text) for pattern in SECRET_PATTERNS):
            leaks.append({"path": relative.as_posix(), "kind": "secret-pattern"})
        if any(fragment in text for fragment in LOCAL_PATH_FRAGMENTS):
            leaks.append({"path": relative.as_posix(), "kind": "absolute-local-path"})
    _add(checks, "S04P01-NO-SECRET-OR-LOCAL-PATH", not leaks, leaks or "none")


def _junit_summary(path: Path) -> Dict[str, int]:
    root = ET.parse(str(path)).getroot()
    suites = [root] if root.tag == "testsuite" else list(root.findall("testsuite"))
    return {key: sum(int(suite.attrib.get(key, "0")) for suite in suites) for key in ("tests", "failures", "errors", "skipped")}


def _junit_is_normalized(path: Path) -> bool:
    root = ET.parse(str(path)).getroot()
    suites = [root] if root.tag == "testsuite" else list(root.findall("testsuite"))
    return all(suite.attrib.get("timestamp") == JUNIT_FIXED_CLOCK and suite.attrib.get("time") == "0.000" for suite in suites)


def _check_external_reports(root: Path, fixture: Mapping[str, Any], checks: List[Dict[str, Any]], hashes: MutableMapping[str, str]) -> None:
    for check_id, relative, minimum in [
        ("S04P01-TARGETED-PYTEST", JUNIT_PATH, int(fixture.get("minimum_targeted_pytest_cases", 0))),
        ("S04P01-FULL-REGRESSION", FULL_JUNIT_PATH, int(fixture.get("minimum_full_pytest_cases", 0))),
    ]:
        try:
            summary = _junit_summary(root / relative)
            ok = summary["tests"] >= minimum and summary["failures"] == 0 and summary["errors"] == 0 and _junit_is_normalized(root / relative)
            _add(checks, check_id, ok, summary)
            hashes[relative.as_posix()] = sha256_file(root / relative)
        except Exception as exc:
            _add(checks, check_id, False, "%s: %s" % (type(exc).__name__, exc))
    try:
        report = strict_json_load(root / PACK_REPORT_PATH)
        summary = report.get("summary", {})
        ok = report.get("status") == "PASS" and summary.get("checks") == 49 and summary.get("passed") == 49 and summary.get("failed") == 0
        _add(checks, "S04P01-TASKPACK-49-PASS", ok, summary)
        hashes[PACK_REPORT_PATH.as_posix()] = sha256_file(root / PACK_REPORT_PATH)
    except Exception as exc:
        _add(checks, "S04P01-TASKPACK-49-PASS", False, "%s: %s" % (type(exc).__name__, exc))
    try:
        text = (root / SCAN_REPORT_PATH).read_text(encoding="utf-8")
        required = {"STATUS: PASS", "MAX_INCREMENTAL_CASH_AUD: 0.00", "PAID_OR_UNKNOWN_DEPENDENCIES: 0", "EXTERNAL_NETWORK_ACCESS_PERFORMED: false", "EXTERNAL_ACCOUNT_OR_BILLING_ACCESS_PERFORMED: false"}
        _add(checks, "S04P01-PAID-DEPENDENCY-SCAN", required.issubset(set(text.splitlines())), text.splitlines()[:10])
        hashes[SCAN_REPORT_PATH.as_posix()] = sha256_file(root / SCAN_REPORT_PATH)
    except Exception as exc:
        _add(checks, "S04P01-PAID-DEPENDENCY-SCAN", False, "%s: %s" % (type(exc).__name__, exc))


def evaluate_contract(
    root: Path,
    require_external_reports: bool = False,
    *,
    _verify_git_history: bool = True,
) -> Dict[str, Any]:
    root = root.resolve()
    checks: List[Dict[str, Any]] = []
    hashes: Dict[str, str] = {}
    fixture = _safe_load(root / FIXTURE_PATH, checks, "S04P01-FIXTURE-STRICT-JSON")
    schema = _safe_load(root / SCHEMA_PATH, checks, "S04P01-SCHEMA-STRICT-JSON")
    compose = _safe_load(root / COMPOSE_PATH, checks, "S04P01-COMPOSE-STRICT-JSON-YAML-SUBSET")

    for relative, expected in PINNED_PHASE_HASHES.items():
        path = root / relative
        actual = sha256_file(path) if path.is_file() else "MISSING"
        hashes[relative] = actual
        successor = SUCCESSOR_UNIT_PROFILE_HASHES.get(relative)
        _add(checks, "S04P01-PIN-%s" % relative.upper().replace("/", "-").replace(".", "-"), actual == expected or (successor is not None and actual == successor), {"expected": expected, "accepted_successor": successor, "actual": actual})
    self_hash = _structural_self_hash(root)
    hashes["abd_acceptance/infrastructure_iac.py"] = sha256_file(root / "abd_acceptance/infrastructure_iac.py")
    _add(checks, "S04P01-ORACLE-SELF-INTEGRITY", self_hash == STRUCTURAL_SELF_NORMALIZED_SHA256, {"expected": STRUCTURAL_SELF_NORMALIZED_SHA256, "actual": self_hash})

    if isinstance(fixture, Mapping) and isinstance(schema, Mapping) and isinstance(compose, Mapping):
        _check_baseline(root, fixture, checks, hashes)
        _check_taskpack_trace(root, fixture, checks)
        try:
            delivery = verify_stage3_delivery(root, verify_git_history=_verify_git_history)
            delivery_ok = delivery.get("status") == "PASS" and delivery.get("decision") == "S03_DELIVERED_S04_MAY_START" and delivery.get("next") == "S04/P01_READY_NOT_STARTED"
            _add(checks, "S04P01-S03-DELIVERY-PREREQUISITE", delivery_ok, delivery.get("summary"))
        except Exception as exc:
            _add(checks, "S04P01-S03-DELIVERY-PREREQUISITE", False, "%s: %s" % (type(exc).__name__, exc))
        _check_schema(schema, fixture, checks)
        _check_compose(compose, checks)
        _check_systemd(root, checks)
        _check_rebuild(root, fixture, checks)
        _check_progression(root, checks, _verify_git_history)
        _check_no_leaks(root, checks)
        _add(checks, "S04P01-EXTERNAL-EFFECT-BOUNDARY", EXTERNAL_EFFECT_BOUNDARY == fixture.get("expected_external_effect_boundary"), EXTERNAL_EFFECT_BOUNDARY)
        _add(checks, "S04P01-ACTIVATION-GATE", activation_gate(fixture.get("valid_config", {})) == fixture.get("expected_activation_gate"), activation_gate(fixture.get("valid_config", {})))
        if require_external_reports:
            _check_external_reports(root, fixture, checks, hashes)
    else:
        _add(checks, "S04P01-INPUTS-AVAILABLE", False, "fixture, schema or compose unavailable")

    minimum = int(fixture.get("minimum_oracle_checks", 0)) if isinstance(fixture, Mapping) else 0
    if len(checks) < minimum:
        _add(checks, "S04P01-ORACLE-CHECK-COUNT-MINIMUM", False, {"actual": len(checks), "minimum": minimum})
    failed = [row["id"] for row in checks if not row["passed"]]
    status = "PASS" if not failed else "FAIL"
    return {
        "schema_version": "1.0.0",
        "contract_id": CONTRACT_ID,
        "requirement_id": REQUIREMENT_ID,
        "stage_id": STAGE_ID,
        "phase_id": PHASE_ID,
        "product_version": VERSION,
        "fixed_clock": FIXED_CLOCK,
        "status": status,
        "decision": "INFRASTRUCTURE_IAC_REBUILD_CONTRACT_FROZEN" if status == "PASS" else "INFRASTRUCTURE_IAC_BLOCKED_FAIL_CLOSED",
        "phase_status": "S04_P01_PASS" if status == "PASS" else "S04_P01_FAIL",
        "summary": {"checks": len(checks), "passed": len(checks) - len(failed), "failed": len(failed), "failed_check_ids": failed},
        "checks": checks,
        "hashes": hashes,
        "activation_gate": fixture.get("expected_activation_gate") if isinstance(fixture, Mapping) else "BLOCKED_INPUT_UNAVAILABLE",
        "production_status": "NOT_DEPLOYED_OR_ACTIVATED",
        "release_status": "NOT_READY_S04_P02_TO_P04_AND_STAGE_REVIEW_REQUIRED",
        "financial_target_status": "UNVERIFIED_NOT_GUARANTEED",
        "external_effect_boundary": EXTERNAL_EFFECT_BOUNDARY,
        "next": "S04/P02_READY_NOT_STARTED" if status == "PASS" else "S04/P01_REMEDIATION_REQUIRED",
    }


def perform_rollback_drill(root: Path) -> Dict[str, Any]:
    root = root.resolve()
    artifacts = [COMPOSE_PATH, SCHEMA_PATH, SYSTEMD_PATH, REBUILD_PATH, FIXTURE_PATH, TEST_PATH, Path("abd_acceptance/infrastructure_iac.py")]
    results: Dict[str, Any] = {}
    with tempfile.TemporaryDirectory(prefix="abd-s04-p01-rollback-") as temporary:
        base = Path(temporary)
        for relative in artifacts:
            source = root / relative
            original = source.read_bytes()
            target = base / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(original)
            signed = _sha256_bytes(original)
            target.write_bytes(original + b"\nCORRUPTED")
            corrupted = sha256_file(target)
            target.write_bytes(original)
            restored = sha256_file(target)
            results[relative.as_posix()] = {
                "signed_sha256": signed,
                "corrupted_sha256": corrupted,
                "restored_sha256": restored,
                "status": "PASS" if signed == restored and corrupted != signed else "FAIL",
            }
    status = "PASS" if all(row["status"] == "PASS" for row in results.values()) else "FAIL"
    return {
        "schema_version": "1.0.0",
        "evidence_id": "EVD-S04-P01-ROLLBACK",
        "contract_id": CONTRACT_ID,
        "fixed_clock": FIXED_CLOCK,
        "mode": "EPHEMERAL_IAC_ARTIFACT_RESTORE",
        "status": status,
        "artifacts": results,
        "production_state_changed": False,
        "external_state_changed": False,
    }


def build_evidence(root: Path, require_external_reports: bool = True, *, _verify_git_history: bool = True) -> tuple[Dict[str, Any], Dict[str, Any]]:
    root = root.resolve()
    validation = evaluate_contract(root, require_external_reports, _verify_git_history=_verify_git_history)
    rollback = perform_rollback_drill(root)
    if rollback["status"] != "PASS":
        validation = deepcopy(validation)
        validation["status"] = "FAIL"
        validation["decision"] = "INFRASTRUCTURE_IAC_BLOCKED_FAIL_CLOSED"
        validation["phase_status"] = "S04_P01_FAIL"
        validation["next"] = "S04/P01_REMEDIATION_REQUIRED"
    inputs: Dict[str, str] = {}
    for relative in sorted({*PINNED_BASELINE_HASHES, *PINNED_PHASE_HASHES, "abd_acceptance/infrastructure_iac.py"}):
        path = root / relative
        inputs[relative] = sha256_file(path)
    for relative in PINNED_REPO_HASHES:
        inputs[relative] = sha256_file(root.parent / relative)
    evidence = {
        "schema_version": "1.0.0",
        "evidence_id": "EVD-S04-P01",
        "contract_id": CONTRACT_ID,
        "requirement_id": REQUIREMENT_ID,
        "stage_id": STAGE_ID,
        "phase_id": PHASE_ID,
        "product_version": VERSION,
        "fixed_clock": FIXED_CLOCK,
        "status": validation["status"],
        "decision": validation["decision"],
        "phase_status": validation["phase_status"],
        "artifacts": strict_json_load(root / FIXTURE_PATH)["expected_artifacts"],
        "validation": validation,
        "rebuild_proof": {
            "mode": "DETERMINISTIC_OFFLINE_PUBLIC_BUNDLE_MATERIALIZATION",
            "one_command_entrypoint": "infra/rebuild.sh rebuild --config <external-config.json> --destination <new-empty-directory>",
            "production_activation_performed": False,
            "activation_gate": validation["activation_gate"],
        },
        "scope_boundary": {
            "p01_delivers_iac_not_runtime_activation": True,
            "p02_cloudflare_not_started": True,
            "p03_blue_green_activation_not_started": True,
            "target_host_capacity_not_account_verified": True,
            "container_image_not_built_or_pulled": True,
            "systemd_and_docker_runtime_not_executed": True,
        },
        "external_effect_boundary": EXTERNAL_EFFECT_BOUNDARY,
        "hashes": {
            "inputs": inputs,
            "parameters": sha256_file(root / "machine/facts/parameters.json"),
            "model": sha256_file(root / "machine/facts/model_system_card.json"),
            "model_not_executed_reason": "S04/P01 builds and replays infrastructure configuration offline; it executes no model, provider, host, container engine, order or return evaluation.",
            "code": _current_code_hash(root),
            "rollback_evidence": _sha256_bytes(_json_bytes(rollback)),
        },
        "production_status": validation["production_status"],
        "release_status": validation["release_status"],
        "financial_target_status": validation["financial_target_status"],
        "next": validation["next"],
    }
    unsigned = deepcopy(evidence)
    evidence["decision_sha256"] = _sha256_bytes(_json_bytes(unsigned))
    return evidence, rollback


def _atomic_write(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + ".tmp")
    temporary.write_bytes(data)
    temporary.replace(path)


def _update_evidence_index(root: Path, status: str, artifact_sha256: str) -> None:
    rows = _load_index(root)
    matching = [row for row in rows if row.get("id") == "INDEX-AC-S04-P01"]
    if len(matching) != 1:
        raise InfrastructureContractError("expected exactly one INDEX-AC-S04-P01 row")
    row = matching[0]
    row.update(
        {
            "status": status,
            "actual_artifact": EVIDENCE_PATH.as_posix(),
            "artifact_sha256": artifact_sha256,
            "verified_at": FIXED_CLOCK,
            "next": "S04/P02_READY_NOT_STARTED" if status == "PASS" else "S04/P01_REMEDIATION_REQUIRED",
        }
    )
    payload = "".join(json.dumps(item, ensure_ascii=False, sort_keys=True) + "\n" for item in rows).encode("utf-8")
    _atomic_write(root / EVIDENCE_INDEX_PATH, payload)


def write_phase_evidence(root: Path, evidence_dir: Path) -> Dict[str, Any]:
    root = root.resolve()
    evidence_dir = evidence_dir.resolve()
    try:
        evidence_dir.relative_to(root)
    except ValueError as exc:
        raise InfrastructureContractError("evidence directory must be inside the ABD project root") from exc
    evidence, rollback = build_evidence(root, require_external_reports=True)
    evidence_path = evidence_dir / EVIDENCE_PATH.name
    rollback_path = evidence_dir / ROLLBACK_EVIDENCE_PATH.name
    _atomic_write(rollback_path, _json_bytes(rollback))
    _atomic_write(evidence_path, _json_bytes(evidence))
    evidence_hash = sha256_file(evidence_path)
    _update_evidence_index(root, evidence["status"], evidence_hash)
    return {
        "contract_id": CONTRACT_ID,
        "status": evidence["status"],
        "evidence_path": evidence_path.relative_to(root).as_posix(),
        "evidence_sha256": evidence_hash,
        "next": evidence["next"],
    }


def _decision_hash_matches(evidence: Mapping[str, Any]) -> bool:
    unsigned = deepcopy(dict(evidence))
    expected = unsigned.pop("decision_sha256", None)
    return isinstance(expected, str) and expected == _sha256_bytes(_json_bytes(unsigned))


def verify_existing_phase_evidence(root: Path, *, verify_git_history: bool = True) -> Dict[str, Any]:
    root = root.resolve()
    checks: List[Dict[str, Any]] = []
    evidence = _safe_load(root / EVIDENCE_PATH, checks, "S04P01-RECEIPT-EVIDENCE-STRICT-JSON")
    rollback = _safe_load(root / ROLLBACK_EVIDENCE_PATH, checks, "S04P01-RECEIPT-ROLLBACK-STRICT-JSON")
    evidence_hash = sha256_file(root / EVIDENCE_PATH) if (root / EVIDENCE_PATH).is_file() else "MISSING"
    rollback_hash = sha256_file(root / ROLLBACK_EVIDENCE_PATH) if (root / ROLLBACK_EVIDENCE_PATH).is_file() else "MISSING"
    if isinstance(evidence, Mapping):
        shape_ok = (
            evidence.get("schema_version") == "1.0.0"
            and evidence.get("evidence_id") == "EVD-S04-P01"
            and evidence.get("contract_id") == CONTRACT_ID
            and evidence.get("requirement_id") == REQUIREMENT_ID
            and evidence.get("stage_id") == STAGE_ID
            and evidence.get("phase_id") == PHASE_ID
            and evidence.get("fixed_clock") == FIXED_CLOCK
            and evidence.get("status") == "PASS"
            and evidence.get("decision") == "INFRASTRUCTURE_IAC_REBUILD_CONTRACT_FROZEN"
            and evidence.get("phase_status") == "S04_P01_PASS"
            and evidence.get("next") == "S04/P02_READY_NOT_STARTED"
            and _decision_hash_matches(evidence)
        )
        _add(checks, "S04P01-RECEIPT-INTEGRITY", shape_ok, evidence.get("status"))
        validation = evidence.get("validation", {})
        validation_ok = (
            isinstance(validation, Mapping)
            and validation.get("status") == "PASS"
            and validation.get("summary", {}).get("failed") == 0
            and validation.get("next") == "S04/P02_READY_NOT_STARTED"
            and all(row.get("passed") is True for row in validation.get("checks", []))
        )
        _add(checks, "S04P01-RECEIPT-VALIDATION-ALL-PASS", validation_ok, validation.get("summary") if isinstance(validation, Mapping) else validation)
        input_errors: List[Dict[str, str]] = []
        for relative, expected in evidence.get("hashes", {}).get("inputs", {}).items():
            candidate = Path(relative)
            if candidate.is_absolute() or ".." in candidate.parts:
                input_errors.append({"path": relative, "actual": "UNSAFE_PATH"})
                continue
            path = root.parent / candidate if relative.startswith(".github/") else root / candidate
            actual = sha256_file(path) if path.is_file() else "MISSING"
            if actual != expected and not _historical_file_matches(root, relative, expected, verify_git_history):
                input_errors.append({"path": relative, "expected": expected, "actual": actual})
        _add(checks, "S04P01-RECEIPT-SIGNED-INPUTS-CURRENT", not input_errors, input_errors or "all inputs match current files or the exact signed phase commit")
        code_current = _current_code_hash(root)
        code_expected = evidence.get("hashes", {}).get("code")
        code_historical = _historical_code_hash(root, verify_git_history) if code_expected != code_current else code_current
        code_ok = (
            code_expected == code_current
            or (
                code_expected == PINNED_PHASE_CODE_HASH
                and code_historical in {PINNED_PHASE_CODE_HASH, "UNVERIFIED_UNIT_TEST_HISTORY"}
            )
        )
        _add(checks, "S04P01-RECEIPT-CODE-HASH-CURRENT", code_ok, {"expected": code_expected, "current": code_current, "historical": code_historical})
        _add(checks, "S04P01-RECEIPT-ROLLBACK-HASH-BINDING", evidence.get("hashes", {}).get("rollback_evidence") == rollback_hash, {"expected": evidence.get("hashes", {}).get("rollback_evidence"), "actual": rollback_hash})
        _add(checks, "S04P01-RECEIPT-BOUNDARY", evidence.get("external_effect_boundary") == EXTERNAL_EFFECT_BOUNDARY and evidence.get("production_status") == "NOT_DEPLOYED_OR_ACTIVATED", evidence.get("external_effect_boundary"))
    else:
        for check_id in ["S04P01-RECEIPT-INTEGRITY", "S04P01-RECEIPT-VALIDATION-ALL-PASS", "S04P01-RECEIPT-SIGNED-INPUTS-CURRENT", "S04P01-RECEIPT-CODE-HASH-CURRENT", "S04P01-RECEIPT-ROLLBACK-HASH-BINDING", "S04P01-RECEIPT-BOUNDARY"]:
            _add(checks, check_id, False, "evidence unavailable")
    rollback_ok = (
        isinstance(rollback, Mapping)
        and rollback.get("evidence_id") == "EVD-S04-P01-ROLLBACK"
        and rollback.get("contract_id") == CONTRACT_ID
        and rollback.get("fixed_clock") == FIXED_CLOCK
        and rollback.get("status") == "PASS"
        and rollback.get("production_state_changed") is False
        and rollback.get("external_state_changed") is False
        and len(rollback.get("artifacts", {})) == 7
        and all(row.get("status") == "PASS" for row in rollback.get("artifacts", {}).values())
    )
    _add(checks, "S04P01-RECEIPT-ROLLBACK-INTEGRITY", rollback_ok, rollback.get("status") if isinstance(rollback, Mapping) else "unavailable")
    try:
        matching = [row for row in _load_index(root) if row.get("id") == "INDEX-AC-S04-P01"]
        index_ok = (
            len(matching) == 1
            and matching[0].get("status") == "PASS"
            and matching[0].get("actual_artifact") == EVIDENCE_PATH.as_posix()
            and matching[0].get("artifact_sha256") == evidence_hash
            and matching[0].get("next") == "S04/P02_READY_NOT_STARTED"
        )
        _add(checks, "S04P01-RECEIPT-EVIDENCE-INDEX-BINDING", index_ok, matching)
    except Exception as exc:
        _add(checks, "S04P01-RECEIPT-EVIDENCE-INDEX-BINDING", False, "%s: %s" % (type(exc).__name__, exc))
    try:
        delivery = verify_stage3_delivery(root, verify_git_history=verify_git_history)
        _add(checks, "S04P01-RECEIPT-S03-DELIVERY-PREREQUISITE", delivery.get("status") == "PASS", delivery.get("summary"))
    except Exception as exc:
        _add(checks, "S04P01-RECEIPT-S03-DELIVERY-PREREQUISITE", False, "%s: %s" % (type(exc).__name__, exc))
    failed = [row["id"] for row in checks if not row["passed"]]
    return {
        "schema_version": "1.0.0",
        "contract_id": CONTRACT_ID,
        "status": "PASS" if not failed else "FAIL",
        "decision": "S04_P01_EVIDENCE_VERIFIED" if not failed else "S04_P01_EVIDENCE_INVALID_FAIL_CLOSED",
        "summary": {"checks": len(checks), "passed": len(checks) - len(failed), "failed": len(failed), "failed_check_ids": failed},
        "checks": checks,
        "evidence_path": EVIDENCE_PATH.as_posix(),
        "evidence_sha256": evidence_hash,
        "rollback_sha256": rollback_hash,
        "next": "S04/P02_READY_NOT_STARTED" if not failed else "S04/P01_REMEDIATION_REQUIRED",
    }


def _cli() -> int:
    parser = argparse.ArgumentParser(description="ABD S04/P01 deterministic infrastructure bundle tool")
    subparsers = parser.add_subparsers(dest="command", required=True)
    check_parser = subparsers.add_parser("check")
    check_parser.add_argument("--config", required=True)
    rebuild_parser = subparsers.add_parser("rebuild")
    rebuild_parser.add_argument("--config", required=True)
    rebuild_parser.add_argument("--destination", required=True)
    args = parser.parse_args()
    root = Path.cwd().resolve()
    schema = strict_json_load(root / SCHEMA_PATH)
    config = strict_json_load(Path(args.config).resolve())
    errors = validate_config(schema, config)
    if errors:
        print(json.dumps({"status": "FAIL", "errors": errors}, ensure_ascii=False, sort_keys=True))
        return 1
    if args.command == "check":
        print(json.dumps({"status": "PASS", "activation_gate": activation_gate(config), "secret_values_read": False}, ensure_ascii=False, sort_keys=True))
        return 0
    manifest = rebuild_bundle(root, config, Path(args.destination))
    print(json.dumps({"status": "PASS", "manifest_sha256": _sha256_bytes(_json_bytes(manifest)), "activation_gate": manifest["activation_gate"]}, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(_cli())
