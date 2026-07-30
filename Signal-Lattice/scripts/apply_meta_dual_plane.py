#!/usr/bin/env python3
from __future__ import annotations

import argparse
import ast
import hashlib
import json
import os
import re
import shlex
import tempfile
from pathlib import Path

PROJECT = "Signal-Lattice"
REQUIRED_PROJECT_TOOLS = (
    "machine/tools/render_human.py",
    "machine/tools/check_doc_budget.py",
    "machine/tools/check_blocker_stop.py",
    "machine/tools/check_dual_plane_ci.py",
)


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def balanced_literal(text: str, start: int, opener: str = "{", closer: str = "}") -> tuple[int, int]:
    depth = 0
    quote: str | None = None
    escaped = False
    for index in range(start, len(text)):
        char = text[index]
        if quote is not None:
            if escaped:
                escaped = False
            elif char == "\\":
                escaped = True
            elif char == quote:
                quote = None
            continue
        if char in {'"', "'"}:
            quote = char
            continue
        if char == opener:
            depth += 1
        elif char == closer:
            depth -= 1
            if depth == 0:
                return start, index + 1
    raise ValueError("UNBALANCED_LITERAL")


def patch_registered(text: str) -> tuple[str, list[str], bool]:
    match = re.search(r"(?m)^(?P<indent>\s*)registered\s*=\s*\{", text)
    if not match:
        raise ValueError("REGISTERED_SET_NOT_FOUND")
    literal_start = text.index("{", match.start())
    start, end = balanced_literal(text, literal_start)
    current = ast.literal_eval(text[start:end])
    if not isinstance(current, set) or not all(isinstance(x, str) for x in current):
        raise ValueError("REGISTERED_SET_INVALID")
    items = sorted(current | {PROJECT})
    if current == set(items):
        return text, items, False
    indent = match.group("indent")
    item_indent = indent + "  "
    replacement = "{\n" + "\n".join(f'{item_indent}"{item}",' for item in items) + f"\n{indent}}}"
    changed = replacement != text[start:end]
    return text[:start] + replacement + text[end:], items, changed


def patch_projects_command(text: str, registered: list[str]) -> tuple[str, bool]:
    pattern = re.compile(
        r'(?ms)(?P<prefix>^(?P<indent>\s*)python3\s+"\$(?:DUAL_PLANE_TOOL|SCRIPT)"\s+--root\s+\.\s+--projects\s+\\\n)'
        r'(?P<body>.*?)'
        r'(?P<suffix>^\s*(?:--exceptions\s+ABD|--require-projects)\s*$)'
    )
    match = pattern.search(text)
    if not match:
        raise ValueError("PROJECTS_COMMAND_NOT_FOUND")
    body_tokens = shlex.split(match.group("body").replace("\\\n", " ").replace("\\", " "))
    existing_projects = set(body_tokens)
    if existing_projects == set(registered):
        return text, False
    projects = sorted(existing_projects | set(registered))
    indent = match.group("indent") + "  "
    lines: list[str] = []
    chunk = 5
    for offset in range(0, len(projects), chunk):
        part = " ".join(projects[offset:offset + chunk])
        lines.append(indent + part + " \\")
    replacement = match.group("prefix") + "\n".join(lines) + "\n" + match.group("suffix")
    changed = replacement != match.group(0)
    return text[:match.start()] + replacement + text[match.end():], changed


def patch_pass_count(text: str, count: int) -> tuple[str, bool]:
    updated = re.sub(
        r"PASS: \d+ governance projects \+ ABD specialized task-pack workflow classified",
        f"PASS: {count} governance projects + ABD specialized task-pack workflow classified",
        text,
    )
    return updated, updated != text


def atomic_write(path: Path, text: str) -> None:
    fd, tmp_name = tempfile.mkstemp(prefix="." + path.name + ".", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write(text)
            handle.flush()
            os.fsync(handle.fileno())
        os.chmod(tmp_name, path.stat().st_mode & 0o777)
        os.replace(tmp_name, path)
    finally:
        if os.path.exists(tmp_name):
            os.unlink(tmp_name)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo", type=Path, required=True)
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--receipt", type=Path)
    args = parser.parse_args()
    repo = args.repo.resolve()
    workflow = repo / ".github/workflows/dual-plane.yml"
    findings: list[str] = []
    for rel in ("AGENTS.md", ".github/workflows/dual-plane.yml"):
        if not (repo / rel).is_file():
            findings.append("MISSING:" + rel)
    project = repo / PROJECT
    if project.exists():
        for rel in REQUIRED_PROJECT_TOOLS:
            if not (project / rel).is_file():
                findings.append("PROJECT_TOOL_MISSING:" + rel)
    if findings:
        result = {"state": "BLOCKED", "findings": findings, "developer_research_required": False}
        print(json.dumps(result, ensure_ascii=False, sort_keys=True))
        return 2

    original = workflow.read_text(encoding="utf-8")
    try:
        text, registered, changed_set = patch_registered(original)
        text, changed_command = patch_projects_command(text, registered)
        text, changed_count = patch_pass_count(text, len(registered))
    except (ValueError, SyntaxError) as exc:
        result = {"state": "BLOCKED", "findings": [str(exc)], "developer_research_required": False}
        print(json.dumps(result, ensure_ascii=False, sort_keys=True))
        return 2

    changed = text != original
    before_sha = hashlib.sha256(original.encode()).hexdigest()
    after_sha = hashlib.sha256(text.encode()).hexdigest()
    backup: str | None = None
    if args.apply and changed:
        backup_path = workflow.with_suffix(workflow.suffix + ".signal-lattice.bak")
        backup_path.write_text(original, encoding="utf-8")
        backup = backup_path.as_posix()
        atomic_write(workflow, text)

    result = {
        "schema_version": "1.0.0",
        "state": "PASS",
        "project": PROJECT,
        "registered_project_count": len(registered),
        "registered_projects": registered,
        "changed": changed,
        "applied": bool(args.apply and changed),
        "changes": {
            "registered_set": changed_set,
            "projects_command": changed_command,
            "pass_count": changed_count,
        },
        "workflow": workflow.as_posix(),
        "before_sha256": before_sha,
        "after_sha256": after_sha,
        "backup": backup,
        "semantic_patch": True,
        "brittle_line_number_dependency": False,
        "developer_research_required": False,
    }
    if args.receipt:
        args.receipt.parent.mkdir(parents=True, exist_ok=True)
        args.receipt.write_text(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
