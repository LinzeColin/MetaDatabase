#!/usr/bin/env python3
"""Reproduce the frozen full-history license-similarity audit for BSS."""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import subprocess
import sys
import unicodedata
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Any, Iterator, Mapping, Sequence


REPORT_SCHEMA_VERSION = "1.0"
AUDIT_ID = "bss-license-similarity-v1"
AUDIT_DATE = "2026-07-23"
WINDOW_LINES = 4
TOKEN20_THRESHOLD = 20
EVIDENCE_LIMIT_PER_PAIR = 20

SCRIPT = Path(__file__).resolve()
PROJECT_ROOT = SCRIPT.parents[1]
CANONICAL_RELATIVE = PurePosixPath(
    "task-pack/skill_draft/bottleneck-serenity-skill"
)
CANONICAL_ROOT = PROJECT_ROOT.joinpath(*CANONICAL_RELATIVE.parts)
DEFAULT_REPORT = PROJECT_ROOT / "LICENSE_SIMILARITY_AUDIT.json"


class AuditError(RuntimeError):
    """Raised when the audit cannot establish its frozen evidence contract."""


@dataclass(frozen=True)
class UpstreamSpec:
    name: str
    url: str
    commit: str
    license_status: str
    expected_license_paths: tuple[str, ...]


LOCKED_UPSTREAMS: tuple[UpstreamSpec, ...] = (
    UpstreamSpec(
        name="muxuuu/serenity-skill",
        url="https://github.com/muxuuu/serenity-skill",
        commit="c2fe93deedfd0d1bd9fe7ef0601ea1b9c20ea24a",
        license_status="MIT",
        expected_license_paths=("LICENSE",),
    ),
    UpstreamSpec(
        name="yan-labs/serenity-aleabitoreddit",
        url="https://github.com/yan-labs/serenity-aleabitoreddit",
        commit="3fe902b29aa7f32d8ab245c5b87b596cb4d85eb9",
        license_status="NO_LICENSE_FOUND",
        expected_license_paths=(),
    ),
    UpstreamSpec(
        name="Mrjie7205/serenity-bottleneck-hunter",
        url="https://github.com/Mrjie7205/serenity-bottleneck-hunter",
        commit="15bb654f41cb39f442ba2076b4023436a0d7554d",
        license_status="MIT",
        expected_license_paths=("LICENSE",),
    ),
    UpstreamSpec(
        name="wesson9527/chokepoint-atlas",
        url="https://github.com/wesson9527/chokepoint-atlas",
        commit="207bf340a86c0342b28934e578162610accefe73",
        license_status="NO_LICENSE_FOUND",
        expected_license_paths=(),
    ),
)


@dataclass(frozen=True)
class TargetFile:
    path: str
    sha256: str
    byte_count: int
    text: str


def _run_git(repo: Path, *arguments: str, input_text: str | None = None) -> str:
    result = subprocess.run(
        ["git", *arguments],
        cwd=repo,
        input=input_text,
        text=True,
        capture_output=True,
        check=False,
    )
    if result.returncode:
        detail = result.stderr.strip() or result.stdout.strip()
        raise AuditError(f"git {' '.join(arguments)} failed for {repo}: {detail}")
    return result.stdout


def _license_like(path: str) -> bool:
    basename = PurePosixPath(path).name.casefold()
    return basename.startswith("license") or basename.startswith("copying")


def _normalized_origin(value: str) -> str:
    normalized = value.strip().replace("git@github.com:", "https://github.com/")
    normalized = normalized.replace("ssh://git@github.com/", "https://github.com/")
    if normalized.endswith(".git"):
        normalized = normalized[:-4]
    return normalized.rstrip("/").casefold()


