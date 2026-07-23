from __future__ import annotations

import sys
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[2]
STAGE2_TOOLS = PROJECT_ROOT / "machine/stages/S2/tools"
if str(STAGE2_TOOLS) not in sys.path:
    sys.path.insert(0, str(STAGE2_TOOLS))

from validate_supply_chain import (  # noqa: E402
    EXPECTED_LOCK_PACKAGE_COUNT,
    WORKFLOW_PATH,
    requirement_versions,
    validate_supply_chain,
)


def test_t0207_hash_lock_sbom_actions_age_and_container_are_immutable() -> None:
    assert validate_supply_chain(PROJECT_ROOT, WORKFLOW_PATH) == []
    lock = (PROJECT_ROOT / "requirements/stage2.lock").read_text(encoding="utf-8")
    versions = requirement_versions(lock)
    assert len(versions) == EXPECTED_LOCK_PACKAGE_COUNT
    assert versions["cryptography"] == "49.0.0"
    assert versions["pikepdf"] == "10.10.0"
    assert versions["pip-audit"] == "2.10.1"


def test_t0207_unhashed_or_nonexact_dependency_is_rejected() -> None:
    with pytest.raises(ValueError, match="non-exact"):
        requirement_versions("unsafe-package>=1.0\n")
    unhashed = "unsafe-package==1.0 " + chr(92) + "\n    # no integrity material\n"
    with pytest.raises(ValueError, match="no SHA-256"):
        requirement_versions(unhashed)
