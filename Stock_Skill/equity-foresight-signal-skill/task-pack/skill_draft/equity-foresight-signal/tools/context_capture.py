from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
from pathlib import Path

ALLOWED_RULE_FILES = ("AGENTS.md", "CONTRIBUTING.md", "Stock_Skill/AGENTS.md")


def run_git(root: Path, *args: str) -> str:
    completed = subprocess.run(
        ["git", "-C", str(root), *args],
        check=False,
        capture_output=True,
        text=True,
        timeout=20,
    )
    if completed.returncode != 0:
        raise ValueError(f"git {' '.join(args)} failed")
    return completed.stdout.strip()


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def capture(root: Path) -> dict:
    root = root.resolve()
    if not root.is_dir() or not (root / ".git").exists():
        raise ValueError("target must be a Git working tree")
    rules = []
    for relative in ALLOWED_RULE_FILES:
        path = root / relative
        if path.is_file() and not path.is_symlink():
            rules.append({"path": relative, "size": path.stat().st_size, "sha256": digest(path)})
    workflows = []
    workflow_root = root / ".github" / "workflows"
    if workflow_root.is_dir():
        for path in sorted(workflow_root.glob("*")):
            if path.is_file() and not path.is_symlink() and path.suffix in {".yml", ".yaml"}:
                workflows.append({"path": path.relative_to(root).as_posix(), "size": path.stat().st_size, "sha256": digest(path)})
    status_lines = run_git(root, "status", "--porcelain=v1", "--untracked-files=normal").splitlines()
    if len(status_lines) > 2000:
        raise ValueError("working tree status exceeds capture limit")
    report = {
        "schema": "efs.target_context_capture.v1",
        "repository_root_name": root.name,
        "head": run_git(root, "rev-parse", "HEAD"),
        "branch": run_git(root, "branch", "--show-current") or "DETACHED",
        "upstream": run_git(root, "rev-parse", "--abbrev-ref", "--symbolic-full-name", "@{upstream}") if run_git(root, "for-each-ref", "--format=%(upstream:short)", "refs/heads/" + (run_git(root, "branch", "--show-current") or "")) else None,
        "is_clean": not status_lines,
        "status_lines": status_lines,
        "rule_files": rules,
        "workflow_files": workflows,
        "read_only_capture": True,
        "file_contents_included": False,
        "secrets_scanned_or_collected": False,
    }
    encoded = json.dumps(report, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()
    report["capture_sha256"] = hashlib.sha256(encoded).hexdigest()
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description="Read-only target repository context capture")
    parser.add_argument("root", type=Path)
    args = parser.parse_args()
    print(json.dumps(capture(args.root), ensure_ascii=False, sort_keys=True, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
