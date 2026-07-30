from __future__ import annotations

import argparse
import json
import subprocess
import sys
import tempfile
from pathlib import Path


HERE = Path(__file__).resolve().parents[1]
PREPARE = HERE / "scripts/prepare_compat_taskpack.py"
BASELINE = json.loads((HERE / "COMPATIBILITY_BASELINE.json").read_text(encoding="utf-8"))
ROOT_NAME = BASELINE["base_taskpack"]["root"]


def run(argv: list[str], cwd: Path | None = None) -> subprocess.CompletedProcess[str]:
    completed = subprocess.run(argv, cwd=cwd, text=True, capture_output=True, check=False)
    if completed.returncode:
        raise RuntimeError(f"command failed: {argv}\n{(completed.stderr or completed.stdout)[-3000:]}")
    return completed


def write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def create_synthetic_repo(root: Path) -> Path:
    origin = root / "origin.git"
    repo = root / "MetaDatabase"
    run(["git", "init", "--bare", str(origin)])
    run(["git", "init", "-b", "main", str(repo)])
    run(["git", "config", "user.email", "compat@example.invalid"], repo)
    run(["git", "config", "user.name", "Social Archive Compat Test"], repo)
    run(["git", "remote", "add", "origin", str(origin)], repo)
    write(repo / "README.md", "synthetic compatibility repository\n")
    write(repo / "xhs-douyin-2notion/.gitignore", "runtime/\n")
    write(repo / "xhs-douyin-2notion/apps/companion/src/x2n_companion/canonical_store.py", "class CanonicalStore:\n    pass\n")
    write(repo / "xhs-douyin-2notion/apps/companion/src/x2n_companion/orchestrator.py", "class CurrentPageOrchestrator:\n    pass\n")
    write(repo / "xhs-douyin-2notion/apps/companion/tests/test_canonical_store.py", "# focused recovery fixture\n")
    write(repo / "xhs-douyin-2notion/apps/companion/tests/test_orchestrator.py", "# focused transaction fixture\n")
    write(repo / "xhs-douyin-2notion/apps/companion/tests/test_operations.py", "# focused operations fixture\n")
    write(repo / "xhs-douyin-2notion/runtime/private.sqlite", "ignored synthetic runtime bytes\n")
    run(["git", "add", "README.md", "xhs-douyin-2notion/.gitignore", "xhs-douyin-2notion/apps"], repo)
    run(["git", "commit", "-m", "synthetic legacy core"], repo)
    run(["git", "push", "-u", "origin", "main"], repo)
    run(["git", "checkout", "-b", "codex/social-archive-compat-test"], repo)
    return repo


def json_output(command: list[str], cwd: Path | None = None) -> dict[str, object]:
    completed = run(command, cwd)
    return json.loads(completed.stdout)


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate the Social Archive v0.0.0.4 compatibility overlay in an isolated synthetic repository.")
    parser.add_argument("--base-zip", type=Path, required=True)
    args = parser.parse_args()
    with tempfile.TemporaryDirectory(prefix="social-archive-compat-") as directory:
        temp = Path(directory)
        extraction = temp / "compatible-taskpack"
        provenance = json_output([sys.executable, str(PREPARE), "--base-zip", str(args.base_zip.resolve()), "--output", str(extraction)])
        taskpack = extraction / str(ROOT_NAME)
        repo = create_synthetic_repo(temp)
        apply_dir = taskpack / "07_IMPLEMENTATION/apply"

        preconditions = json_output([sys.executable, str(apply_dir / "verify_preconditions.py"), "--repo", str(repo), "--fetch"])
        if preconditions.get("status") != "READY":
            raise RuntimeError(f"worktree branch precondition unexpectedly blocked: {preconditions}")

        semantic = json_output([sys.executable, str(apply_dir / "semantic_classify.py"), "--repo", str(repo)])
        expected_decision = "PRESERVE_TRANSACTION_CORE_REBUILD_PRODUCT_SHELL_AND_CONNECTORS"
        if semantic.get("decision") != expected_decision:
            raise RuntimeError(f"legacy companion core was not detected: {semantic}")

        run([sys.executable, str(apply_dir / "apply_taskpack.py"), "--repo", str(repo), "--phase", "identity"])
        moved_core = repo / "social-archive/apps/companion/src/x2n_companion/canonical_store.py"
        retained_runtime = repo / "xhs-douyin-2notion/runtime/private.sqlite"
        if not moved_core.is_file() or not retained_runtime.is_file():
            raise RuntimeError("tracked core move or ignored runtime retention failed")
        if (repo / "social-archive/src/social_archive/db.py").exists():
            raise RuntimeError("identity phase incorrectly created a second core")
        root_ignore = (repo / ".gitignore").read_text(encoding="utf-8")
        for rule in ("/.social-archive-migration/", "/.social-archive-candidate-v0.0.0.4/"):
            if rule not in root_ignore:
                raise RuntimeError("generated migration path is not ignored")

        run([sys.executable, str(apply_dir / "apply_taskpack.py"), "--repo", str(repo), "--phase", "all"])
        candidate = repo / ".social-archive-candidate-v0.0.0.4/social-archive/src/social_archive/db.py"
        if not candidate.is_file() or (repo / "social-archive/src/social_archive/db.py").exists():
            raise RuntimeError("prebuilt core was not retained as an SA-003 candidate")

        rollback = json_output([sys.executable, str(apply_dir / "rollback_taskpack.py"), "--repo", str(repo), "--latest"])
        if rollback.get("status") != "ROLLBACK_PLAN":
            raise RuntimeError("rollback default was not non-mutating")
        migration = subprocess.run(
            [sys.executable, str(apply_dir / "migrate_legacy_sqlite.py"), "--repo", str(repo), "--dry-run"],
            text=True,
            capture_output=True,
            check=False,
        )
        migration_result = json.loads(migration.stdout)
        if migration.returncode != 2 or migration_result.get("reason") != "EXPLICIT_OWNER_AUTHORIZED_SNAPSHOT_REQUIRED":
            raise RuntimeError("SQLite migration did not fail closed without one explicit snapshot")

        report = {
            "status": "PASS",
            "base_taskpack_verifier": provenance["taskpack_verifier_status"],
            "semantic_decision": semantic["decision"],
            "worktree_branch_allowed": True,
            "ignored_runtime_retained": True,
            "second_core_withheld_as_candidate": True,
            "rollback_default": rollback["status"],
            "raw_sqlite_discovery": migration_result["reason"],
        }
        print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (OSError, RuntimeError, json.JSONDecodeError) as exc:
        print(json.dumps({"status": "FAIL", "error": str(exc)}, ensure_ascii=False))
        raise SystemExit(2)
