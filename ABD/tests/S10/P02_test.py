from __future__ import annotations

import ast
from copy import deepcopy
from decimal import Decimal
import json
from pathlib import Path
import shutil

import pytest

from abd_acceptance.uncertainty import (
    UncertaintyAcceptanceError,
    evaluate_contract,
    perform_rollback_drill,
    validate_candidate_preflight,
    verify_existing_phase_evidence,
    write_phase_evidence,
)
from uncertainty import (
    BootstrapBlock,
    UncertaintyError,
    block_bootstrap_samples,
    build_manifest,
    conservative_probability,
    manifest_sha256,
    percentile,
    validate_fixture,
)


ROOT = Path(__file__).resolve().parents[2]
FIXTURE = json.loads((ROOT / "machine/tests/fixtures/S10_P02.json").read_text(encoding="utf-8"))
PARAMETERS = json.loads((ROOT / "machine/facts/parameters.json").read_text(encoding="utf-8"))


def _clone_project(tmp_path: Path) -> Path:
    clone = tmp_path / "ABD"
    shutil.copytree(ROOT, clone, ignore=shutil.ignore_patterns(".git", ".pytest_cache", "__pycache__", ".venv"))
    return clone


def test_candidate_preflight_passes_without_generated_test_reports() -> None:
    result = validate_candidate_preflight(ROOT)
    assert result["status"] == "PASS", result
    assert result["contract_id"] == "AC-S10-P02"
    assert result["next"] == "S10/P03_READY_NOT_STARTED"
    assert result["summary"]["checks"] >= 30
    assert result["external_effect_boundary"]["real_time_soak_waited"] is False
    assert result["external_effect_boundary"]["incremental_cash_spent_aud"] == "0.00"


def test_frozen_manifest_is_exact_replay_with_required_counts() -> None:
    manifest = build_manifest(FIXTURE, PARAMETERS)
    assert manifest_sha256(manifest) == FIXTURE["expected_manifest_sha256"]
    assert manifest["parameters"] == {
        "runtime_block_bootstrap_iterations": 1000,
        "evaluation_block_bootstrap_iterations": 2000,
        "conservative_probability_percentile": 10,
    }
    assert manifest["runtime"]["iterations"] == 1000
    assert manifest["evaluation"]["iterations"] == 2000
    assert manifest["runtime"]["percentile"] == manifest["evaluation"]["percentile"] == 10
    assert Decimal(manifest["conservative_probability"]) <= Decimal(manifest["base_probability"])
    assert manifest["decision"] == "CONSERVATIVE_PROBABILITY_READY_DOWNSTREAM_DECIMAL_GATE_REQUIRED"


def test_block_bootstrap_distribution_is_non_degenerate_and_fixed_seed_replayable() -> None:
    validated = validate_fixture(FIXTURE, PARAMETERS)
    first = block_bootstrap_samples(
        validated["base_probability"],
        validated["blocks"],
        iterations=1000,
        seed=validated["runtime_seed"],
    )
    second = block_bootstrap_samples(
        validated["base_probability"],
        validated["blocks"],
        iterations=1000,
        seed=validated["runtime_seed"],
    )
    assert first == second
    assert len(first) == 1000
    assert min(first) < max(first)


def test_runtime_and_evaluation_use_distinct_seeded_distributions() -> None:
    manifest = build_manifest(FIXTURE, PARAMETERS)
    assert manifest["runtime"]["seed"] != manifest["evaluation"]["seed"]
    assert manifest["runtime"]["sample_sha256"] != manifest["evaluation"]["sample_sha256"]
    assert manifest["runtime"]["minimum_probability"] != manifest["runtime"]["maximum_probability"]
    assert manifest["evaluation"]["minimum_probability"] != manifest["evaluation"]["maximum_probability"]


def test_conservative_probability_is_monotonic_for_frozen_residual_blocks() -> None:
    manifest = build_manifest(FIXTURE, PARAMETERS)
    outputs = [Decimal(row["conservative_probability"]) for row in manifest["monotonic_probe"]]
    assert outputs == sorted(outputs)
    assert manifest["conservative_probability_monotonic"] is True


def test_one_in_ten_thousand_base_probability_boundary_preserves_conservative_monotonicity() -> None:
    validated = validate_fixture(FIXTURE, PARAMETERS)
    base = validated["base_probability"]
    inputs = (base - Decimal("0.0001"), base, base + Decimal("0.0001"))
    outputs = [
        conservative_probability(
            probability,
            validated["blocks"],
            iterations=validated["runtime_iterations"],
            seed=validated["runtime_seed"],
            percentile_value=validated["percentile"],
        )
        for probability in inputs
    ]
    assert outputs == sorted(outputs)
    assert all(output <= probability for output, probability in zip(outputs, inputs))


def test_conservative_probability_never_increases_base_when_all_residuals_are_positive() -> None:
    blocks = (
        BootstrapBlock("B01", (Decimal("0.05"), Decimal("0.05"))),
        BootstrapBlock("B02", (Decimal("0.03"), Decimal("0.04"))),
    )
    base = Decimal("0.400")
    assert conservative_probability(base, blocks, iterations=1000, seed=7, percentile_value=10) == base


def test_percentile_uses_deterministic_nearest_rank() -> None:
    samples = tuple(Decimal(value) / Decimal("100") for value in range(1, 101))
    assert percentile(samples, 10) == Decimal("0.10")
    assert percentile(samples, 1) == Decimal("0.01")