def _verify_upstream(spec: UpstreamSpec, repo: Path) -> tuple[list[str], list[str]]:
    if not repo.is_dir():
        raise AuditError(f"upstream path is not a directory: {repo}")
    if _run_git(repo, "rev-parse", "--is-inside-work-tree").strip() != "true":
        raise AuditError(f"upstream path is not a Git worktree: {repo}")
    if _run_git(repo, "rev-parse", "--is-shallow-repository").strip() != "false":
        raise AuditError(f"full history required; shallow repository rejected: {repo}")
    resolved = _run_git(repo, "rev-parse", "--verify", f"{spec.commit}^{{commit}}").strip()
    if resolved != spec.commit:
        raise AuditError(
            f"{spec.name}: frozen commit mismatch: expected {spec.commit}, got {resolved}"
        )
    if spec.url:
        origin = _run_git(repo, "config", "--get", "remote.origin.url").strip()
        if _normalized_origin(origin) != _normalized_origin(spec.url):
            raise AuditError(f"{spec.name}: origin URL does not match frozen repository")

    current_paths = sorted(
        path
        for path in _run_git(repo, "ls-tree", "-r", "--name-only", spec.commit).splitlines()
        if _license_like(path)
    )
    historical_paths = sorted(
        {
            path
            for path in _run_git(
                repo, "log", "--format=", "--name-only", spec.commit
            ).splitlines()
            if path and _license_like(path)
        }
    )
    expected = list(spec.expected_license_paths)
    if current_paths != expected or historical_paths != expected:
        raise AuditError(
            f"{spec.name}: license path drift: current={current_paths}, "
            f"history={historical_paths}, expected={expected}"
        )
    if spec.license_status == "MIT":
        for path in expected:
            payload = _run_git(repo, "show", f"{spec.commit}:{path}")
            if "MIT License" not in payload or "Permission is hereby granted" not in payload:
                raise AuditError(f"{spec.name}: {path} does not contain the expected MIT notice")
    elif spec.license_status == "NO_LICENSE_FOUND":
        if expected:
            raise AuditError(f"{spec.name}: unlicensed classification has license paths")
    else:
        raise AuditError(f"{spec.name}: unsupported license status {spec.license_status}")
    return current_paths, historical_paths


def _reachable_blob_ids(repo: Path, commit: str) -> list[str]:
    object_ids = sorted(
        {
            line.split(" ", 1)[0]
            for line in _run_git(repo, "rev-list", "--objects", commit).splitlines()
            if line
        }
    )
    checked = _run_git(
        repo,
        "cat-file",
        "--batch-check=%(objectname) %(objecttype)",
        input_text="".join(f"{oid}\n" for oid in object_ids),
    )
    blobs: list[str] = []
    for line in checked.splitlines():
        fields = line.split()
        if len(fields) != 2:
            raise AuditError(f"unexpected git cat-file batch-check row: {line!r}")
        if fields[1] == "blob":
            blobs.append(fields[0])
    return sorted(set(blobs))


def _read_exact(stream: Any, size: int) -> bytes:
    chunks: list[bytes] = []
    remaining = size
    while remaining:
        chunk = stream.read(remaining)
        if not chunk:
            raise AuditError("unexpected EOF while reading Git blob payload")
        chunks.append(chunk)
        remaining -= len(chunk)
    return b"".join(chunks)


