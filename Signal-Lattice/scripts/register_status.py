#!/usr/bin/env python3
from __future__ import annotations

import argparse
import ast
import hashlib
import json
import os
import re
import subprocess
import tempfile
from pathlib import Path

PROJECT = {
    "name": "Signal Lattice",
    "url": "https://signal-lattice.linzezhang.com",
    "parts": ["前台", "后台"],
    "repo": "MetaDatabase",
    "host": "OVH VPS-1",
    "db": "OVH SQLite · 可重建事务缓存/队列/Runtime Journal/Outbox",
    "store": "Private-Database 结构化事实 + R2 对象字节",
    "deploy": "host-direct systemd + Cloudflare Tunnel",
    "backup": "Private-Database + R2 + OCI",
    "agent": "无（运行期模型调用 0）",
    "notify": "status.linzezhang.com",
    "owns": {"systemd": ["signal-lattice-"]},
}


def offset(text: str, line: int, column: int) -> int:
    lines = text.splitlines(keepends=True)
    return sum(len(item) for item in lines[: line - 1]) + column


def assignment(tree: ast.AST, name: str) -> ast.Assign:
    for node in ast.walk(tree):
        if isinstance(node, ast.Assign) and any(isinstance(target, ast.Name) and target.id == name for target in node.targets):
            return node
    raise ValueError(name + "_ASSIGNMENT_NOT_FOUND")


def format_entry(entry: dict[str, object], indent: str = "    ") -> str:
    return (
        indent + '{"name": ' + json.dumps(entry["name"], ensure_ascii=False)
        + ', "url": ' + json.dumps(entry["url"], ensure_ascii=False)
        + ', "parts": ' + json.dumps(entry["parts"], ensure_ascii=False)
        + ', "repo": "MetaDatabase",\n'
        + indent + ' "host": ' + json.dumps(entry["host"], ensure_ascii=False)
        + ', "db": ' + json.dumps(entry["db"], ensure_ascii=False)
        + ', "store": ' + json.dumps(entry["store"], ensure_ascii=False) + ',\n'
        + indent + ' "deploy": ' + json.dumps(entry["deploy"], ensure_ascii=False)
        + ', "backup": ' + json.dumps(entry["backup"], ensure_ascii=False) + ',\n'
        + indent + ' "agent": ' + json.dumps(entry["agent"], ensure_ascii=False)
        + ', "notify": ' + json.dumps(entry["notify"], ensure_ascii=False)
        + ', "owns": {"systemd": ["signal-lattice-"]}}'
    )


def patch_projects(text: str) -> tuple[str, bool, int]:
    tree = ast.parse(text)
    node = assignment(tree, "PROJECTS")
    if not isinstance(node.value, ast.List):
        raise ValueError("PROJECTS_NOT_LIST")
    projects = ast.literal_eval(node.value)
    if not isinstance(projects, list) or not all(isinstance(item, dict) for item in projects):
        raise ValueError("PROJECTS_LITERAL_INVALID")
    matches = [index for index, item in enumerate(projects) if item.get("name") == PROJECT["name"]]
    if len(matches) > 1:
        raise ValueError("DUPLICATE_SIGNAL_LATTICE_REGISTRATION")
    formatted = format_entry(PROJECT)
    if matches:
        index = matches[0]
        if projects[index] == PROJECT:
            return text, False, len(projects)
        dict_node = node.value.elts[index]
        start = offset(text, dict_node.lineno, dict_node.col_offset)
        end = offset(text, dict_node.end_lineno, dict_node.end_col_offset)
        return text[:start] + formatted.lstrip() + text[end:], True, len(projects)
    closing = offset(text, node.value.end_lineno, node.value.end_col_offset - 1)
    prefix = text[:closing]
    if projects and not prefix.rstrip().endswith(","):
        prefix = prefix.rstrip() + ",\n"
    elif not prefix.endswith("\n"):
        prefix += "\n"
    updated = prefix + formatted + ",\n" + text[closing:]
    return updated, True, len(projects) + 1


