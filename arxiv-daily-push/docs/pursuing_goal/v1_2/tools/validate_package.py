#!/usr/bin/env python3
"""Fail-closed structural, traceability, archive and digest checks for ADP v1.2."""

from __future__ import annotations

import argparse
import csv
import hashlib
import io
import json
import re
import stat
import sys
import zipfile
from collections import Counter
from pathlib import Path, PurePosixPath

import yaml


ROLE_ALIASES = {
    "manifest": ("MANIFEST.yaml", "MANIFEST.yml", "MANIFEST.json", "TASKPACK_MANIFEST.yaml", "TASKPACK_MANIFEST.yml", "TASKPACK_MANIFEST.json"),
    "pursuing_goal": ("PURSUE_GOAL.md", "PURSUING_GOAL.md", "PURSUING_GOAL_PROMPT.md", "GOAL.md"),
    "prd": ("DECISION_PRD.md", "PRD.md", "PRODUCT_REQUIREMENTS.md", "PRODUCT_DESIGN.md"),
    "technical_design": ("TECHNICAL_OPERATIONS_DESIGN.md", "TECHNICAL_DESIGN.md", "SYSTEM_DESIGN.md", "ARCHITECTURE.md"),
    "roadmap": ("ROADMAP.md", "ROADMAP.yaml", "ROADMAP.yml", "ROADMAP.json"),
    "task_graph": ("TASK_GRAPH.yaml", "TASK_GRAPH.yml", "TASK_GRAPH.json", "TASK_DAG.yaml", "TASK_DAG.yml", "TASK_DAG.json"),
    "acceptance_contract": ("ACCEPTANCE_CONTRACT.yaml", "ACCEPTANCE_CONTRACT.yml", "ACCEPTANCE_CONTRACT.json", "ACCEPTANCE_CONTRACT.md"),
}
EXPECTED_ROLES = {
    "manifest": "MANIFEST.yaml",
    "pursuing_goal": "PURSUING_GOAL.md",
    "prd": "PRD.md",
    "technical_design": "TECHNICAL_DESIGN.md",
    "roadmap": "ROADMAP.md",
    "task_graph": "TASK_GRAPH.yaml",
    "acceptance_contract": "ACCEPTANCE_CONTRACT.yaml",
}
EXPECTED_FAMILY_COUNTS = {
    "V0_1_TASK": 90,
    "V0_1_REQUIREMENT": 20,
    "FRONTEND_V1_1": 9,
    "ACCEPTANCE_7FD": 8,
    "ACCEPTANCE_E1AF": 7,
    "HANDOFF_DECISION": 8,
}
ALLOWED_DISPOSITIONS = {
    "INHERITED_PROVEN",
    "V1_2_ACTIVE",
    "SUPERSEDED_WITH_REASON",
    "OUT_OF_SCOPE_OWNER_DECISION",
    "UNKNOWN_BLOCKED",
}
KNOWN_SECRET_PATTERNS = {
    "private_key": re.compile(rb"-----BEGIN (?:RSA |EC |OPENSSH |DSA )?PRIVATE KEY-----"),
    "github_token": re.compile(rb"\b(?:gh[pousr]_[A-Za-z0-9]{20,}|github_pat_[A-Za-z0-9_]{20,})\b"),
    "openai_key": re.compile(rb"\bsk-(?:proj-)?[A-Za-z0-9_-]{20,}\b"),
    "aws_access_key": re.compile(rb"\b(?:AKIA|ASIA)[A-Z0-9]{16}\b"),
    "bearer": re.compile(rb"(?i)authorization\s*:\s*bearer\s+[A-Za-z0-9._~+/=-]{16,}"),
    "basic_auth_url": re.compile(rb"https?://[^\s/:@]{2,}:[^\s/@]{4,}@"),
}
SECRET_ASSIGNMENT = re.compile(
    rb'''(?ix)\b(password|passwd|secret|token|api[_-]?key|client[_-]?secret|smtp[_-]?(?:password|pass|token))\b\s*[:=]\s*["']?([^\s,"'\]}]{8,})'''
)
PLACEHOLDER = re.compile(
    rb'''(?ix)^(?:<.*>|\$\{?.*\}?|your[_-].*|example|changeme|redacted|masked|none|null|false|true|unknown|not[_-]?set|placeholder|test|dummy|sha256:[0-9a-f]+)$'''
)


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def tree_digest(pack_root: Path) -> str:
    digest = hashlib.sha256()
    for path in sorted(p for p in pack_root.rglob("*") if p.is_file() and p.name != "TREE_SHA256.txt"):
        relative = path.relative_to(pack_root).as_posix()
        digest.update(f"{relative}\0{sha256(path)}\0{path.stat().st_size}\n".encode("utf-8"))
    return digest.hexdigest()


