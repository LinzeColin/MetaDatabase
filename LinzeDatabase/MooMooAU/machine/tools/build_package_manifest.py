#!/usr/bin/env python3
"""Build the v1.0.26 protected T0705 pointer-blob recovery repair manifest."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[2]
MANIFEST_PATH = Path("taskpack/PACKAGE_MANIFEST.v1.0.26.json")
PACKAGE_ID = "MMAU-ARCHIVE-TP-2026-07-26-V1.0.26"
PACKAGE_VERSION = "1.0.26"
PREDECESSOR_MANIFEST_PATH = Path("taskpack/PACKAGE_MANIFEST.v1.0.25.json")
PREDECESSOR_MANIFEST_SHA256 = "ea2ff510ccd929aa4b99dfb49ebbc90184f6cfcfc75ede846a167c502face3a9"  # pragma: allowlist secret  # noqa: E501
CONTROL_PREDECESSOR_MANIFEST_PATH = Path("taskpack/PACKAGE_MANIFEST.v1.0.4.json")
CONTROL_PREDECESSOR_MANIFEST_SHA256 = "24b24ce8bd25b85f6c4dce3f7fbf6c8770b24e88be13f52be1d8d6a87b0c6e15"  # pragma: allowlist secret  # noqa: E501
FOUNDATION_PREDECESSOR_MANIFEST_PATH = Path("taskpack/PACKAGE_MANIFEST.v1.0.3.json")
FOUNDATION_PREDECESSOR_MANIFEST_SHA256 = (
    "301fa1c6f5c46760c4aa3a7092bf0be77ca1a2e974e7b65e8b53dcf90db9925e"  # pragma: allowlist secret
)
BASELINE_PREDECESSOR_MANIFEST_PATH = Path("taskpack/PACKAGE_MANIFEST.v1.0.2.json")
BASELINE_PREDECESSOR_MANIFEST_SHA256 = (
    "6767cd11ac260b66df1dd2dec892b73e91a2a6928c4185b1c4ff6446daa6a9b3"  # pragma: allowlist secret
)
LEGACY_MANIFEST_PATH = Path("taskpack/PACKAGE_MANIFEST.v1.0.1.json")
LEGACY_MANIFEST_SHA256 = "c2783bd232062ca123a725a3db2cf26a36c4a99a9476c432c36c850f86675c7f"  # pragma: allowlist secret  # noqa: E501
INHERITED_CONTRACT_HASHES = {
    "machine/contracts/requirements.json": (
        "ea1c5ec0371576b1852cc23d5836eaf21b044a577ee6c6c1a92dddc3923bea27"  # pragma: allowlist secret  # noqa: E501
    ),
    "machine/contracts/acceptance_contract.json": (
        "3115ea47f01549218c817845554dc32b019a894708c4ac311e99249bcabf95bb"  # pragma: allowlist secret  # noqa: E501
    ),
    "machine/contracts/traceability_matrix.csv": (
        "263250bceb42d623c4491b99665dff3d1ba08e78f4e43a4fde74380a5e28abf2"  # pragma: allowlist secret  # noqa: E501
    ),
    "machine/contracts/kill_criteria.json": (
        "2a0494577382d1529721b05c6b03f874787f8c8deb5dbd4a56895624573f25dc"  # pragma: allowlist secret  # noqa: E501
    ),
    "machine/facts/canonical_facts.json": (
        "27110e8e6d8d337474eefa29f51d5bf294061c90dfebac2e0d898268dce96bf2"  # pragma: allowlist secret  # noqa: E501
    ),
    "machine/contracts/task_graph.json": (
        "72785605390a31c8dbb0a5d349cf81418b158f7714e46fe8e7f8e4b113f318d9"  # pragma: allowlist secret  # noqa: E501
    ),
}
ROOT_FILES = [
    ".gitattributes",
    ".gitignore",
    "AGENTS.md",
    "README.md",
    "VERSION",
    "pyproject.toml",
]
PACKAGE_DIRECTORIES = [
    "container",
    "design",
    "evidence",
    "implementation",
    "inventory",
    "machine",
    "operations",
    "prd",
    "release",
    "requirements",
    "research",
    "schemas",
    "security",
    "src/moomooau_archive",
    "taskpack",
    "testing",
    "tests",
    "文档",
]
EXCLUDED_DIRECTORY_NAMES = {
    ".git",
    ".hypothesis",
    ".mypy_cache",
    ".pytest_cache",
    ".ruff_cache",
    "__pycache__",
}
EXCLUDED_FILE_NAMES = {".DS_Store"}


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _verify_inherited_baseline(root: Path) -> None:
    predecessor = root / PREDECESSOR_MANIFEST_PATH
    if (
        not predecessor.is_file()
        or predecessor.is_symlink()
        or _sha256(predecessor) != PREDECESSOR_MANIFEST_SHA256
    ):
        raise ValueError("predecessor v1.0.25 manifest drift")
    control_predecessor = root / CONTROL_PREDECESSOR_MANIFEST_PATH
    if (
        not control_predecessor.is_file()
        or control_predecessor.is_symlink()
        or _sha256(control_predecessor) != CONTROL_PREDECESSOR_MANIFEST_SHA256
    ):
        raise ValueError("control predecessor v1.0.4 manifest drift")
    foundation_predecessor = root / FOUNDATION_PREDECESSOR_MANIFEST_PATH
    if (
        not foundation_predecessor.is_file()
        or foundation_predecessor.is_symlink()
        or _sha256(foundation_predecessor) != FOUNDATION_PREDECESSOR_MANIFEST_SHA256
    ):
        raise ValueError("foundation predecessor v1.0.3 manifest drift")
    baseline_predecessor = root / BASELINE_PREDECESSOR_MANIFEST_PATH
    if (
        not baseline_predecessor.is_file()
        or baseline_predecessor.is_symlink()
        or _sha256(baseline_predecessor) != BASELINE_PREDECESSOR_MANIFEST_SHA256
    ):
        raise ValueError("baseline predecessor v1.0.2 manifest drift")
    legacy = root / LEGACY_MANIFEST_PATH
    if not legacy.is_file() or legacy.is_symlink() or _sha256(legacy) != LEGACY_MANIFEST_SHA256:
        raise ValueError("legacy v1.0.1 manifest drift")
    for relative, expected in INHERITED_CONTRACT_HASHES.items():
        path = root / relative
        if not path.is_file() or path.is_symlink() or _sha256(path) != expected:
            raise ValueError(f"inherited product contract drift: {relative}")


def _include_path(root: Path, path: Path) -> bool:
    relative = path.relative_to(root)
    return (
        relative != MANIFEST_PATH
        and not any(part in EXCLUDED_DIRECTORY_NAMES for part in relative.parts)
        and path.name not in EXCLUDED_FILE_NAMES
        and path.suffix != ".pyc"
    )


def _selected_paths(root: Path) -> list[Path]:
    selected: set[Path] = set()
    for relative in ROOT_FILES:
        path = root / relative
        if not path.is_file() or path.is_symlink():
            raise FileNotFoundError(path)
        selected.add(path)
    for relative in PACKAGE_DIRECTORIES:
        directory = root / relative
        if not directory.is_dir() or directory.is_symlink():
            raise FileNotFoundError(directory)
        for path in directory.rglob("*"):
            if path.is_symlink():
                raise ValueError(f"package scope contains symlink: {path.relative_to(root)}")
            if path.is_file() and _include_path(root, path):
                selected.add(path)
    return sorted(selected, key=lambda path: path.relative_to(root).as_posix())


def build_manifest(root: Path = PROJECT_ROOT) -> dict[str, Any]:
    root = root.resolve()
    _verify_inherited_baseline(root)
    status = json.loads((root / "machine/status/latest.json").read_text(encoding="utf-8"))
    if (
        not isinstance(status, dict)
        or status.get("package_version") != PACKAGE_VERSION
        or "REV-P1-006" not in status.get("resolved_review_findings", [])
        or "RMD-06_LATER_PROTECTED_ACCEPTANCE_PENDING" not in status.get("blockers", [])
        or status.get("overall_status")
        != "PROTECTED_GA_SEVENTH_ATTEMPT_FAILED_POINTER_BLOB_REPAIR_AUTHORIZED"
        or "T0705_POINTER_BLOB_RECOVERY_REPAIR_PENDING" not in status.get("blockers", [])
    ):
        raise ValueError(
            "T0705 protected GA pointer-blob recovery repair is not exactly authorized-pending"
        )
    entries = [
        {
            "path": path.relative_to(root).as_posix(),
            "bytes": path.stat().st_size,
            "sha256": _sha256(path),
        }
        for path in _selected_paths(root)
    ]
    return {
        "schema_version": "moomooau.package-manifest.v26",
        "package_id": PACKAGE_ID,
        "product": "MooMooAU Archive",
        "version": PACKAGE_VERSION,
        "generated_at_utc": status["status_as_of_utc"],
        "authorization": (
            "Stage 7 T0705 only: freeze failed main heads "
            "eb7ad073ecd7e4e6d0d8b5d39126cc95d3d2427f, "
            "e38cd60ed0458cc6ebe7723c26190d17db0bc5f0 and "
            "cc7c8af9a40122a61ee2549fb365df813cbd4f16 and "
            "4c207ad539754166fae6642ff4e6850438d3e2fc and "
            "64d88e910ab4078bf90e9fa4f7ce01ef87cf02b4 and "
            "d10f5086e90aa06f4e6373cb0e44111e1f2c36c7 and "
            "2133673b335a384657c8668b62a1c13055c212cd, and preserve the exact T0702, "
            "T0703 and T0704 protected PASS receipts plus all seven immutable T0705 failed-attempt "
            "ledgers. One reviewed pointer-blob recovery repair delivery, one new exact-main "
            "attempt-1 protected "
            "SCHEDULE_REHEARSAL with rerun zero and one later receipt/schedule-closure delivery "
            "remain authorized. "
            "Reuse only the existing eight-name moomooau-beta protected input "
            "set and installed GitHub App; T0706, final Acceptance and final publication remain "
            "unauthorized."
        ),
        "scope": (
            "Baseline-preserving v1.0.26 T0705 repair candidate: immutable v1.0.1 product "
            "contracts and v1.0.2-v1.0.25 predecessor lineage remain unchanged. All seven failed "
            "GA heads are digest-bound and cannot be rerun or redispatched. The only runtime "
            "change replaces unsafe Contents inline current-pointer decoding with bounded "
            "Contents metadata, exact raw media and canonical Git blob SHA binding before decrypt. "
            "It preserves persisted first-import label replay, "
            "pre-Raw metadata quarantine, "
            "fail-closed second verification, ACTIVE processing and the repaired "
            "paired-empty SAFE_DEFERRED path. "
            "The one remaining exact-main workflow_dispatch must use the production SCHEDULE planner "
            "targeting 04:30 Australia/Sydney, truthfully identify itself as SCHEDULE_REHEARSAL, "
            "refresh live private-repository capacity before Gmail exchange, and retain "
            "verified-only full reads, "
            "Raw and Processed remote recovery before exact-message Trash, one recoverable latest "
            "encrypted Timeline and checkpoint-last CAS. Repair execution, "
            "T0705/S7AC-005 PASS, "
            "T0706, final Acceptance, Stage 7 completion and final publication remain unclaimed."
        ),
        "status_authority": "machine/status/latest.json",
        "predecessor": {
            "path": PREDECESSOR_MANIFEST_PATH.as_posix(),
            "sha256": PREDECESSOR_MANIFEST_SHA256,
            "status": "IMMUTABLE_CONTROL_PREDECESSOR",
        },
        "control_predecessor": {
            "path": CONTROL_PREDECESSOR_MANIFEST_PATH.as_posix(),
            "sha256": CONTROL_PREDECESSOR_MANIFEST_SHA256,
            "status": "IMMUTABLE_CONTROL_PREDECESSOR",
        },
        "foundation_predecessor": {
            "path": FOUNDATION_PREDECESSOR_MANIFEST_PATH.as_posix(),
            "sha256": FOUNDATION_PREDECESSOR_MANIFEST_SHA256,
            "status": "IMMUTABLE_CONTROL_PREDECESSOR",
        },
        "baseline_predecessor": {
            "path": BASELINE_PREDECESSOR_MANIFEST_PATH.as_posix(),
            "sha256": BASELINE_PREDECESSOR_MANIFEST_SHA256,
            "status": "IMMUTABLE_CONTROL_PREDECESSOR",
        },
        "legacy_baseline": {
            "path": LEGACY_MANIFEST_PATH.as_posix(),
            "sha256": LEGACY_MANIFEST_SHA256,
            "status": "IMMUTABLE_HISTORICAL_ARTIFACT",
        },
        "inherited_contract_hashes": INHERITED_CONTRACT_HASHES,
        "file_count_excluding_manifest": len(entries),
        "files": entries,
    }


def _render(manifest: dict[str, Any]) -> str:
    return json.dumps(manifest, ensure_ascii=False, indent=2) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, default=PROJECT_ROOT)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--write", action="store_true")
    mode.add_argument("--check", action="store_true")
    args = parser.parse_args()
    root = args.root.resolve()
    expected = _render(build_manifest(root))
    manifest_path = root / MANIFEST_PATH
    if args.write:
        manifest_path.write_text(expected, encoding="utf-8")
        status = "PASS"
    else:
        status = (
            "PASS"
            if manifest_path.is_file()
            and not manifest_path.is_symlink()
            and manifest_path.read_text(encoding="utf-8") == expected
            else "FAIL"
        )
    print(
        json.dumps(
            {
                "status": status,
                "mode": "write" if args.write else "check",
                "manifest": MANIFEST_PATH.as_posix(),
            },
            sort_keys=True,
        )
    )
    return 0 if status == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
