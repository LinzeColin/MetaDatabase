#!/usr/bin/env python3
from __future__ import annotations
import argparse, ast, hashlib, io, json, re, sqlite3, subprocess, sys, tokenize, tomllib
from html.parser import HTMLParser
from pathlib import Path, PurePosixPath

GARBAGE_NAMES = {".git", ".pytest_cache", "__pycache__", "build", "dist", ".venv", "venv", "node_modules", ".mypy_cache", ".ruff_cache"}
FORBIDDEN_SUFFIXES = (".pyc", ".pyo", ".zip")
SECRET_PATTERNS = (
    re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----"),
    re.compile(r"(?i)(?:api[_-]?key|token|password|secret)\s*[:=]\s*[\"'][A-Za-z0-9_\-]{20,}[\"']"),
)
UNFINISHED = re.compile(r"\b(?:TODO|TBD|FIXME)\b")
PLACEHOLDER = re.compile(r"(?:TARGET_ENVIRONMENT_BINDING_REQUIRED|按任务包内冻结脚本|example\.(?:com|org|net))", re.I)
MANIFEST_EXCLUDED = {"MANIFEST.json", "SUBJECT_LOCK.json", "CANONICAL_STATE.json", "evidence/skill_router/pass_c.json"}
MANIFEST_EXCLUDED_PREFIXES = ("evidence/formal_review/", "evidence/owner_gate/")
EMBEDDED_SOURCE_ROOTS = ("Stock_Skill",)
ALLOWED_ROOT_FILES = {
    "00_READ_FIRST.md", "CANONICAL_STATE.json", "CODEX_LAST_MILE_PROMPT.txt",
    "MEMORY_RECONCILIATION.md", "PURSUING_GOAL.txt", "README.md", "ROADMAP.md",
    "SUBJECT_LOCK.json", "MANIFEST.json", "events.yaml", "openapi.yaml", "pyproject.toml",
}


def unsafe_path_reason(rel: str) -> str | None:
    """Reject archive/package paths that can be interpreted as command options or controls."""
    if "\\" in rel:
        return "BACKSLASH"
    if any(ord(char) < 32 or ord(char) == 127 for char in rel):
        return "CONTROL_CHARACTER"
    parts = PurePosixPath(rel).parts
    if any(part.startswith("-") for part in parts):
        return "LEADING_DASH_COMPONENT"
    if any(part != part.strip() for part in parts):
        return "SURROUNDING_WHITESPACE"
    return None


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def is_garbage(path: Path) -> bool:
    return any(part in GARBAGE_NAMES or part.endswith((".egg-info", ".dist-info")) for part in path.parts)


def is_embedded_source(rel: str) -> bool:
    return any(rel == root or rel.startswith(root + "/") for root in EMBEDDED_SOURCE_ROOTS)


def validate_embedded_stock_skill(root: Path, findings: list[str]) -> None:
    """Validate the co-located source without treating it as app-package payload.

    Stock Skill archives intentionally retain ZIPs and native YAML, which belong to
    their own integrity contract rather than the Signal Lattice application bundle.
    In a repository checkout this helper requires the stock registry and public
    safety validators to pass. A distributable app-only task pack omits the source
    tree entirely, so absence is allowed after packaging.
    """
    stock_root = root / "Stock_Skill"
    if not stock_root.exists() and not stock_root.is_symlink():
        return
    if stock_root.is_symlink() or not stock_root.is_dir():
        findings.append("EMBEDDED_STOCK_SKILL_ROOT_INVALID")
        return
    repository_root = root.parent
    if not (repository_root / "AGENTS.md").is_file() or not (repository_root / "README.md").is_file():
        findings.append("EMBEDDED_STOCK_SKILL_REPOSITORY_SURFACES_MISSING")
        return
    validators = (
        ("registry", [sys.executable, "-B", str(stock_root / "scripts/validate_registry.py")]),
        ("public_safety", [sys.executable, "-B", str(stock_root / "scripts/validate_public_safety.py"), "--repo-root", str(repository_root)]),
    )
    for name, command in validators:
        completed = subprocess.run(command, cwd=repository_root, capture_output=True, text=True, timeout=300)
        if completed.returncode != 0:
            findings.append("EMBEDDED_STOCK_SKILL_" + name.upper() + "_FAILED")


