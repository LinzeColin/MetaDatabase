from __future__ import annotations

import hashlib
from pathlib import Path

from validate_evidence import validate_record
from validate_package import validate as validate_package
from validate_stage0 import PROJECT_ROOT, evaluate_stage0


def _tree_digest(root: Path) -> dict[str, str]:
    return {
        path.relative_to(root).as_posix(): hashlib.sha256(path.read_bytes()).hexdigest()
        for path in sorted(root.rglob("*"))
        if path.is_file()
        and not path.is_symlink()
        and "__pycache__" not in path.parts
        and ".pytest_cache" not in path.parts
        and path.suffix != ".pyc"
    }


def test_t0001_package_is_exact_and_validator_is_read_only() -> None:
    before = _tree_digest(PROJECT_ROOT)
    package = validate_package(PROJECT_ROOT)
    after = _tree_digest(PROJECT_ROOT)
    result = evaluate_stage0(PROJECT_ROOT)
    checks = {item["id"]: item["status"] for item in result["checks"]}
    assert package["status"] == "PASS"
    assert before == after
    assert checks["source.package_identity"] == "PASS"
    assert checks["source.provenance_integrity"] == "PASS"
    assert checks["package.read_only_manifest"] == "PASS"
    assert validate_record(PROJECT_ROOT / "evidence/tasks/T0001.json") == []