def patch_systemd_pattern(text: str) -> tuple[str, bool]:
    tree = ast.parse(text)
    node = assignment(tree, "SYSTEMD_SERVICE_PATTERN")
    if not isinstance(node.value, ast.Call) or not node.value.args or not isinstance(node.value.args[0], ast.Constant) or not isinstance(node.value.args[0].value, str):
        raise ValueError("SYSTEMD_PATTERN_INVALID")
    pattern = node.value.args[0].value
    if "signal-lattice" in pattern:
        return text, False
    match = re.fullmatch(r"\(([^)]+)\)(.*)", pattern)
    if not match:
        raise ValueError("SYSTEMD_PATTERN_SHAPE_UNSUPPORTED")
    alternatives = match.group(1).split("|")
    alternatives.append("signal-lattice")
    new_pattern = "(" + "|".join(dict.fromkeys(alternatives)) + ")" + match.group(2)
    literal_node = node.value.args[0]
    start = offset(text, literal_node.lineno, literal_node.col_offset)
    end = offset(text, literal_node.end_lineno, literal_node.end_col_offset)
    return text[:start] + repr(new_pattern) + text[end:], True


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


def find_status_dir(root: Path) -> Path:
    for candidate in (root / "status", root):
        if (candidate / "collector/collect.py").is_file():
            return candidate
    raise FileNotFoundError("STATUS_COLLECTOR_NOT_FOUND")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--status-root", type=Path, required=True)
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--receipt", type=Path)
    args = parser.parse_args()
    try:
        status_dir = find_status_dir(args.status_root.resolve())
    except FileNotFoundError as exc:
        print(json.dumps({"state": "BLOCKED", "reason": str(exc), "developer_research_required": False}, sort_keys=True))
        return 2
    collector = status_dir / "collector/collect.py"
    test_file = status_dir / "collector/tests/test_software_registry.py"
    if not test_file.is_file():
        print(json.dumps({"state": "BLOCKED", "reason": "STATUS_REGISTRY_TEST_MISSING", "developer_research_required": False}, sort_keys=True))
        return 2
    original = collector.read_text(encoding="utf-8")
    try:
        text, project_changed, project_count = patch_projects(original)
        text, pattern_changed = patch_systemd_pattern(text)
        ast.parse(text)
    except (ValueError, SyntaxError) as exc:
        print(json.dumps({"state": "BLOCKED", "reason": str(exc), "developer_research_required": False}, ensure_ascii=False, sort_keys=True))
        return 2
    changed = text != original
    backup_path = collector.with_suffix(collector.suffix + ".signal-lattice.bak")
    test_result: dict[str, object] = {"state": "NOT_RUN"}
    if args.apply and changed:
        backup_path.write_text(original, encoding="utf-8")
        atomic_write(collector, text)
        completed = subprocess.run(
            [os.sys.executable, str(test_file)],
            cwd=status_dir,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=180,
            env={"PATH": os.environ.get("PATH", "/usr/bin:/bin"), "LANG": "C.UTF-8", "LC_ALL": "C.UTF-8", "PYTHONHASHSEED": "0"},
        )
        test_result = {
            "state": "PASS" if completed.returncode == 0 else "FAIL",
            "returncode": completed.returncode,
            "stdout_tail": completed.stdout[-2000:],
            "stderr_tail": completed.stderr[-2000:],
        }
        if completed.returncode != 0:
            atomic_write(collector, original)
            print(json.dumps({"state": "BLOCKED", "reason": "STATUS_REGISTRY_TEST_FAILED", "test": test_result, "restored": True}, ensure_ascii=False, sort_keys=True))
            return 2
    elif args.apply:
        completed = subprocess.run(
            [os.sys.executable, str(test_file)], cwd=status_dir, text=True,
            stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=180,
            env={"PATH": os.environ.get("PATH", "/usr/bin:/bin"), "LANG": "C.UTF-8", "LC_ALL": "C.UTF-8", "PYTHONHASHSEED": "0"},
        )
        test_result = {"state": "PASS" if completed.returncode == 0 else "FAIL", "returncode": completed.returncode, "stdout_tail": completed.stdout[-2000:], "stderr_tail": completed.stderr[-2000:]}
        if completed.returncode != 0:
            print(json.dumps({"state": "BLOCKED", "reason": "STATUS_REGISTRY_TEST_FAILED", "test": test_result}, ensure_ascii=False, sort_keys=True))
            return 2
    result = {
        "schema_version": "1.0.0",
        "state": "PASS",
        "project": PROJECT["name"],
        "project_count": project_count,
        "changed": changed,
        "applied": bool(args.apply and changed),
        "project_registration_changed": project_changed,
        "systemd_discovery_pattern_changed": pattern_changed,
        "collector": collector.as_posix(),
        "collector_sha256": hashlib.sha256((text if args.apply else original).encode()).hexdigest(),
        "test": test_result,
        "backup": backup_path.as_posix() if args.apply and changed else None,
        "developer_research_required": False,
    }
    if args.receipt:
        args.receipt.parent.mkdir(parents=True, exist_ok=True)
        args.receipt.write_text(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