def unfinished_scan_text(path: Path, text: str) -> str:
    if path.suffix != ".py":
        return text
    # Preserve code and comments while removing Python string literals. This avoids
    # the scanner matching its own regex examples without hiding real comment debt.
    try:
        tokens = tokenize.generate_tokens(io.StringIO(text).readline)
        kept = []
        for token in tokens:
            if token.type == tokenize.STRING:
                kept.append("\n" * token.string.count("\n"))
            else:
                kept.append(token.string)
        return "".join(kept)
    except (tokenize.TokenError, IndentationError):
        return text


def validate_dag_and_trace(root: Path, findings: list[str]) -> None:
    try:
        requirements = json.loads((root / "machine/facts/requirements.json").read_text())["requirements"]
        requirement_ids = {row["id"] for row in requirements}
        dag = json.loads((root / "machine/facts/task_dag.json").read_text())
        tasks = {task["id"]: task for task in dag["tasks"]}
        if len(tasks) != len(dag["tasks"]):
            findings.append("DUPLICATE_TASK_ID")
        covered: set[str] = set()
        for task in tasks.values():
            if "depends_on" not in task or not isinstance(task["depends_on"], list):
                findings.append("INVALID_DEPENDS_ON:" + task.get("id", "UNKNOWN"))
                continue
            covered.update(task.get("requirements", []))
            for dependency in task["depends_on"]:
                if dependency not in tasks:
                    findings.append("MISSING_DEP:" + task["id"] + ":" + dependency)
            if PLACEHOLDER.search(str(task.get("test_command", ""))):
                findings.append("TASK_COMMAND_PLACEHOLDER:" + task["id"])
        for missing in sorted(requirement_ids - covered):
            findings.append("REQUIREMENT_WITHOUT_TASK:" + missing)
        temporary: set[str] = set()
        done: set[str] = set()
        def visit(task_id: str) -> None:
            if task_id in temporary:
                raise ValueError("cycle")
            if task_id in done:
                return
            temporary.add(task_id)
            for dependency in tasks[task_id]["depends_on"]:
                visit(dependency)
            temporary.remove(task_id)
            done.add(task_id)
        for task_id in tasks:
            visit(task_id)
        trace = json.loads((root / "machine/facts/traceability.json").read_text())
        rows = trace["rows"]
        if len(rows) != len(requirement_ids):
            findings.append("TRACEABILITY_ROW_COUNT_MISMATCH")
        row_ids = {row.get("requirement_id") for row in rows}
        if row_ids != requirement_ids:
            findings.append("TRACEABILITY_REQUIREMENT_SET_MISMATCH")
        for row in rows:
            if row.get("complete") is not True:
                findings.append("TRACEABILITY_INCOMPLETE:" + str(row.get("requirement_id")))
            if not row.get("task_ids") or not row.get("tests") or not row.get("oracle") or not row.get("evidence") or not row.get("artifacts"):
                findings.append("TRACEABILITY_EMPTY_FIELD:" + str(row.get("requirement_id")))
    except Exception as exc:
        findings.append("DAG_TRACE:" + type(exc).__name__)


