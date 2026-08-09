from __future__ import annotations

import ast
import argparse
import json
import os
import re
import stat
import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
REQUIRED = {
    "START_HERE.md",
    "AGENTS.md",
    "PURSUING_GOAL.txt",
    "README.md",
    "LICENSE",
    "NOTICE",
    "Dockerfile",
    "compose.yaml",
    ".env.example",
    "requirements.txt",
    "requirements-dev.txt",
    "app/db_types.py",
    "app/services/data_migration.py",
    "app/services/ai_provider.py",
    "deploy/deploy.sh",
    "deploy/acceptance.sh",
    "deploy/rollback.sh",
    "deploy/restore.sh",
    "taskpack/CANONICAL_CONTRACT.md",
    "taskpack/ARCHITECTURE.md",
    "taskpack/DELIVERY_AND_ACCEPTANCE.md",
    "taskpack/TRACEABILITY.md",
    "taskpack/ROADMAP.md",
    "taskpack/LOCAL_ACCEPTANCE.md",
    "taskpack/DEPENDENCIES.md",
    "taskpack/task_dag.json",
    "taskpack/acceptance_contract.json",
    "tests/http_golden.py",
    "tests/test_data_migration.py",
    "tests/test_ai_provider.py",
    "tests/e2e_golden.py",
    "tests/e2e_live_readonly.py",
    "tests/e2e_live_golden.py",
    "tools/verify_runtime.py",
}
FORBIDDEN_DIRS = {
    "__pycache__", ".pytest_cache", ".mypy_cache", ".ruff_cache", ".venv", ".venv-acceptance"
}
FORBIDDEN_SUFFIXES = {".pyc", ".pyo"}
PLACEHOLDER_PATTERN = re.compile(r"\b(?:TODO|TBD|FIXME)\b", re.IGNORECASE)


def topological_check(tasks: list[dict[str, object]]) -> list[str]:
    errors: list[str] = []
    ids = {str(task.get("id")) for task in tasks}
    graph: dict[str, list[str]] = {}
    for task in tasks:
        task_id = str(task.get("id"))
        deps = [str(item) for item in task.get("dependencies", [])]
        graph[task_id] = deps
        unknown = sorted(set(deps) - ids)
        if unknown:
            errors.append(f"{task_id} has unknown dependencies: {', '.join(unknown)}")

    visiting: set[str] = set()
    visited: set[str] = set()

    def visit(node: str) -> None:
        if node in visiting:
            errors.append(f"task DAG cycle detected at {node}")
            return
        if node in visited:
            return
        visiting.add(node)
        for dep in graph.get(node, []):
            visit(dep)
        visiting.remove(node)
        visited.add(node)

    for node in graph:
        visit(node)
    return errors