def check_zip_bytes(label: str, raw: bytes, failures: list[str], secret_hits: list[str], depth: int = 0) -> None:
    if depth > 5:
        failures.append(f"{label}: nested ZIP depth exceeds 5")
        return
    try:
        archive = zipfile.ZipFile(io.BytesIO(raw))
    except zipfile.BadZipFile as error:
        failures.append(f"{label}: bad ZIP: {error}")
        return
    with archive:
        exact = set()
        folded = set()
        for info in archive.infolist():
            name = info.filename.replace("\\", "/")
            pure = PurePosixPath(name)
            normalized = pure.as_posix().rstrip("/")
            if (not normalized or pure.is_absolute() or ".." in pure.parts or
                    name.startswith("//") or re.match(r"^[A-Za-z]:/", name)):
                failures.append(f"{label}: unsafe member {info.filename!r}")
                continue
            if normalized in exact or normalized.casefold() in folded:
                failures.append(f"{label}: duplicate/case-colliding member {normalized!r}")
            exact.add(normalized)
            folded.add(normalized.casefold())
            if info.flag_bits & 1:
                failures.append(f"{label}: encrypted member {normalized!r}")
            mode = (info.external_attr >> 16) & 0o170000
            if mode == stat.S_IFLNK:
                failures.append(f"{label}: symlink member {normalized!r}")
            if info.is_dir() or info.file_size > 30_000_000:
                continue
            data = archive.read(info)
            location = f"{label}!{normalized}"
            for kind, pattern in KNOWN_SECRET_PATTERNS.items():
                if pattern.search(data):
                    secret_hits.append(f"{kind}:{location}")
            for match in SECRET_ASSIGNMENT.finditer(data):
                value = match.group(2)
                if PLACEHOLDER.match(value):
                    continue
                if re.fullmatch(rb"[0-9a-f]{32,128}", value, re.I):
                    continue
                if re.fullmatch(rb"[A-Z][A-Z0-9_]{7,}", value):
                    continue
                if any(ch in value for ch in b"(){}[];"):
                    continue
                fingerprint = hashlib.sha256(value).hexdigest()[:12]
                secret_hits.append(f"assignment:{location}:{match.group(1).decode(errors='replace')}:{fingerprint}")
            if normalized.lower().endswith(".zip"):
                check_zip_bytes(location, data, failures, secret_hits, depth + 1)