@pytest.mark.parametrize(
    "mutate",
    [
        lambda fixture: fixture.update({"runtime_seed": fixture["evaluation_seed"]}),
        lambda fixture: fixture.update({"blocks": []}),
        lambda fixture: fixture["claim_boundary"].update({"network_accessed": True}),
        lambda fixture: fixture["blocks"][0].update({"residuals": ["1.0", "0.0"]}),
        lambda fixture: fixture["predecessor"].update({"contract_id": "AC-S09-P04"}),
    ],
)
def test_malformed_or_unsafe_fixture_fails_closed(mutate) -> None:
    mutated = deepcopy(FIXTURE)
    mutate(mutated)
    with pytest.raises(UncertaintyError):
        validate_fixture(mutated, PARAMETERS)


def test_invalid_bootstrap_inputs_fail_closed() -> None:
    block = BootstrapBlock("B01", (Decimal("0.01"), Decimal("-0.01")))
    with pytest.raises(UncertaintyError):
        block_bootstrap_samples(Decimal("0"), (block,), iterations=1000, seed=1)
    with pytest.raises(UncertaintyError):
        block_bootstrap_samples(Decimal("0.5"), (BootstrapBlock("B02", (Decimal("NaN"),)),), iterations=1000, seed=1)
    with pytest.raises(UncertaintyError):
        percentile((Decimal("0.1"),), 0)


def test_core_source_has_no_network_process_soak_float_or_order_capability() -> None:
    source = (ROOT / "uncertainty.py").read_text(encoding="utf-8")
    tree = ast.parse(source)
    imports = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imports.update(alias.name.split(".")[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imports.add(node.module.split(".")[0])
    assert not imports.intersection({"socket", "subprocess", "requests", "urllib", "http", "time", "asyncio", "os", "random"})
    assert "sleep(" not in source
    assert "submit_order" not in source
    assert "retry_order" not in source
    assert "float(" not in source


def test_candidate_fails_closed_when_expected_manifest_hash_is_tampered(tmp_path: Path) -> None:
    clone = _clone_project(tmp_path)
    path = clone / "machine/tests/fixtures/S10_P02.json"
    fixture = json.loads(path.read_text(encoding="utf-8"))
    fixture["expected_manifest_sha256"] = "f" * 64
    path.write_text(json.dumps(fixture, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    result = evaluate_contract(clone)
    assert result["status"] == "FAIL"
    assert "S10P02-MANIFEST-REPLAY-EXACT" in result["summary"]["failed_check_ids"]


def test_candidate_fails_closed_when_manifest_is_tampered(tmp_path: Path) -> None:
    clone = _clone_project(tmp_path)
    path = clone / "bootstrap_manifest.json"
    manifest = json.loads(path.read_text(encoding="utf-8"))
    manifest["next"] = "S10/P99_READY"
    path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    result = evaluate_contract(clone)
    assert result["status"] == "FAIL"
    assert "S10P02-MANIFEST-REPLAY-EXACT" in result["summary"]["failed_check_ids"]


def test_candidate_fails_closed_when_frozen_residual_block_is_tampered(tmp_path: Path) -> None:
    clone = _clone_project(tmp_path)
    path = clone / "machine/tests/fixtures/S10_P02.json"
    fixture = json.loads(path.read_text(encoding="utf-8"))
    fixture["blocks"][0]["residuals"][0] = "-0.031"
    path.write_text(json.dumps(fixture, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    result = evaluate_contract(clone)
    assert result["status"] == "FAIL"
    assert "S10P02-MANIFEST-REPLAY-EXACT" in result["summary"]["failed_check_ids"]


def test_candidate_fails_closed_when_p01_predecessor_is_changed(tmp_path: Path) -> None:
    clone = _clone_project(tmp_path)
    path = clone / "machine/evidence/EVD-S10-P01.json"
    evidence = json.loads(path.read_text(encoding="utf-8"))
    evidence["status"] = "FAIL"
    path.write_text(json.dumps(evidence, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    result = evaluate_contract(clone)
    assert result["status"] == "FAIL"
    assert "S10P02-P01-PREDECESSOR-HASH" in result["summary"]["failed_check_ids"]


def test_existing_evidence_fails_closed_when_index_binding_is_tampered(tmp_path: Path) -> None:
    clone = _clone_project(tmp_path)
    write_phase_evidence(clone, clone / "machine/evidence")
    path = clone / "machine/evidence/evidence_index.jsonl"
    rows = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]
    for row in rows:
        if row["id"] == "INDEX-AC-S10-P02":
            row["artifact_sha256"] = "f" * 64
    path.write_text("".join(json.dumps(row, ensure_ascii=False, sort_keys=True, separators=(", ", ": ")) + "\n" for row in rows), encoding="utf-8")
    with pytest.raises(UncertaintyAcceptanceError):
        verify_existing_phase_evidence(clone)


def test_rollback_drill_is_local_and_has_no_external_side_effect() -> None:
    rollback = perform_rollback_drill(ROOT)
    assert rollback["status"] == "PASS"
    assert rollback["feature_flag_id"] == "model:block_bootstrap_conservative_probability"
    assert rollback["external_state_changed"] is False
    assert rollback["production_state_changed"] is False
    assert rollback["real_time_soak_waited"] is False


def test_cli_is_wired_to_exact_contract_and_phase_boundaries() -> None:
    source = (ROOT / "abd_acceptance/__main__.py").read_text(encoding="utf-8")
    assert '"AC-S10-P02": write_uncertainty_phase_evidence' in source
    assert '"AC-S10-P02": verify_uncertainty_phase_evidence' in source
    with pytest.raises((UncertaintyAcceptanceError, FileNotFoundError)):
        from abd_acceptance.uncertainty import verify_existing_phase_evidence

        verify_existing_phase_evidence(ROOT / "missing")