def shell_syntax(path: Path) -> str | None:
    result = subprocess.run(["bash", "-n", str(path)], capture_output=True, text=True)
    return None if result.returncode == 0 else (result.stderr.strip() or "bash syntax failure")


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate the frozen JobHuntBot taskpack")
    parser.add_argument(
        "--allow-production-runtime-secrets",
        action="store_true",
        help="allow only root-level 0600 .env and OWNER_LOGIN.txt during target acceptance",
    )
    args = parser.parse_args()
    errors: list[str] = []
    warnings: list[str] = []

    for relative in sorted(REQUIRED):
        if not (ROOT / relative).is_file():
            errors.append(f"missing required file: {relative}")

    for path in ROOT.rglob("*"):
        relative = path.relative_to(ROOT)
        if any(part in FORBIDDEN_DIRS for part in relative.parts):
            errors.append(f"generated/cache directory present: {relative}")
        if path.is_file() and path.suffix in FORBIDDEN_SUFFIXES:
            errors.append(f"compiled artifact present: {relative}")
        if path.is_symlink():
            errors.append(f"symlink is not allowed in taskpack: {relative}")
        if path.name in {".env", "OWNER_LOGIN.txt"}:
            if not args.allow_production_runtime_secrets:
                errors.append(f"secret-bearing runtime file present: {relative}")
            elif relative.parent != Path(".") or stat.S_IMODE(path.stat().st_mode) != 0o600:
                errors.append(f"production runtime secret has unsafe location or permissions: {relative}")

    dag_path = ROOT / "taskpack/task_dag.json"
    acceptance_path = ROOT / "taskpack/acceptance_contract.json"
    if dag_path.is_file():
        try:
            dag = json.loads(dag_path.read_text(encoding="utf-8"))
            tasks = dag.get("tasks", [])
            if not isinstance(tasks, list) or not tasks:
                errors.append("task DAG has no tasks")
            else:
                errors.extend(topological_check(tasks))
        except (OSError, json.JSONDecodeError) as exc:
            errors.append(f"invalid task DAG: {exc}")
            tasks = []
    else:
        tasks = []

    task_ids = {str(task.get("id")) for task in tasks}
    if acceptance_path.is_file():
        try:
            contract = json.loads(acceptance_path.read_text(encoding="utf-8"))
            requirements = contract.get("requirements", [])
            requirement_ids = [str(item.get("id")) for item in requirements]
            if len(requirement_ids) != len(set(requirement_ids)):
                errors.append("acceptance requirement ids are not unique")
            for item in requirements:
                req_id = str(item.get("id"))
                unknown_tasks = sorted(set(map(str, item.get("tasks", []))) - task_ids)
                if unknown_tasks:
                    errors.append(f"{req_id} refers to unknown tasks: {', '.join(unknown_tasks)}")
                for test_path in item.get("tests", []):
                    if not (ROOT / str(test_path)).exists():
                        errors.append(f"{req_id} refers to missing test/artifact: {test_path}")
                if not str(item.get("oracle", "")).strip():
                    errors.append(f"{req_id} has no business oracle")
        except (OSError, json.JSONDecodeError) as exc:
            errors.append(f"invalid acceptance contract: {exc}")

    for path in ROOT.rglob("*.py"):
        relative = path.relative_to(ROOT)
        if any(part in FORBIDDEN_DIRS for part in relative.parts):
            continue
        try:
            ast.parse(path.read_text(encoding="utf-8"), filename=str(relative))
        except (OSError, SyntaxError, UnicodeDecodeError) as exc:
            errors.append(f"python syntax failure in {relative}: {exc}")

    for path in list((ROOT / "deploy").glob("*.sh")) + list((ROOT / "ops").glob("*.sh")):
        failure = shell_syntax(path)
        if failure:
            errors.append(f"shell syntax failure in {path.relative_to(ROOT)}: {failure}")
        if not os.access(path, os.X_OK):
            errors.append(f"shell script is not executable: {path.relative_to(ROOT)}")

    for path in ROOT.rglob("*"):
        if not path.is_file():
            continue
        relative = path.relative_to(ROOT)
        if any(part in FORBIDDEN_DIRS for part in relative.parts):
            continue
        if path.suffix.lower() not in {
            ".py", ".sh", ".md", ".txt", ".json", ".yaml", ".yml", ".html", ".css", ".js", ""
        }:
            continue
        try:
            content = path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            continue
        if relative == Path("tools/validate_taskpack.py"):
            continue
        if PLACEHOLDER_PATTERN.search(content):
            errors.append(f"unresolved planning placeholder in {relative}")

    dockerfile = ROOT / "Dockerfile"
    if dockerfile.is_file():
        for raw in dockerfile.read_text(encoding="utf-8").splitlines():
            line = raw.strip()
            if not line.startswith("COPY "):
                continue
            parts = line.split()
            sources = parts[1:-1]
            for source in sources:
                if source.startswith("--") or any(char in source for char in "*$?"):
                    continue
                if not (ROOT / source).exists():
                    errors.append(f"Dockerfile COPY source is missing: {source}")

    try:
        import yaml  # type: ignore

        with (ROOT / "compose.yaml").open(encoding="utf-8") as handle:
            compose = yaml.safe_load(handle)
        if not isinstance(compose, dict) or "services" not in compose:
            errors.append("compose.yaml has no services map")
    except ImportError:
        warnings.append("PyYAML unavailable; docker compose config remains the target parser")
    except Exception as exc:
        errors.append(f"compose.yaml parse failure: {exc}")

    result = {
        "result": "PASS" if not errors else "FAIL",
        "errors": errors,
        "warnings": warnings,
        "task_count": len(tasks),
        "required_file_count": len(REQUIRED),
    }
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if not errors else 1


if __name__ == "__main__":
    raise SystemExit(main())
