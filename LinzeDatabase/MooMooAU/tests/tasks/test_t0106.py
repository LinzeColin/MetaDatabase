from __future__ import annotations

import copy
import csv
import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
STAGE1_TOOLS = PROJECT_ROOT / "machine/stages/S1/tools"
if str(STAGE1_TOOLS) not in sys.path:
    sys.path.insert(0, str(STAGE1_TOOLS))

from validate_stage1 import (  # noqa: E402
    _validate_stage1_contracts,
    validate_taskpack_structures,
)


def _load(path: str):
    return json.loads((PROJECT_ROOT / path).read_text(encoding="utf-8"))


def _inputs():
    requirements = _load("machine/contracts/requirements.json")["requirements"]
    acceptances = _load("machine/contracts/acceptance_contract.json")["acceptance_contracts"]
    graph = _load("machine/contracts/task_graph.json")
    with (PROJECT_ROOT / "machine/contracts/traceability_matrix.csv").open(
        encoding="utf-8", newline=""
    ) as stream:
        trace = list(csv.DictReader(stream))
    return requirements, acceptances, graph, trace


def test_t0106_validator_accepts_frozen_graph_and_stage1_overlay() -> None:
    assert validate_taskpack_structures(*_inputs()) == []
    assert _validate_stage1_contracts(PROJECT_ROOT) == []


def test_t0106_validator_rejects_duplicates_cycles_and_trace_gaps() -> None:
    requirements, acceptances, graph, trace = copy.deepcopy(_inputs())
    requirements[1]["id"] = requirements[0]["id"]
    graph["tasks"][0]["dependencies"] = [graph["tasks"][-1]["id"]]
    graph["tasks"][-1]["dependencies"] = [graph["tasks"][0]["id"]]
    trace.pop()
    errors = validate_taskpack_structures(requirements, acceptances, graph, trace)
    assert any("unique" in item for item in errors)
    assert any("cyclic" in item for item in errors)
    assert any("traceability" in item for item in errors)