def _blob_payloads(repo: Path, object_ids: Sequence[str]) -> Iterator[tuple[str, bytes]]:
    process = subprocess.Popen(
        ["git", "cat-file", "--batch"],
        cwd=repo,
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    if process.stdin is None or process.stdout is None or process.stderr is None:
        process.kill()
        raise AuditError("could not open git cat-file batch streams")
    try:
        for requested in object_ids:
            process.stdin.write(requested.encode("ascii") + b"\n")
            process.stdin.flush()
            header = process.stdout.readline().decode("ascii", errors="strict").strip()
            fields = header.split()
            if len(fields) != 3 or fields[0] != requested or fields[1] != "blob":
                raise AuditError(f"unexpected git cat-file header: {header!r}")
            try:
                size = int(fields[2])
            except ValueError as exc:
                raise AuditError(f"invalid Git blob size in header: {header!r}") from exc
            payload = _read_exact(process.stdout, size)
            if process.stdout.read(1) != b"\n":
                raise AuditError("Git blob payload missing batch separator")
            yield requested, payload
        process.stdin.close()
        return_code = process.wait()
        if return_code:
            raise AuditError(
                f"git cat-file --batch failed: {process.stderr.read().decode('utf-8', 'replace')}"
            )
    finally:
        if not process.stdin.closed:
            process.stdin.close()
        if process.poll() is None:
            process.kill()
            process.wait()
        process.stdout.close()
        process.stderr.close()


def _normalize_line(line: str) -> str:
    normalized = unicodedata.normalize("NFC", line)
    return re.sub(r"\s+", " ", normalized.strip(), flags=re.UNICODE)


def _windows(text: str) -> Iterator[tuple[int, tuple[str, ...]]]:
    lines = [_normalize_line(line) for line in text.splitlines()]
    for index in range(max(0, len(lines) - WINDOW_LINES + 1)):
        window = tuple(lines[index : index + WINDOW_LINES])
        if all(window):
            yield index + 1, window


def _window_sha256(window: Sequence[str]) -> str:
    payload = json.dumps(
        list(window), ensure_ascii=False, separators=(",", ":")
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def _ascii_alnum_token_count(window: Sequence[str]) -> int:
    return len(re.findall(r"[A-Za-z0-9]+", "\n".join(window), flags=re.ASCII))


def collect_targets(root: Path) -> list[TargetFile]:
    if root.is_symlink() or not root.is_dir():
        raise AuditError(f"canonical target root must be a real directory: {root}")
    targets: list[TargetFile] = []
    for path in sorted(
        root.rglob("*"), key=lambda item: item.relative_to(root).as_posix().encode("utf-8")
    ):
        if path.is_symlink():
            raise AuditError(f"canonical target symlink rejected: {path}")
        if not path.is_file():
            continue
        payload = path.read_bytes()
        if b"\x00" in payload:
            raise AuditError(f"canonical target contains NUL and is not eligible text: {path}")
        try:
            text = payload.decode("utf-8")
        except UnicodeDecodeError as exc:
            raise AuditError(f"canonical target is not strict UTF-8: {path}") from exc
        targets.append(
            TargetFile(
                path=path.relative_to(root).as_posix(),
                sha256=hashlib.sha256(payload).hexdigest(),
                byte_count=len(payload),
                text=text,
            )
        )
    if not targets:
        raise AuditError("canonical target file set is empty")
    return targets


def algorithm_contract() -> dict[str, Any]:
    return {
        "history_scope": (
            "each unique Git blob reachable from the frozen commit, including all ancestors; "
            "no size or path exclusion"
        ),
        "target_scope": (
            "every regular file recursively present in the canonical Skill root; symlinks, "
            "non-UTF-8, or NUL-bearing target files fail the audit"
        ),
        "text_blob_eligibility": "strict UTF-8 decode succeeds and raw payload contains no NUL byte",
        "exact_match": "SHA-256 equality of complete raw payload bytes",
        "line_split": "Python str.splitlines physical lines",
        "line_normalization": (
            "Unicode NFC, strip leading/trailing Unicode whitespace, then collapse each "
            "Unicode whitespace run to one ASCII space"
        ),
        "window": "four physically contiguous normalized lines, all four non-empty",
        "pair_identity": "canonical target relative path + upstream repository name + Git blob OID",
        "pair_count": "one per unique pair identity with at least one matching window",
        "token20_candidate": (
            "a normalized-window pair with at least one matching window containing 20 or more "
            "ASCII [A-Za-z0-9]+ tokens; this is a review candidate, not a legal conclusion"
        ),
        "window_lines": WINDOW_LINES,
        "token20_threshold": TOKEN20_THRESHOLD,
        "evidence_limit_per_pair": EVIDENCE_LIMIT_PER_PAIR,
        "evidence_payload": "line starts, normalized-window SHA-256, and token count; no upstream text",
    }


def _target_indexes(
    targets: Sequence[TargetFile],
) -> tuple[dict[str, list[str]], dict[tuple[str, ...], list[tuple[str, int]]]]:
    sha_index: dict[str, list[str]] = {}
    window_index: dict[tuple[str, ...], list[tuple[str, int]]] = {}
    for target in targets:
        sha_index.setdefault(target.sha256, []).append(target.path)
        for line_start, window in _windows(target.text):
            window_index.setdefault(window, []).append((target.path, line_start))
    for values in sha_index.values():
        values.sort()
    for values in window_index.values():
        values.sort()
    return sha_index, window_index


def scan_upstream(
    spec: UpstreamSpec,
    repo: Path,
    target_sha_index: Mapping[str, Sequence[str]],
    target_window_index: Mapping[tuple[str, ...], Sequence[tuple[str, int]]],
) -> dict[str, Any]:
    current_licenses, historical_licenses = _verify_upstream(spec, repo)
    blob_ids = _reachable_blob_ids(repo, spec.commit)
    eligible_count = 0
    eligible_bytes = 0
    nul_rejected = 0
    non_utf8_rejected = 0
    exact_pairs: list[dict[str, Any]] = []
    normalized_pairs: dict[tuple[str, str], dict[str, Any]] = {}

    for oid, payload in _blob_payloads(repo, blob_ids):
        if b"\x00" in payload:
            nul_rejected += 1
            continue
        try:
            text = payload.decode("utf-8")
        except UnicodeDecodeError:
            non_utf8_rejected += 1
            continue
        eligible_count += 1
        eligible_bytes += len(payload)
        payload_sha = hashlib.sha256(payload).hexdigest()
        for target_path in target_sha_index.get(payload_sha, ()):
            exact_pairs.append(
                {
                    "target_path": target_path,
                    "upstream": spec.name,
                    "blob_oid": oid,
                    "payload_sha256": payload_sha,
                }
            )

        for upstream_line, window in _windows(text):
            target_occurrences = target_window_index.get(window)
            if not target_occurrences:
                continue
            window_sha = _window_sha256(window)
            token_count = _ascii_alnum_token_count(window)
            for target_path, target_line in target_occurrences:
                key = (target_path, oid)
                pair = normalized_pairs.setdefault(
                    key,
                    {
                        "target_path": target_path,
                        "upstream": spec.name,
                        "blob_oid": oid,
                        "matching_window_count": 0,
                        "token20_matching_window_count": 0,
                        "window_evidence": [],
                    },
                )
                pair["matching_window_count"] += 1
                if token_count >= TOKEN20_THRESHOLD:
                    pair["token20_matching_window_count"] += 1
                if len(pair["window_evidence"]) < EVIDENCE_LIMIT_PER_PAIR:
                    pair["window_evidence"].append(
                        {
                            "target_line_start": target_line,
                            "upstream_line_start": upstream_line,
                            "normalized_window_sha256": window_sha,
                            "ascii_alnum_token_count": token_count,
                        }
                    )

    normalized = []
    for key in sorted(normalized_pairs):
        pair = normalized_pairs[key]
        pair["window_evidence_truncated"] = (
            pair["matching_window_count"] > len(pair["window_evidence"])
        )
        normalized.append(pair)
    exact_pairs.sort(key=lambda item: (item["target_path"], item["blob_oid"]))
    return {
        "upstream": {
            "name": spec.name,
            "url": spec.url,
            "commit": spec.commit,
            "license_status": spec.license_status,
            "license_paths_in_frozen_tree": current_licenses,
            "license_paths_ever_in_reachable_history": historical_licenses,
            "reachable_unique_blob_count": len(blob_ids),
            "eligible_text_blob_count": eligible_count,
            "eligible_text_blob_bytes": eligible_bytes,
            "nul_rejected_blob_count": nul_rejected,
            "non_utf8_rejected_blob_count": non_utf8_rejected,
        },
        "exact_pairs": exact_pairs,
        "normalized_pairs": normalized,
    }


def build_report(
    target_root: Path,
    specs: Sequence[UpstreamSpec],
    upstream_paths: Mapping[str, Path],
    *,
    target_label: str,
) -> dict[str, Any]:
    expected_names = [spec.name for spec in specs]
    if sorted(upstream_paths) != sorted(expected_names):
        raise AuditError(
            f"upstream set mismatch: expected {expected_names}, got {sorted(upstream_paths)}"
        )
    targets = collect_targets(target_root)
    sha_index, window_index = _target_indexes(targets)
    scans = [
        scan_upstream(spec, upstream_paths[spec.name], sha_index, window_index)
        for spec in specs
    ]
    upstreams = [scan["upstream"] for scan in scans]
    exact_pairs = sorted(
        (pair for scan in scans for pair in scan["exact_pairs"]),
        key=lambda item: (item["target_path"], item["upstream"], item["blob_oid"]),
    )
    normalized_pairs = sorted(
        (pair for scan in scans for pair in scan["normalized_pairs"]),
        key=lambda item: (item["target_path"], item["upstream"], item["blob_oid"]),
    )
    token20_pairs = [
        pair for pair in normalized_pairs if pair["token20_matching_window_count"] > 0
    ]
    unlicensed_names = {
        spec.name for spec in specs if spec.license_status == "NO_LICENSE_FOUND"
    }
    return {
        "report_schema_version": REPORT_SCHEMA_VERSION,
        "audit_id": AUDIT_ID,
        "audit_date": AUDIT_DATE,
        "algorithm": algorithm_contract(),
        "target": {
            "root": target_label,
            "file_count": len(targets),
            "files": [
                {
                    "path": target.path,
                    "sha256": target.sha256,
                    "byte_count": target.byte_count,
                }
                for target in targets
            ],
        },
        "upstreams": upstreams,
        "summary": {
            "target_file_count": len(targets),
            "upstream_repository_count": len(upstreams),
            "upstream_reachable_unique_blob_instances": sum(
                item["reachable_unique_blob_count"] for item in upstreams
            ),
            "upstream_eligible_text_blob_instances": sum(
                item["eligible_text_blob_count"] for item in upstreams
            ),
            "exact_pair_count": len(exact_pairs),
            "normalized_four_line_pair_count": len(normalized_pairs),
            "token20_pair_count": len(token20_pairs),
            "unlicensed_exact_pair_count": sum(
                pair["upstream"] in unlicensed_names for pair in exact_pairs
            ),
            "unlicensed_normalized_four_line_pair_count": sum(
                pair["upstream"] in unlicensed_names for pair in normalized_pairs
            ),
            "unlicensed_token20_pair_count": sum(
                pair["upstream"] in unlicensed_names for pair in token20_pairs
            ),
        },
        "exact_pairs": exact_pairs,
        "normalized_four_line_pairs": normalized_pairs,
    }


def _spec_projection(spec: UpstreamSpec) -> dict[str, Any]:
    return {
        "name": spec.name,
        "url": spec.url,
        "commit": spec.commit,
        "license_status": spec.license_status,
        "license_paths_in_frozen_tree": list(spec.expected_license_paths),
        "license_paths_ever_in_reachable_history": list(spec.expected_license_paths),
    }


def validate_report_targets(
    report: Mapping[str, Any],
    target_root: Path,
    *,
    target_label: str,
    specs: Sequence[UpstreamSpec] = LOCKED_UPSTREAMS,
) -> None:
    if report.get("report_schema_version") != REPORT_SCHEMA_VERSION:
        raise AuditError("report schema version drift")
    if report.get("audit_id") != AUDIT_ID or report.get("audit_date") != AUDIT_DATE:
        raise AuditError("report identity/date drift")
    if report.get("algorithm") != algorithm_contract():
        raise AuditError("report algorithm contract drift")
    target = report.get("target")
    if not isinstance(target, Mapping) or target.get("root") != target_label:
        raise AuditError("report target root drift")
    actual = collect_targets(target_root)
    expected_files = [
        {"path": item.path, "sha256": item.sha256, "byte_count": item.byte_count}
        for item in actual
    ]
    if target.get("file_count") != len(actual) or target.get("files") != expected_files:
        raise AuditError("report target file set/hash/size drift")

    upstreams = report.get("upstreams")
    if not isinstance(upstreams, list) or len(upstreams) != len(specs):
        raise AuditError("report upstream set drift")
    for actual_item, spec in zip(upstreams, specs):
        if not isinstance(actual_item, Mapping):
            raise AuditError("report upstream row must be an object")
        projection = _spec_projection(spec)
        if {key: actual_item.get(key) for key in projection} != projection:
            raise AuditError(f"report frozen upstream metadata drift: {spec.name}")
        counts = (
            actual_item.get("reachable_unique_blob_count"),
            actual_item.get("eligible_text_blob_count"),
            actual_item.get("nul_rejected_blob_count"),
            actual_item.get("non_utf8_rejected_blob_count"),
        )
        if any(isinstance(value, bool) or not isinstance(value, int) or value < 0 for value in counts):
            raise AuditError(f"report invalid upstream blob counts: {spec.name}")
        reachable, eligible, nul_rejected, non_utf8_rejected = counts
        if reachable != eligible + nul_rejected + non_utf8_rejected:
            raise AuditError(f"report upstream eligibility counts do not balance: {spec.name}")

    exact_pairs = report.get("exact_pairs")
    normalized_pairs = report.get("normalized_four_line_pairs")
    summary = report.get("summary")
    if not isinstance(exact_pairs, list) or not isinstance(normalized_pairs, list):
        raise AuditError("report pair collections must be arrays")
    if not isinstance(summary, Mapping):
        raise AuditError("report summary must be an object")

    target_paths = {item.path for item in actual}
    upstream_names = {spec.name for spec in specs}
    unlicensed_names = {
        spec.name for spec in specs if spec.license_status == "NO_LICENSE_FOUND"
    }

    def pair_identity(pair: Any, *, normalized: bool) -> tuple[str, str, str]:
        if not isinstance(pair, Mapping):
            raise AuditError("report pair row must be an object")
        target_path = pair.get("target_path")
        upstream = pair.get("upstream")
        blob_oid = pair.get("blob_oid")
        if (
            not isinstance(target_path, str)
            or not isinstance(upstream, str)
            or target_path not in target_paths
            or upstream not in upstream_names
        ):
            raise AuditError("report pair references unknown target or upstream")
        if not isinstance(blob_oid, str) or re.fullmatch(r"[0-9a-f]{40,64}", blob_oid) is None:
            raise AuditError("report pair has invalid Git blob OID")
        if normalized:
            matching = pair.get("matching_window_count")
            token20 = pair.get("token20_matching_window_count")
            evidence = pair.get("window_evidence")
            if (
                isinstance(matching, bool)
                or not isinstance(matching, int)
                or matching < 1
                or isinstance(token20, bool)
                or not isinstance(token20, int)
                or not 0 <= token20 <= matching
                or not isinstance(evidence, list)
                or len(evidence) > EVIDENCE_LIMIT_PER_PAIR
                or pair.get("window_evidence_truncated") != (matching > len(evidence))
            ):
                raise AuditError("report normalized pair count/evidence drift")
            for item in evidence:
                if not isinstance(item, Mapping):
                    raise AuditError("report window evidence must be an object")
                line_values = (
                    item.get("target_line_start"),
                    item.get("upstream_line_start"),
                    item.get("ascii_alnum_token_count"),
                )
                if any(
                    isinstance(value, bool) or not isinstance(value, int) or value < 0
                    for value in line_values
                ) or line_values[0] < 1 or line_values[1] < 1:
                    raise AuditError("report window evidence line/token count drift")
                window_sha = item.get("normalized_window_sha256")
                if not isinstance(window_sha, str) or re.fullmatch(
                    r"[0-9a-f]{64}", window_sha
                ) is None:
                    raise AuditError("report window evidence SHA-256 drift")
        else:
            payload_sha = pair.get("payload_sha256")
            if not isinstance(payload_sha, str) or re.fullmatch(
                r"[0-9a-f]{64}", payload_sha
            ) is None:
                raise AuditError("report exact pair SHA-256 drift")
        return target_path, upstream, blob_oid

    exact_identities = [pair_identity(pair, normalized=False) for pair in exact_pairs]
    normalized_identities = [
        pair_identity(pair, normalized=True) for pair in normalized_pairs
    ]
    if len(exact_identities) != len(set(exact_identities)):
        raise AuditError("report contains duplicate exact pair identity")
    if len(normalized_identities) != len(set(normalized_identities)):
        raise AuditError("report contains duplicate normalized pair identity")
    token20_count = sum(
        isinstance(pair, Mapping)
        and isinstance(pair.get("token20_matching_window_count"), int)
        and pair["token20_matching_window_count"] > 0
        for pair in normalized_pairs
    )
    expected_summary = {
        "target_file_count": len(actual),
        "upstream_repository_count": len(upstreams),
        "upstream_reachable_unique_blob_instances": sum(
            item["reachable_unique_blob_count"] for item in upstreams
        ),
        "upstream_eligible_text_blob_instances": sum(
            item["eligible_text_blob_count"] for item in upstreams
        ),
        "exact_pair_count": len(exact_pairs),
        "normalized_four_line_pair_count": len(normalized_pairs),
        "token20_pair_count": token20_count,
        "unlicensed_exact_pair_count": sum(
            pair["upstream"] in unlicensed_names for pair in exact_pairs
        ),
        "unlicensed_normalized_four_line_pair_count": sum(
            pair["upstream"] in unlicensed_names for pair in normalized_pairs
        ),
        "unlicensed_token20_pair_count": sum(
            pair["upstream"] in unlicensed_names
            and pair["token20_matching_window_count"] > 0
            for pair in normalized_pairs
        ),
    }
    if {key: summary.get(key) for key in expected_summary} != expected_summary:
        raise AuditError("report summary count drift")


def serialize_report(report: Mapping[str, Any]) -> bytes:
    return (
        json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    ).encode("utf-8")


def load_report(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise AuditError(f"cannot read audit report {path}: {exc}") from exc
    if not isinstance(value, dict):
        raise AuditError("audit report root must be an object")
    return value


def _parse_upstream_arguments(values: Sequence[str]) -> dict[str, Path]:
    parsed: dict[str, Path] = {}
    for value in values:
        name, separator, raw_path = value.partition("=")
        if not separator or not name or not raw_path:
            raise AuditError("--upstream must use NAME=PATH")
        if name in parsed:
            raise AuditError(f"duplicate --upstream name: {name}")
        parsed[name] = Path(raw_path).resolve()
    return parsed


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--upstream",
        action="append",
        default=[],
        metavar="NAME=PATH",
        help="full local clone for one frozen upstream; repeat exactly four times",
    )
    parser.add_argument("--output", type=Path, default=DEFAULT_REPORT)
    modes = parser.add_mutually_exclusive_group()
    modes.add_argument(
        "--verify-targets",
        action="store_true",
        help="verify committed report metadata and all current canonical target hashes",
    )
    modes.add_argument(
        "--verify-report",
        action="store_true",
        help="recompute from four full clones and require byte-identical committed report",
    )
    args = parser.parse_args()
    try:
        if args.verify_targets:
            if args.upstream:
                raise AuditError("--verify-targets does not accept --upstream")
            report = load_report(args.output)
            validate_report_targets(
                report, CANONICAL_ROOT, target_label=CANONICAL_RELATIVE.as_posix()
            )
            print(
                f"PASS: {args.output}; canonical targets={report['target']['file_count']}"
            )
            return

        upstream_paths = _parse_upstream_arguments(args.upstream)
        report = build_report(
            CANONICAL_ROOT,
            LOCKED_UPSTREAMS,
            upstream_paths,
            target_label=CANONICAL_RELATIVE.as_posix(),
        )
        payload = serialize_report(report)
        if args.verify_report:
            if not args.output.is_file():
                raise AuditError(f"committed report missing: {args.output}")
            if args.output.read_bytes() != payload:
                raise AuditError("recomputed audit report differs from committed report")
            print(
                f"PASS: recomputed report is byte-identical; "
                f"targets={report['summary']['target_file_count']}; "
                f"text_blobs={report['summary']['upstream_eligible_text_blob_instances']}"
            )
            return
        args.output.write_bytes(payload)
        print(
            f"PASS: wrote {args.output}; targets={report['summary']['target_file_count']}; "
            f"text_blobs={report['summary']['upstream_eligible_text_blob_instances']}; "
            f"exact={report['summary']['exact_pair_count']}; "
            f"four_line={report['summary']['normalized_four_line_pair_count']}; "
            f"token20={report['summary']['token20_pair_count']}"
        )
    except AuditError as exc:
        print(f"FAIL: {exc}", file=sys.stderr)
        raise SystemExit(1) from exc


if __name__ == "__main__":
    main()
