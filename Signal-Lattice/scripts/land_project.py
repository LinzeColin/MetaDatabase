#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import subprocess
import tempfile
from pathlib import Path

EXCLUDED_PARTS = {".git", ".pytest_cache", "__pycache__", "build", "dist", ".venv", "venv", "node_modules", ".mypy_cache", ".ruff_cache"}
EXCLUDED_SUFFIXES = (".pyc", ".pyo", ".zip", ".whl")
SOURCE_ONLY_ROOT = "Stock_Skill"


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def inventory(root: Path) -> dict[str, dict[str, object]]:
    rows: dict[str, dict[str, object]] = {}
    if not root.exists():
        return rows
    for path in sorted(root.rglob("*")):
        if path.is_symlink():
            raise ValueError("SYMLINK_FORBIDDEN:" + path.as_posix())
        if not path.is_file():
            continue
        rel = path.relative_to(root)
        if rel.parts[:1] == (SOURCE_ONLY_ROOT,):
            continue
        if any(part in EXCLUDED_PARTS or part.endswith((".egg-info", ".dist-info")) for part in rel.parts):
            continue
        if rel.as_posix().endswith(EXCLUDED_SUFFIXES):
            continue
        rows[rel.as_posix()] = {"size": path.stat().st_size, "sha256": sha(path)}
    return rows


def git_worktree(repo: Path) -> bool:
    completed = subprocess.run(["git", "rev-parse", "--is-inside-work-tree"], cwd=repo, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    return completed.returncode == 0 and completed.stdout.strip() == "true"


def atomic_copytree(source: Path, destination: Path) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    temp = destination.parent / ("." + destination.name + ".tmp")
    if temp.exists():
        shutil.rmtree(temp)
    shutil.copytree(source, temp, ignore=shutil.ignore_patterns(SOURCE_ONLY_ROOT, *EXCLUDED_PARTS, "*.pyc", "*.pyo", "*.zip", "*.whl", "*.egg-info", "*.dist-info"))
    os.replace(temp, destination)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--target-repo", type=Path, required=True)
    parser.add_argument("--target-area", default="Signal-Lattice")
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--receipt", type=Path)
    args = parser.parse_args()
    source = args.source.resolve()
    repo = args.target_repo.resolve()
    destination = repo / args.target_area
    if not source.is_dir():
        print(json.dumps({"state": "BLOCKED", "reason": "SOURCE_MISSING"}, sort_keys=True))
        return 2
    if not repo.is_dir() or not git_worktree(repo):
        print(json.dumps({"state": "BLOCKED", "reason": "TARGET_NOT_GIT_WORKTREE"}, sort_keys=True))
        return 2
    try:
        source_rows = inventory(source)
        target_rows = inventory(destination)
    except ValueError as exc:
        print(json.dumps({"state": "BLOCKED", "reason": str(exc)}, sort_keys=True))
        return 2
    all_paths = sorted(set(source_rows) | set(target_rows))
    classification: dict[str, list[str]] = {key: [] for key in ("satisfied", "apply", "adapt", "equivalent", "conflict", "blocked", "obsolete")}
    for rel in all_paths:
        src = source_rows.get(rel)
        dst = target_rows.get(rel)
        if src and dst:
            classification["satisfied" if src == dst else "conflict"].append(rel)
        elif src:
            classification["apply"].append(rel)
        else:
            classification["obsolete"].append(rel)
    state = "BLOCKED" if classification["conflict"] else ("SATISFIED" if not classification["apply"] else "READY")
    applied: list[str] = []
    rollback: list[str] = []
    if args.apply:
        if classification["conflict"]:
            state = "BLOCKED"
        elif not destination.exists():
            atomic_copytree(source, destination)
            applied = sorted(source_rows)
            rollback = [destination.as_posix()]
            state = "PASS"
        else:
            for rel in classification["apply"]:
                src = source / rel
                dst = destination / rel
                dst.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(src, dst)
                applied.append(rel)
                rollback.append(dst.as_posix())
            state = "PASS"
    payload = {
        "schema_version": "1.0.0",
        "state": state,
        "source": source.as_posix(),
        "target": destination.as_posix(),
        "classification": classification,
        "counts": {key: len(value) for key, value in classification.items()},
        "applied": applied,
        "rollback_paths": rollback,
        "upstream_files_preserved": classification["obsolete"],
        "overwrites_performed": False,
        "developer_research_required": False,
        "resolution": "conflicts require environment-bound Semantic Delta classification; frozen source never overwrites a different target file",
    }
    if args.receipt:
        args.receipt.parent.mkdir(parents=True, exist_ok=True)
        args.receipt.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(payload, ensure_ascii=False, sort_keys=True))
    return 0 if state in {"PASS", "SATISFIED", "READY"} else 2


if __name__ == "__main__":
    raise SystemExit(main())
