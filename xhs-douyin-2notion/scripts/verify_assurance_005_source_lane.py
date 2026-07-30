#!/usr/bin/env python3
"""Freeze and verify public-safe source-lane evidence for A005.

This verifier is deliberately separate from the immutable Stage 3 Resume
evidence and from the later A005 go-live receipt.  It proves only that the
current public source passed the bounded local software lane; it never reads
an Owner Runtime, opens Chrome, or claims a deployment, capture, or release.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Sequence


PROJECT_ROOT = Path(__file__).resolve().parents[1]
TASK_ID = "TSK.x2n.assurance.005"
CHANGE_EVENT = "CE-X2N-20260729-S06-A005-XHS-TWO-CURRENT-BATCHES"
LEGACY_EVIDENCE = PROJECT_ROOT / "machine/evidence/stage_6/assurance_005/source_lane.json"
EVIDENCE_DIRECTORY = PROJECT_ROOT / "machine/evidence/stage_6/assurance_005/source_lanes"
EXPECTED_GATES = [
    "format",
    "lint",
    "python_compile",
    "typescript_contract",
    "assurance_unit",
    "companion_unit_integration",
    "contract_unit",
    "extension_self_test",
    "sbom_drift",
]
EXPECTED_TOOLCHAIN = {
    "coverage": "7.15.2",
    "node": "24.18.0",
    "npm": "11.16.0",
    "python": "3.12.13",
    "pyyaml": "6.0.3",
    "ruff": "0.15.22",
    "uv": "0.11.28",
}
_SHA256 = re.compile(r"^[0-9a-f]{64}$")
_PLATFORM_CDN = re.compile(
    "|".join(
        re.escape("".join(parts))
        for parts in (
            ("xhs", "cdn"),
            ("douyin", "vod"),
            ("byte", "img"),
            ("bili", "video"),
            ("ks", "cdn"),
            ("sina", "img"),
            ("tb", "cdn"),
            ("ali", "cdn"),
        )
    ),
    re.IGNORECASE,
)


class SourceLaneError(RuntimeError):
    """Raised when the A005 source-only evidence cannot be trusted."""


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise SourceLaneError(message)


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _load_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
        raise SourceLaneError("required source-lane input is unavailable") from error
    _require(isinstance(value, dict), "source-lane input must be an object")
    return value


def _git(arguments: Sequence[str]) -> str:
    result = subprocess.run(
        ["git", "-C", str(PROJECT_ROOT), *arguments],
        stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL,
        check=False,
    )
    _require(result.returncode == 0, "source-lane Git identity is unavailable")
    return result.stdout.decode("utf-8").rstrip("\n")


def _safe_payload(payload: Any) -> None:
    rendered = json.dumps(payload, ensure_ascii=False, sort_keys=True)
    _require("/" + "Users/" not in rendered and "/" + "home/" not in rendered, "local path reached source evidence")
    _require(
        "github" + "_pat_" not in rendered and "Bearer" + " " not in rendered, "credential reached source evidence"
    )
    _require(_PLATFORM_CDN.search(rendered) is None, "platform CDN reached source evidence")


def _source_paths() -> tuple[Path, ...]:
    legacy_evidence_relative = LEGACY_EVIDENCE.relative_to(PROJECT_ROOT).as_posix()
    evidence_directory_relative = EVIDENCE_DIRECTORY.relative_to(PROJECT_ROOT).as_posix()
    tracked = _git(("ls-files", "-z", "--cached", "--others", "--exclude-standard")).split("\0")
    paths: list[Path] = []
    for relative in sorted(
        item
        for item in tracked
        if item and item != legacy_evidence_relative and not item.startswith(f"{evidence_directory_relative}/")
    ):
        path = PROJECT_ROOT / relative
        _require(path.is_file() and not path.is_symlink(), "source manifest contains an unsafe path")
        _require(path.resolve().is_relative_to(PROJECT_ROOT.resolve()), "source manifest escaped the x2n project")
        paths.append(path)
    _require(paths, "source manifest has no project files")
    return tuple(paths)


def _source_manifest() -> dict[str, Any]:
    records: list[bytes] = []
    paths = _source_paths()
    for path in paths:
        relative = path.relative_to(PROJECT_ROOT).as_posix()
        records.append(f"{relative}\0{_sha256(path)}\n".encode("utf-8"))
    return {
        "file_count": len(paths),
        "sha256": hashlib.sha256(b"".join(records)).hexdigest(),
    }


def validate_lane_report(path: Path) -> dict[str, Any]:
    _require(path.is_file() and not path.is_symlink(), "software lane report is unavailable")
    _require(
        path.stat().st_mtime_ns >= max(item.stat().st_mtime_ns for item in _source_paths()),
        "software lane report predates current A005 source",
    )
    report = _load_json(path)
    _require(
        report.get("lane") == "fast"
        and report.get("status") == "PASS"
        and report.get("blocking_repetitions") == 1
        and report.get("blocking_commands") == len(EXPECTED_GATES)
        and report.get("blocking_executions") == len(EXPECTED_GATES)
        and report.get("blocking_failures") == 0
        and report.get("flaky_blocking_tests") == 0
        and report.get("silent_blocking_skips") == 0
        and report.get("explicit_nonblocking_skips") == 0,
        "software lane status/count boundary drifted",
    )
    results = report.get("blocking_results")
    _require(
        isinstance(results, list)
        and [item.get("gate") for item in results] == EXPECTED_GATES
        and [item.get("label") for item in results] == [f"{gate}_r1" for gate in EXPECTED_GATES]
        and all(
            isinstance(item, dict)
            and item.get("blocking") is True
            and item.get("repetition") == 1
            and item.get("status") == "PASS"
            for item in results
        ),
        "software lane gates are incomplete or non-passing",
    )
    _require(
        report.get("platform_calls") == 0
        and report.get("model_calls") == 0
        and report.get("real_accounts") == 0
        and report.get("remote_github_actions") == "NOT_RUN_LOCAL_BASELINE"
        and report.get("stage_gate_evaluation") == "NOT_PERFORMED_BY_SOFTWARE_LANE"
        and report.get("toolchain", {}).get("actual") == EXPECTED_TOOLCHAIN,
        "software lane overstated execution or toolchain drifted",
    )
    return {
        "blocking_executions": len(EXPECTED_GATES),
        "gates": EXPECTED_GATES,
        "report_sha256": _sha256(path),
        "toolchain": EXPECTED_TOOLCHAIN,
    }


def _build_evidence(lane: dict[str, Any]) -> dict[str, Any]:
    evidence = {
        "change_event": CHANGE_EVENT,
        "evidence_kind": "A005_SOURCE_LANE_PRECONDITION",
        "execution": {
            "model_calls": 0,
            "platform_calls": 0,
            "real_accounts": 0,
            "remote_github_actions": "NOT_RUN_LOCAL_BASELINE",
        },
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "release_claim": "SOURCE_LANE_ONLY_NO_OWNER_RUNTIME_CAPTURE_OR_GO_LIVE",
        "schema_version": "1.0",
        "software_lane": lane,
        "source_manifest": _source_manifest(),
        "task_id": TASK_ID,
    }
    _safe_payload(evidence)
    return evidence


def _evidence_path(source_manifest: dict[str, Any]) -> Path:
    digest = source_manifest.get("sha256")
    _require(_SHA256.fullmatch(str(digest)) is not None, "A005 source manifest digest is invalid")
    return EVIDENCE_DIRECTORY / f"{digest}.json"


def _write_evidence(evidence: dict[str, Any]) -> Path:
    source_manifest = evidence.get("source_manifest")
    _require(isinstance(source_manifest, dict), "A005 source manifest is invalid")
    _require(source_manifest == _source_manifest(), "A005 source changed before evidence write")
    evidence_path = _evidence_path(source_manifest)
    if evidence_path.exists() or evidence_path.is_symlink():
        _require(evidence_path.is_file() and not evidence_path.is_symlink(), "A005 source-lane evidence is unsafe")
        _validate_evidence(_load_json(evidence_path), source_manifest=source_manifest, path=evidence_path)
        return evidence_path
    parent = evidence_path.parent
    parent.mkdir(parents=True, exist_ok=True)
    _require(parent.is_dir() and not parent.is_symlink(), "A005 evidence directory is unsafe")
    descriptor = os.open(evidence_path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o644)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            json.dump(evidence, handle, ensure_ascii=False, indent=2, sort_keys=True)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
    except BaseException:
        evidence_path.unlink(missing_ok=True)
        raise
    return evidence_path


def _validate_evidence(evidence: dict[str, Any], *, source_manifest: dict[str, Any], path: Path) -> dict[str, Any]:
    _require(
        set(evidence)
        == {
            "change_event",
            "evidence_kind",
            "execution",
            "generated_at",
            "release_claim",
            "schema_version",
            "software_lane",
            "source_manifest",
            "task_id",
        }
        and evidence.get("schema_version") == "1.0"
        and evidence.get("task_id") == TASK_ID
        and evidence.get("change_event") == CHANGE_EVENT
        and evidence.get("evidence_kind") == "A005_SOURCE_LANE_PRECONDITION"
        and evidence.get("release_claim") == "SOURCE_LANE_ONLY_NO_OWNER_RUNTIME_CAPTURE_OR_GO_LIVE",
        "A005 source-lane evidence identity is invalid",
    )
    generated_at = datetime.fromisoformat(str(evidence.get("generated_at", "")))
    _require(generated_at.tzinfo is not None, "A005 source-lane timestamp is invalid")
    _require(
        evidence.get("execution")
        == {
            "model_calls": 0,
            "platform_calls": 0,
            "real_accounts": 0,
            "remote_github_actions": "NOT_RUN_LOCAL_BASELINE",
        },
        "A005 source-lane evidence claims external execution",
    )
    lane = evidence.get("software_lane")
    _require(
        isinstance(lane, dict)
        and lane.get("blocking_executions") == len(EXPECTED_GATES)
        and lane.get("gates") == EXPECTED_GATES
        and lane.get("toolchain") == EXPECTED_TOOLCHAIN
        and _SHA256.fullmatch(str(lane.get("report_sha256"))) is not None,
        "A005 source-lane software receipt is invalid",
    )
    _require(evidence.get("source_manifest") == source_manifest, "A005 source changed after source-lane evidence")
    _safe_payload(evidence)
    return {
        "evidence_sha256": _sha256(path),
        "source_files": evidence["source_manifest"]["file_count"],
        "status": "PASS_SOURCE_LANE_ONLY",
        "task_id": TASK_ID,
    }


def validate_evidence() -> dict[str, Any]:
    source_manifest = _source_manifest()
    evidence_path = _evidence_path(source_manifest)
    _require(evidence_path.is_file() and not evidence_path.is_symlink(), "A005 source-lane evidence is unavailable")
    return _validate_evidence(_load_json(evidence_path), source_manifest=source_manifest, path=evidence_path)


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Verify public-safe A005 source-lane evidence")
    parser.add_argument("--lane-report", type=Path)
    parser.add_argument("--write-evidence", action="store_true")
    parser.add_argument("--require-evidence", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = _parse_args()
    try:
        _require(not (args.write_evidence and args.require_evidence), "write and require modes are exclusive")
        if args.write_evidence:
            _require(args.lane_report is not None, "writing A005 source evidence requires a lane report")
            _write_evidence(_build_evidence(validate_lane_report(args.lane_report)))
            result = validate_evidence()
        elif args.require_evidence:
            result = validate_evidence()
        else:
            _require(args.lane_report is not None, "a lane report is required")
            result = {
                "source_files": _source_manifest()["file_count"],
                "status": "PASS_SOURCE_LANE_NOT_PERSISTED",
                "task_id": TASK_ID,
                **validate_lane_report(args.lane_report),
            }
    except (OSError, SourceLaneError, UnicodeDecodeError, ValueError):
        print(
            json.dumps({"status": "FAIL_CLOSED", "task_id": TASK_ID}, ensure_ascii=False, sort_keys=True),
            file=sys.stderr,
        )
        return 2
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
