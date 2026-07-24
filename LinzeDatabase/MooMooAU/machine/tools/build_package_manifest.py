#!/usr/bin/env python3
"""Build the v1.0.14 T0703 historical-label zero-write reconciliation manifest."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[2]
MANIFEST_PATH = Path("taskpack/PACKAGE_MANIFEST.v1.0.14.json")
PACKAGE_ID = "MMAU-ARCHIVE-TP-2026-07-24-V1.0.14"
PACKAGE_VERSION = "1.0.14"
PREDECESSOR_MANIFEST_PATH = Path("taskpack/PACKAGE_MANIFEST.v1.0.13.json")
PREDECESSOR_MANIFEST_SHA256 = "63a9d3f90fd420c8b661e7617793df0c748eece68c9363a11115d4b0d264fa1e"  # pragma: allowlist secret  # noqa: E501
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
        raise ValueError("predecessor v1.0.13 manifest drift")
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
        or "RMD-06_PROTECTED_ACCEPTANCE_PENDING" not in status.get("blockers", [])
        or "T0703_REPAIR_CANDIDATE_PENDING" not in status.get("blockers", [])
    ):
        raise ValueError("T0703 repair candidate is not in the exact authorized pre-run state")
    entries = [
        {
            "path": path.relative_to(root).as_posix(),
            "bytes": path.stat().st_size,
            "sha256": _sha256(path),
        }
        for path in _selected_paths(root)
    ]
    return {
        "schema_version": "moomooau.package-manifest.v13",
        "package_id": PACKAGE_ID,
        "product": "MooMooAU Archive",
        "version": PACKAGE_VERSION,
        "generated_at_utc": status["status_as_of_utc"],
        "authorization": (
            "Stage 7 T0703 only: preserve the protected T0702 PASS and all six failed M3 "
            "attempts. The fifth reached closed MUTATION_FAILED after Raw and Processed recovery; "
            "the sixth stopped at PROCESSED_PLAN with independently verified zero new effect. "
            "One controlled main delivery and one attempt-1 historical-label zero-new-write "
            "reconciliation are authorized. Every failed-head rerun or redispatch, final "
            "publication and T0704 remain forbidden."
        ),
        "scope": (
            "Baseline-preserving v1.0.14 reconciliation snapshot: immutable v1.0.1 product "
            "contracts and v1.0.2-v1.0.13 predecessor lineage; the exact T0702 protected PASS "
            "receipt remains unchanged. The first four T0703 attempts retain zero observed "
            "effects. The fifth is truthfully bound as MUTATION_FAILED with one recovered "
            "Processed lineage, processed-current ZERO-to-ONE and Gmail Trash aggregate plus one, "
            "while exact-source attribution and the mutation subreason remain unclaimed. The sixth "
            "recovered Raw then stopped at PROCESSED_PLAN with no new remote or Gmail effect. The "
            "candidate restores canonical historical Gmail label state only from the existing "
            "encrypted Processed envelope, selects the sole verified Trash source backed by the "
            "pointer, repeats Raw and Processed recovery and second verification, and has no Gmail "
            "or private-repository write path. At package-build time reconciliation has not run; "
            "Timeline, T0704, production health, final Acceptance, Stage 7 completion and final "
            "publication are not claimed."
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
