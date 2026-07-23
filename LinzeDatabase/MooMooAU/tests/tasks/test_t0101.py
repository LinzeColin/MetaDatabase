from __future__ import annotations

import hashlib
from pathlib import Path

from validate_package import validate as validate_package

PROJECT_ROOT = Path(__file__).resolve().parents[2]
REPOSITORY_ROOT = PROJECT_ROOT.parents[1]


def test_t0101_public_package_structure_preserves_frozen_baseline() -> None:
    required = [
        PROJECT_ROOT / "src/moomooau_archive/__init__.py",
        PROJECT_ROOT / "tests/tasks/test_t0101.py",
        PROJECT_ROOT / "machine/stages/S1/contracts/run_contract.json",
        PROJECT_ROOT / "evidence",
        PROJECT_ROOT / "schemas",
        PROJECT_ROOT / "inventory",
        PROJECT_ROOT / "文档",
        REPOSITORY_ROOT / ".github/workflows/moomooau-stage1-ci.yml",
    ]
    assert all(path.exists() for path in required)
    manifest = PROJECT_ROOT / "taskpack/PACKAGE_MANIFEST.v1.0.1.json"
    assert hashlib.sha256(manifest.read_bytes()).hexdigest() == (
        "c2783bd232062ca123a725a3db2cf26a36c4a99a9476c432c36c850f86675c7f"
    )
    assert validate_package(PROJECT_ROOT)["status"] == "PASS"
