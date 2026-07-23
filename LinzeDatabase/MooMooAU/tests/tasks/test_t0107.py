from __future__ import annotations

import re
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
STAGE1_TOOLS = PROJECT_ROOT / "machine/stages/S1/tools"
if str(STAGE1_TOOLS) not in sys.path:
    sys.path.insert(0, str(STAGE1_TOOLS))

from validate_stage1 import _validate_workflow  # noqa: E402


def test_t0107_workflow_is_pinned_read_only_and_synthetic() -> None:
    assert _validate_workflow(PROJECT_ROOT) == []
    workflow = (PROJECT_ROOT.parents[1] / ".github/workflows/moomooau-stage1-ci.yml").read_text(
        encoding="utf-8"
    )
    uses = re.findall(r"^\s*uses:\s*([^\s]+)$", workflow, flags=re.MULTILINE)
    assert len(uses) == 3
    assert all(re.fullmatch(r"actions/[A-Za-z0-9_-]+@[0-9a-f]{40}", item) for item in uses)
    lowered = workflow.casefold()
    assert "schedule:" not in lowered
    assert "self-hosted" not in lowered
    assert re.findall(
        r"\$\{\{\s*secrets\.([A-Z0-9_]+)\s*\}\}",
        workflow,
    ) == ["MOOMOOAU_GOVERNANCE_DEPLOY_KEY"]
    assert "ssh-key: ${{ secrets.MOOMOOAU_GOVERNANCE_DEPLOY_KEY }}" in workflow
    assert "pull_request_target" not in lowered
    assert "upload-artifact" not in lowered
    assert "actions/cache" not in lowered


def test_t0107_direct_ci_dependencies_are_exactly_pinned() -> None:
    lines = [
        line.strip()
        for line in (PROJECT_ROOT / "requirements/stage1-ci.txt")
        .read_text(encoding="utf-8")
        .splitlines()
        if line.strip() and not line.startswith("#")
    ]
    assert len(lines) == 9
    assert all(
        "==" in line and not any(token in line for token in (">=", "<=", "~=", "*"))
        for line in lines
    )