def _canonical_without_receipt(data: dict) -> bytes:
    body = dict(data)
    body.pop("receipt_sha256", None)
    return json.dumps(body, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()


def validate_evidence_receipts(root: Path, findings: list[str]) -> None:
    evidence = root / "evidence"
    if not evidence.is_dir():
        findings.append("EVIDENCE_DIRECTORY_MISSING")
        return

    def validate_artifact_map(mapping: object, source: str, receipt_path: Path) -> None:
        if not isinstance(mapping, dict):
            findings.append("EVIDENCE_ARTIFACT_MAP_INVALID:" + source)
            return
        for rel, expected in mapping.items():
            if not isinstance(rel, str) or not isinstance(expected, str):
                findings.append("EVIDENCE_ARTIFACT_ENTRY_INVALID:" + source)
                continue
            root_target = root / rel
            local_target = receipt_path.parent / rel
            target = root_target if root_target.is_file() else local_target
            if not target.is_file():
                findings.append("EVIDENCE_ARTIFACT_MISSING:" + source + ":" + rel)
            elif sha(target) != expected:
                findings.append("EVIDENCE_ARTIFACT_HASH_MISMATCH:" + source + ":" + rel)

    for path in sorted(evidence.rglob("*.json")):
        rel = path.relative_to(root).as_posix()
        try:
            data = json.loads(path.read_text())
        except Exception as exc:
            findings.append("EVIDENCE_JSON_INVALID:" + rel + ":" + type(exc).__name__)
            continue
        if not isinstance(data, dict):
            continue
        receipt = data.get("receipt_sha256")
        if receipt is not None:
            expected = hashlib.sha256(_canonical_without_receipt(data)).hexdigest()
            if receipt != expected:
                findings.append("EVIDENCE_RECEIPT_HASH_MISMATCH:" + rel)
        if "artifact_sha256" in data:
            validate_artifact_map(data["artifact_sha256"], rel + ":artifact_sha256", path)
        for index, lens in enumerate(data.get("lenses", [])):
            if isinstance(lens, dict) and "changed_artifact_sha256" in lens:
                validate_artifact_map(lens["changed_artifact_sha256"], rel + f":lenses[{index}]", path)
            if isinstance(lens, dict) and lens.get("developer_burden_delta_ref"):
                target = root / str(lens["developer_burden_delta_ref"])
                if not target.is_file():
                    findings.append("EVIDENCE_REFERENCE_MISSING:" + rel + ":" + str(lens["developer_burden_delta_ref"]))


def validate_manifest(root: Path, manifest: Path, findings: list[str]) -> None:
    try:
        data = json.loads(manifest.read_text())
        indexed = {row["path"]: row for row in data["files"]}
        if len(indexed) != len(data["files"]):
            findings.append("MANIFEST_DUPLICATE_PATH")
        for rel, row in indexed.items():
            reason = unsafe_path_reason(rel)
            if reason:
                findings.append("MANIFEST_UNSAFE_PATH:" + reason + ":" + rel)
            path = root / rel
            if not path.is_file() or path.stat().st_size != row["size"] or sha(path) != row["sha256"]:
                findings.append("MANIFEST_MISMATCH:" + rel)
        current = []
        for path in sorted(root.rglob("*")):
            if not path.is_file() or path.is_symlink():
                continue
            rel = path.relative_to(root).as_posix()
            if is_embedded_source(rel) or rel in MANIFEST_EXCLUDED or any(rel.startswith(prefix) for prefix in MANIFEST_EXCLUDED_PREFIXES) or is_garbage(path) or rel.endswith((".pyc", ".pyo", ".zip", ".whl")):
                continue
            current.append(rel)
        if set(current) != set(indexed):
            findings.append("MANIFEST_FILE_SET_MISMATCH")
        if data.get("manifest_payload_file_count") != len(indexed):
            findings.append("MANIFEST_COUNT_MISMATCH")
        if data.get("manifest_payload_bytes") != sum(row["size"] for row in indexed.values()):
            findings.append("MANIFEST_BYTES_MISMATCH")
        expected_payload = hashlib.sha256(json.dumps(data["files"], sort_keys=True, separators=(",", ":")).encode()).hexdigest()
        if data.get("payload_sha256") != expected_payload:
            findings.append("MANIFEST_PAYLOAD_HASH_MISMATCH")
        try:
            project = tomllib.loads((root / "pyproject.toml").read_text())
            version = project["project"]["version"]
            if data.get("candidate_version") != version:
                findings.append("MANIFEST_VERSION_MISMATCH")
        except Exception:
            findings.append("MANIFEST_VERSION_UNAVAILABLE")
    except Exception as exc:
        findings.append("MANIFEST:" + type(exc).__name__)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--manifest", type=Path, required=True)
    args = parser.parse_args()
    root = args.root.resolve()
    findings: list[str] = []

    garbage_roots: set[str] = set()
    for path in root.rglob("*"):
        rel = path.relative_to(root).as_posix()
        if is_embedded_source(rel):
            continue
        reason = unsafe_path_reason(rel)
        if reason:
            findings.append("UNSAFE_PATH:" + reason + ":" + rel)
        if path.is_symlink():
            findings.append("SYMLINK:" + rel)
            continue
        if is_garbage(path):
            top = next((part for part in path.relative_to(root).parts if part in GARBAGE_NAMES or part.endswith((".egg-info", ".dist-info"))), rel)
            garbage_roots.add(top)
            continue
        if not path.is_file():
            continue
        if "/" not in rel and rel not in ALLOWED_ROOT_FILES:
            findings.append("UNEXPECTED_ROOT_FILE:" + rel)
        if rel.endswith(FORBIDDEN_SUFFIXES):
            findings.append("FORBIDDEN_FILE:" + rel)
        text = ""
        if path.stat().st_size < 2_000_000:
            try:
                text = path.read_text()
            except UnicodeDecodeError:
                pass
        if text:
            semantic_text = unfinished_scan_text(path, text)
            if UNFINISHED.search(semantic_text):
                findings.append("UNFINISHED_MARKER:" + rel)
            if PLACEHOLDER.search(semantic_text):
                findings.append("PLACEHOLDER:" + rel)
            if any(pattern.search(semantic_text) for pattern in SECRET_PATTERNS):
                findings.append("SECRET_LITERAL:" + rel)
        try:
            if path.suffix == ".py":
                ast.parse(text)
            elif path.suffix == ".json":
                json.loads(text)
            elif path.suffix in {".yaml", ".yml"}:
                # Delivery YAML is emitted as JSON (a valid YAML subset) so validation is standard-library only.
                json.loads(text)
            elif path.name == "pyproject.toml" or path.suffix == ".toml":
                tomllib.loads(text)
            elif path.suffix == ".js":
                node = subprocess.run(["node", "--check", str(path)], capture_output=True, text=True)
                if node.returncode:
                    findings.append("JS_SYNTAX:" + rel + ":" + node.stderr[-200:])
            elif path.suffix in {".html", ".htm"}:
                parser = HTMLParser(); parser.feed(text); parser.close()
            elif path.suffix == ".sh":
                check = subprocess.run(["bash", "-n", str(path)], capture_output=True, text=True)
                if check.returncode:
                    findings.append("SHELL_SYNTAX:" + rel + ":" + check.stderr[-200:])
        except Exception as exc:
            findings.append("SYNTAX:" + rel + ":" + type(exc).__name__)
    findings.extend("BUILD_GARBAGE:" + item for item in sorted(garbage_roots))

    try:
        connection = sqlite3.connect(":memory:")
        connection.executescript((root / "db/schema.sql").read_text())
        connection.close()
    except Exception as exc:
        findings.append("SQL_SCHEMA:" + type(exc).__name__)

    validate_dag_and_trace(root, findings)
    validate_evidence_receipts(root, findings)
    validate_embedded_stock_skill(root, findings)
    try:
        contract = json.loads((root / "machine/facts/task_execution_contract.json").read_text())
        task_rows = contract["tasks"]
        task_ids = {row["task_id"] for row in task_rows}
        dag_rows = json.loads((root / "machine/facts/task_dag.json").read_text())["tasks"]
        dag_by_id = {row["id"]: row for row in dag_rows}
        dag_ids = set(dag_by_id)
        if len(task_ids) != len(task_rows):
            findings.append("TASK_EXECUTION_CONTRACT_DUPLICATE_ID")
        if task_ids != dag_ids:
            findings.append("TASK_EXECUTION_CONTRACT_SET_MISMATCH")
        try:
            project_version = tomllib.loads((root / "pyproject.toml").read_text())["project"]["version"]
            if contract.get("version") != project_version:
                findings.append("TASK_EXECUTION_CONTRACT_VERSION_MISMATCH")
        except Exception:
            findings.append("TASK_EXECUTION_CONTRACT_VERSION_UNAVAILABLE")
        if contract.get("schema_version") != "1.1.0":
            findings.append("TASK_EXECUTION_CONTRACT_SCHEMA_VERSION")
        required_fields = (
            "title", "mode", "environment_bound", "environment_bound_reason",
            "authorization_required", "authorization_env", "required_env", "commands",
            "timeout_seconds", "allow_degraded", "expected", "failure_branch",
            "stop_condition", "rollback", "evidence_path"
        )
        for row in task_rows:
            tid = row.get("task_id", "UNKNOWN")
            for key in required_fields:
                if key not in row:
                    findings.append("TASK_EXECUTION_CONTRACT_MISSING:" + tid + ":" + key)
            if row.get("mode") not in {"DETERMINISTIC", "ENVIRONMENT_BOUND", "AUTHORIZED_SIDE_EFFECT"}:
                findings.append("TASK_EXECUTION_CONTRACT_MODE:" + tid)
            if row.get("authorization_required") and row.get("mode") != "AUTHORIZED_SIDE_EFFECT":
                findings.append("TASK_EXECUTION_CONTRACT_AUTH_MODE:" + tid)
            if row.get("authorization_required") and not row.get("authorization_env"):
                findings.append("TASK_EXECUTION_CONTRACT_AUTH_ENV:" + tid)
            if not isinstance(row.get("commands"), list) or not row.get("commands"):
                findings.append("TASK_EXECUTION_CONTRACT_COMMANDS:" + tid)
            for command in row.get("commands", []):
                if not isinstance(command, list) or not command or not all(isinstance(item, str) and item for item in command):
                    findings.append("TASK_EXECUTION_CONTRACT_COMMAND_INVALID:" + tid)
                    continue
                if command[0] in {"python3", "bash"} and len(command) > 1 and command[1].startswith(("scripts/", "machine/")) and not (root / command[1]).is_file():
                    findings.append("TASK_EXECUTION_CONTRACT_COMMAND_MISSING:" + tid + ":" + command[1])
            if row.get("evidence_path") != "{ARTIFACT_DIR}/tasks/" + tid + ".json":
                findings.append("TASK_EXECUTION_CONTRACT_EVIDENCE_PATH:" + tid)
            if tid in dag_by_id and row.get("environment_bound") != dag_by_id[tid].get("environment_bound"):
                findings.append("TASK_EXECUTION_CONTRACT_ENV_MISMATCH:" + tid)
        if (root / "machine/facts/environment_task_contracts.json").exists() or (root / "schemas/environment_task_contracts.schema.json").exists():
            findings.append("PARALLEL_TASK_CONTRACT_FORBIDDEN")
    except Exception as exc:
        findings.append("TASK_EXECUTION_CONTRACT:" + type(exc).__name__)

    required_delivery = (
        "00_READ_FIRST.md", "PURSUING_GOAL.txt", "ROADMAP.md", "CODEX_LAST_MILE_PROMPT.txt",
        "CANONICAL_STATE.json", "MEMORY_RECONCILIATION.md",
        "schemas/task_execution_contract.schema.json",
        "scripts/build_review_input.py", "scripts/build_review_chain.py",
        "scripts/frozen_replay.py", "scripts/verify_frozen_replays.py",
        "scripts/build_stop_and_freeze.py", "scripts/build_final_zip.py",
        "scripts/freeze_candidate_contracts.py", "schemas/candidate_freeze.schema.json",
        "scripts/prepare_formal_candidate.sh", "scripts/close_formal_candidate.sh",
        "scripts/transition_canonical_state.py", "scripts/build_skill_pass_c.py",
        "scripts/verify_skill_pass_c.py", "schemas/state_transition.schema.json", "schemas/skill_pass_c.schema.json",
        "schemas/taskpack_owner_approval.schema.json", "schemas/taskpack_seal.schema.json",
        "scripts/build_taskpack_owner_approval.py", "scripts/build_taskpack_seal.py", "scripts/build_taskpack_zip.py",
        "scripts/verify_taskpack_seal.py", "machine/facts/final_scope_summary.json",
        "machine/facts/residual_environment_tasks.json", "machine/facts/skill_route_summary.json"
    )
    for rel in required_delivery:
        if not (root / rel).is_file():
            findings.append("REQUIRED_DELIVERY_FILE_MISSING:" + rel)
    if (root / "machine/facts/human_docs.json").exists():
        findings.append("PARALLEL_HUMAN_DOC_SOURCE_FORBIDDEN")
    validate_manifest(root, args.manifest, findings)

    result = {"state": "PASS" if not findings else "FAIL", "findings": sorted(set(findings)), "finding_count": len(set(findings))}
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    return 0 if not findings else 2


if __name__ == "__main__":
    raise SystemExit(main())