def validate(repo_root: Path, write_tree: bool) -> list[str]:
    failures: list[str] = []
    pack_root = repo_root / "arxiv-daily-push/docs/pursuing_goal/v1_2"
    if not pack_root.is_dir():
        return [f"missing pack root: {pack_root}"]

    all_files = [p for p in pack_root.rglob("*") if p.is_file()]
    for role, aliases in ROLE_ALIASES.items():
        candidates = [p for p in all_files if p.name.upper() in {a.upper() for a in aliases}]
        expected = pack_root / EXPECTED_ROLES[role]
        if candidates != [expected]:
            failures.append(f"role {role}: expected only {expected.name}, got {[p.relative_to(pack_root).as_posix() for p in candidates]}")

    try:
        manifest = yaml.safe_load((pack_root / "MANIFEST.yaml").read_text(encoding="utf-8"))
        graph = yaml.safe_load((pack_root / "TASK_GRAPH.yaml").read_text(encoding="utf-8"))
        contract = yaml.safe_load((pack_root / "ACCEPTANCE_CONTRACT.yaml").read_text(encoding="utf-8"))
    except Exception as error:
        failures.append(f"cannot parse canonical YAML: {error}")
        return failures
    if manifest.get("taskpack_version") != "1.2.0" or manifest.get("target_product_version") != "1.2.0":
        failures.append("manifest taskpack/target product version must both be 1.2.0")
    version_path = repo_root / "arxiv-daily-push/VERSION"
    if not version_path.is_file() or version_path.read_text(encoding="utf-8").strip() != "0.41.0":
        failures.append("current product VERSION must remain 0.41.0 during S0")

    tasks = graph.get("tasks") or []
    task_ids = [task.get("task_id") for task in tasks]
    if len(task_ids) != 10 or len(set(task_ids)) != 10:
        failures.append(f"task graph must contain 10 unique tasks, got {len(task_ids)}/{len(set(task_ids))}")
    expected_previous = None
    for task in tasks:
        deps = task.get("dependencies") or []
        expected = [] if expected_previous is None else [expected_previous]
        if deps != expected:
            failures.append(f"strict sequence violation for {task.get('task_id')}: {deps} != {expected}")
        for dep in deps:
            if dep not in task_ids:
                failures.append(f"unknown dependency {dep} in {task.get('task_id')}")
        expected_previous = task.get("task_id")

    acceptances = contract.get("acceptances") or []
    acceptance_ids = [item.get("acceptance_id") for item in acceptances]
    if len(acceptance_ids) != 33 or len(set(acceptance_ids)) != 33:
        failures.append(f"acceptance contract must contain 33 unique IDs, got {len(acceptance_ids)}/{len(set(acceptance_ids))}")
    for task in tasks:
        for acceptance_id in task.get("acceptance_ids") or []:
            if acceptance_id not in acceptance_ids:
                failures.append(f"task {task.get('task_id')} references unknown acceptance {acceptance_id}")
    graph_acceptances = {item for task in tasks for item in (task.get("acceptance_ids") or [])}
    if graph_acceptances != set(acceptance_ids):
        failures.append("Task Graph and Acceptance Contract ID sets differ")
    for acceptance in acceptances:
        for task_id in acceptance.get("task_ids") or []:
            if task_id not in task_ids:
                failures.append(f"acceptance {acceptance.get('acceptance_id')} references unknown task {task_id}")
        if not acceptance.get("test_ids") or not acceptance.get("evidence") or not acceptance.get("oracle"):
            failures.append(f"acceptance {acceptance.get('acceptance_id')} lacks test/evidence/oracle")

    trace_path = pack_root / "HISTORICAL_TRACEABILITY.csv"
    if not trace_path.is_file():
        failures.append("missing HISTORICAL_TRACEABILITY.csv")
    else:
        trace_rows = list(csv.DictReader(trace_path.open(encoding="utf-8", newline="")))
        counts = Counter(row["source_family"] for row in trace_rows)
        if dict(counts) != EXPECTED_FAMILY_COUNTS:
            failures.append(f"historical family counts mismatch: {dict(counts)}")
        keys = [(row["source_family"], row["source_id"]) for row in trace_rows]
        if len(keys) != len(set(keys)):
            failures.append("duplicate historical source family/id")
        trace_task_ids: set[str] = set()
        trace_acceptance_ids: set[str] = set()
        for row in trace_rows:
            if row["disposition"] not in ALLOWED_DISPOSITIONS:
                failures.append(f"invalid disposition for {row['source_family']}:{row['source_id']}")
            if row["disposition"] == "UNKNOWN_BLOCKED":
                failures.append(f"decision-incomplete UNKNOWN_BLOCKED row: {row['source_family']}:{row['source_id']}")
            if not all(row.get(field) for field in ("disposition_reason", "current_evidence", "v1_2_task_ids", "v1_2_acceptance_ids", "source_ref")):
                failures.append(f"incomplete trace row: {row['source_family']}:{row['source_id']}")
            for task_id in row["v1_2_task_ids"].split(";"):
                trace_task_ids.add(task_id)
                if task_id not in task_ids:
                    failures.append(f"trace row references unknown task {task_id}")
            for acceptance_id in row["v1_2_acceptance_ids"].split(";"):
                trace_acceptance_ids.add(acceptance_id)
                if acceptance_id not in acceptance_ids:
                    failures.append(f"trace row references unknown acceptance {acceptance_id}")
        if trace_task_ids != set(task_ids):
            failures.append(
                "historical trace task reverse coverage mismatch "
                f"missing={sorted(set(task_ids) - trace_task_ids)} "
                f"extra={sorted(trace_task_ids - set(task_ids))}"
            )
        if trace_acceptance_ids != set(acceptance_ids):
            failures.append(
                "historical trace acceptance reverse coverage mismatch "
                f"missing={sorted(set(acceptance_ids) - trace_acceptance_ids)} "
                f"extra={sorted(trace_acceptance_ids - set(acceptance_ids))}"
            )

    input_manifest_path = pack_root / "INPUT_ARCHIVE_MANIFEST.json"
    try:
        input_manifest = json.loads(input_manifest_path.read_text(encoding="utf-8"))
    except Exception as error:
        failures.append(f"invalid INPUT_ARCHIVE_MANIFEST.json: {error}")
        input_manifest = {"archives": []}
    secret_hits: list[str] = []
    for item in input_manifest.get("archives", []):
        path = repo_root / item["repository_path"]
        if not path.is_file():
            failures.append(f"missing archive input {path}")
            continue
        if path.stat().st_size != item["size"]:
            failures.append(f"archive size mismatch: {item['id']}")
        if sha256(path) != item["sha256"]:
            failures.append(f"archive sha256 mismatch: {item['id']}")
        check_zip_bytes(item["id"], path.read_bytes(), failures, secret_hits)
    if secret_hits:
        failures.extend(f"confirmed credential candidate: {hit}" for hit in secret_hits)

    v01 = repo_root / input_manifest["archives"][0]["repository_path"] if input_manifest.get("archives") else None
    if v01 and v01.is_file() and trace_path.is_file():
        with zipfile.ZipFile(v01) as archive:
            task_member = next(n for n in archive.namelist() if n.endswith("/06_TASK_INDEX.csv"))
            req_member = next(n for n in archive.namelist() if n.endswith("/08_REQUIREMENT_TRACEABILITY_MATRIX.csv"))
            old_tasks = {r["task_id"] for r in csv.DictReader(io.StringIO(archive.read(task_member).decode("utf-8-sig")))}
            old_reqs = {r["requirement_id"] for r in csv.DictReader(io.StringIO(archive.read(req_member).decode("utf-8-sig")))}
        trace_rows = list(csv.DictReader(trace_path.open(encoding="utf-8", newline="")))
        mapped_tasks = {r["source_id"] for r in trace_rows if r["source_family"] == "V0_1_TASK"}
        mapped_reqs = {r["source_id"] for r in trace_rows if r["source_family"] == "V0_1_REQUIREMENT"}
        if old_tasks != mapped_tasks:
            failures.append(f"v0.1 task identity mismatch missing={sorted(old_tasks-mapped_tasks)} extra={sorted(mapped_tasks-old_tasks)}")
        if old_reqs != mapped_reqs:
            failures.append(f"v0.1 requirement identity mismatch missing={sorted(old_reqs-mapped_reqs)} extra={sorted(mapped_reqs-old_reqs)}")

    digest_path = pack_root / "TREE_SHA256.txt"
    current_digest = tree_digest(pack_root)
    if write_tree:
        digest_path.write_text(f"{current_digest}  v1_2-tree-excluding-TREE_SHA256.txt\n", encoding="utf-8")
    elif not digest_path.is_file():
        failures.append("missing TREE_SHA256.txt")
    else:
        recorded = digest_path.read_text(encoding="utf-8").split()[0]
        if recorded != current_digest:
            failures.append(f"tree digest mismatch recorded={recorded} current={current_digest}")

    return failures


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo-root", default=".")
    parser.add_argument("--write-tree-digest", action="store_true")
    args = parser.parse_args()
    failures = validate(Path(args.repo_root).resolve(), args.write_tree_digest)
    if failures:
        print(f"FAIL: {len(failures)} issue(s)")
        for failure in failures:
            print(f"- {failure}")
        return 1
    print("PASS: ADP v1.2 taskpack structure, traceability, archives and digest")
    return 0


if __name__ == "__main__":
    sys.exit(main())
