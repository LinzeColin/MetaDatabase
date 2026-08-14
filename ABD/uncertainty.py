"""Deterministic block-bootstrap uncertainty primitives for ABD S10/P02.

The module works only on frozen residual blocks.  It has no live-provider,
account, order, or wall-clock dependency, and it does not produce an advice
or execution action.
"""

from __future__ import annotations

import argparse
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation, localcontext
import hashlib
import json
from pathlib import Path
from typing import Any, Mapping, Sequence


DECIMAL_PRECISION = 50
_ZERO = Decimal("0")
_ONE = Decimal("1")
_LCG_MULTIPLIER = 6364136223846793005
_LCG_INCREMENT = 1442695040888963407
_LCG_MASK = (1 << 64) - 1

FIXTURE_ID = "FIX-S10-P02-BLOCK-BOOTSTRAP"
CONTRACT_ID = "AC-S10-P02"
REQUIREMENT_ID = "REQ-S10-P02"
STAGE_ID = "S10"
PHASE_ID = "P02"
INPUT_MODE = "FROZEN_SYNTHETIC_NO_NETWORK_NO_ACCOUNT"
EXTERNAL_EFFECT_BOUNDARY = {
    "external_network_accessed": False,
    "actual_market_or_odds_observed": False,
    "recommendation_generated_or_enabled": False,
    "order_submission_enabled": False,
    "real_account_balance_read_or_written": False,
    "gmail_account_or_api_accessed": False,
    "ovh_or_cloudflare_runtime_accessed": False,
    "production_deployed_or_activated": False,
    "financial_return_verified_or_guaranteed": False,
    "real_time_soak_waited": False,
    "incremental_cash_spent_aud": "0.00",
}


class UncertaintyError(ValueError):
    """Raised when frozen bootstrap input or output is unsafe or malformed."""


@dataclass(frozen=True)
class BootstrapBlock:
    """One chronological residual block retained as an indivisible sample unit."""

    block_id: str
    residuals: tuple[Decimal, ...]


def canonical_json_bytes(value: Any) -> bytes:
    return (json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2) + "\n").encode("utf-8")


def decimal_text(value: Decimal) -> str:
    if not isinstance(value, Decimal) or not value.is_finite():
        raise UncertaintyError("value must be a finite Decimal")
    rendered = format(value, "f")
    if "." in rendered:
        rendered = rendered.rstrip("0").rstrip(".")
    return rendered or "0"


def _decimal(value: Any, *, label: str) -> Decimal:
    if not isinstance(value, str):
        raise UncertaintyError("%s must be a decimal string" % label)
    try:
        parsed = Decimal(value)
    except InvalidOperation as exc:
        raise UncertaintyError("%s is not decimal" % label) from exc
    if not parsed.is_finite():
        raise UncertaintyError("%s must be finite" % label)
    return parsed


def _probability(value: Any, *, label: str) -> Decimal:
    parsed = _decimal(value, label=label)
    if not _ZERO < parsed < _ONE:
        raise UncertaintyError("%s must be strictly between zero and one" % label)
    return parsed


def _residual(value: Any, *, label: str) -> Decimal:
    parsed = _decimal(value, label=label)
    if not -_ONE < parsed < _ONE:
        raise UncertaintyError("%s must be strictly between minus one and one" % label)
    return parsed


def _integer(value: Any, *, label: str, minimum: int, maximum: int) -> int:
    if type(value) is not int or not minimum <= value <= maximum:
        raise UncertaintyError("%s is outside the allowed integer range" % label)
    return value


def _strict_object(value: Any, fields: set[str], *, label: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping) or set(value) != fields:
        raise UncertaintyError("%s has an unexpected shape" % label)
    return value


def _clamp_probability(value: Decimal) -> Decimal:
    return min(max(value, _ZERO), _ONE)


def _next_state(state: int) -> int:
    return (state * _LCG_MULTIPLIER + _LCG_INCREMENT) & _LCG_MASK


def _block_digest(blocks: Sequence[BootstrapBlock]) -> str:
    payload = [
        {"block_id": block.block_id, "residuals": [decimal_text(value) for value in block.residuals]}
        for block in blocks
    ]
    return hashlib.sha256(canonical_json_bytes(payload)).hexdigest()


def _sample_digest(samples: Sequence[Decimal]) -> str:
    return hashlib.sha256(canonical_json_bytes([decimal_text(value) for value in samples])).hexdigest()


def validate_fixture(fixture: Any, parameters: Any) -> Mapping[str, Any]:
    """Validate the complete frozen input and return typed bootstrap values."""

    required = {
        "schema_version",
        "fixture_id",
        "contract_id",
        "requirement_id",
        "stage_id",
        "phase_id",
        "product_version",
        "fixed_clock",
        "input_mode",
        "base_probability",
        "blocks",
        "runtime_seed",
        "evaluation_seed",
        "monotonic_probe_probabilities",
        "claim_boundary",
        "predecessor",
        "expected_manifest_sha256",
    }
    row = _strict_object(fixture, required, label="fixture")
    identity_ok = (
        row["schema_version"] == "1.0.0"
        and row["fixture_id"] == FIXTURE_ID
        and row["contract_id"] == CONTRACT_ID
        and row["requirement_id"] == REQUIREMENT_ID
        and row["stage_id"] == STAGE_ID
        and row["phase_id"] == PHASE_ID
        and row["product_version"] == "0.0.0.1"
        and row["fixed_clock"] == "2026-07-30T00:00:00+10:00"
        and row["input_mode"] == INPUT_MODE
    )
    if not identity_ok:
        raise UncertaintyError("fixture identity is invalid")
    market = parameters.get("market_model") if isinstance(parameters, Mapping) else None
    if not isinstance(market, Mapping):
        raise UncertaintyError("market_model parameters are unavailable")
    runtime_iterations = market.get("runtime_block_bootstrap_iterations")
    evaluation_iterations = market.get("evaluation_block_bootstrap_iterations")
    percentile = market.get("conservative_probability_percentile")
    if runtime_iterations != 1000 or evaluation_iterations != 2000 or percentile != 10:
        raise UncertaintyError("bootstrap parameters differ from the frozen task pack")
    base_probability = _probability(row["base_probability"], label="fixture.base_probability")
    raw_blocks = row["blocks"]
    if not isinstance(raw_blocks, list) or not 4 <= len(raw_blocks) <= 32:
        raise UncertaintyError("fixture.blocks must contain between four and thirty-two blocks")
    blocks: list[BootstrapBlock] = []
    expected_ids = ["B%02d" % number for number in range(1, len(raw_blocks) + 1)]
    for expected_id, raw_block in zip(expected_ids, raw_blocks):
        block = _strict_object(raw_block, {"block_id", "residuals"}, label="fixture.block.%s" % expected_id)
        residuals = block["residuals"]
        if block["block_id"] != expected_id or not isinstance(residuals, list) or not 2 <= len(residuals) <= 16:
            raise UncertaintyError("bootstrap block %s is invalid" % expected_id)
        blocks.append(
            BootstrapBlock(
                block_id=expected_id,
                residuals=tuple(_residual(value, label="fixture.block.%s.residual" % expected_id) for value in residuals),
            )
        )
    runtime_seed = _integer(row["runtime_seed"], label="fixture.runtime_seed", minimum=0, maximum=_LCG_MASK)
    evaluation_seed = _integer(row["evaluation_seed"], label="fixture.evaluation_seed", minimum=0, maximum=_LCG_MASK)
    if runtime_seed == evaluation_seed:
        raise UncertaintyError("runtime and evaluation seeds must differ")
    probes_raw = row["monotonic_probe_probabilities"]
    if not isinstance(probes_raw, list) or len(probes_raw) < 3:
        raise UncertaintyError("fixture.monotonic_probe_probabilities is invalid")
    probes = tuple(_probability(value, label="fixture.monotonic_probe_probabilities") for value in probes_raw)
    if list(probes) != sorted(probes) or len(probes) != len(set(probes)):
        raise UncertaintyError("monotonic probes must be strictly increasing")
    predecessor = _strict_object(
        row["predecessor"],
        {"contract_id", "evidence_path", "sha256"},
        label="fixture.predecessor",
    )
    if predecessor["contract_id"] != "AC-S10-P01" or predecessor["evidence_path"] != "machine/evidence/EVD-S10-P01.json":
        raise UncertaintyError("fixture predecessor is invalid")
    predecessor_hash = predecessor["sha256"]
    expected_hash = row["expected_manifest_sha256"]
    for value, label in ((predecessor_hash, "fixture.predecessor.sha256"), (expected_hash, "fixture.expected_manifest_sha256")):
        if not isinstance(value, str) or len(value) != 64 or any(character not in "0123456789abcdef" for character in value):
            raise UncertaintyError("%s must be a lowercase SHA-256 digest" % label)
    boundary = _strict_object(
        row["claim_boundary"],
        {
            "network_accessed",
            "actual_market_or_odds_observed",
            "recommendation_generated",
            "order_submission_enabled",
            "real_time_soak_required",
            "incremental_cash_spent_aud",
        },
        label="fixture.claim_boundary",
    )
    boundary_ok = (
        boundary["network_accessed"] is False
        and boundary["actual_market_or_odds_observed"] is False
        and boundary["recommendation_generated"] is False
        and boundary["order_submission_enabled"] is False
        and boundary["real_time_soak_required"] is False
        and boundary["incremental_cash_spent_aud"] == "0.00"
    )
    if not boundary_ok:
        raise UncertaintyError("fixture claim boundary is unsafe")
    return {
        "base_probability": base_probability,
        "blocks": tuple(blocks),
        "runtime_seed": runtime_seed,
        "evaluation_seed": evaluation_seed,
        "probes": probes,
        "runtime_iterations": runtime_iterations,
        "evaluation_iterations": evaluation_iterations,
        "percentile": percentile,
        "predecessor": predecessor,
        "expected_manifest_sha256": expected_hash,
    }


def block_bootstrap_samples(
    base_probability: Decimal,
    blocks: Sequence[BootstrapBlock],
    *,
    iterations: int,
    seed: int,
) -> tuple[Decimal, ...]:
    """Resample complete chronological blocks with replacement using a fixed LCG."""

    if not isinstance(base_probability, Decimal) or not _ZERO < base_probability < _ONE:
        raise UncertaintyError("base_probability must be a strict Decimal probability")
    if not isinstance(blocks, Sequence) or not blocks:
        raise UncertaintyError("blocks are required")
    if type(iterations) is not int or not 1 <= iterations <= 10000:
        raise UncertaintyError("iterations are out of range")
    block_ids: set[str] = set()
    for block in blocks:
        if not isinstance(block, BootstrapBlock) or not isinstance(block.block_id, str) or not block.block_id or block.block_id in block_ids or not block.residuals:
            raise UncertaintyError("bootstrap block is invalid")
        block_ids.add(block.block_id)
        for residual in block.residuals:
            if not isinstance(residual, Decimal) or not residual.is_finite() or not -_ONE < residual < _ONE:
                raise UncertaintyError("bootstrap residual is invalid")
    state = _integer(seed, label="seed", minimum=0, maximum=_LCG_MASK)
    samples: list[Decimal] = []
    with localcontext() as context:
        context.prec = DECIMAL_PRECISION
        for _ in range(iterations):
            total = _ZERO
            count = 0
            for _ in range(len(blocks)):
                state = _next_state(state)
                selected = blocks[(state * len(blocks)) >> 64]
                total += sum(selected.residuals, _ZERO)
                count += len(selected.residuals)
            samples.append(_clamp_probability(base_probability + (total / Decimal(count))))
    return tuple(samples)


def percentile(samples: Sequence[Decimal], percentile_value: int) -> Decimal:
    if not samples:
        raise UncertaintyError("samples are required")
    if type(percentile_value) is not int or not 1 <= percentile_value <= 99:
        raise UncertaintyError("percentile must be an integer from one through ninety-nine")
    if any(not isinstance(value, Decimal) or not value.is_finite() or value < _ZERO or value > _ONE for value in samples):
        raise UncertaintyError("samples contain an invalid probability")
    rank = max(1, (percentile_value * len(samples) + 99) // 100)
    return sorted(samples)[rank - 1]


def conservative_probability(
    base_probability: Decimal,
    blocks: Sequence[BootstrapBlock],
    *,
    iterations: int,
    seed: int,
    percentile_value: int,
) -> Decimal:
    samples = block_bootstrap_samples(base_probability, blocks, iterations=iterations, seed=seed)
    return min(base_probability, percentile(samples, percentile_value))


def _run_payload(
    base_probability: Decimal,
    blocks: Sequence[BootstrapBlock],
    *,
    iterations: int,
    seed: int,
    percentile_value: int,
) -> Mapping[str, Any]:
    samples = block_bootstrap_samples(base_probability, blocks, iterations=iterations, seed=seed)
    conservative = min(base_probability, percentile(samples, percentile_value))
    return {
        "seed": seed,
        "iterations": iterations,
        "percentile": percentile_value,
        "sample_sha256": _sample_digest(samples),
        "minimum_probability": decimal_text(min(samples)),
        "maximum_probability": decimal_text(max(samples)),
        "conservative_probability": decimal_text(conservative),
    }


def build_manifest(fixture: Any, parameters: Any) -> Mapping[str, Any]:
    """Build the exact local-only runtime and evaluation bootstrap record."""

    validated = validate_fixture(fixture, parameters)
    blocks = validated["blocks"]
    base_probability = validated["base_probability"]
    runtime = _run_payload(
        base_probability,
        blocks,
        iterations=validated["runtime_iterations"],
        seed=validated["runtime_seed"],
        percentile_value=validated["percentile"],
    )
    evaluation = _run_payload(
        base_probability,
        blocks,
        iterations=validated["evaluation_iterations"],
        seed=validated["evaluation_seed"],
        percentile_value=validated["percentile"],
    )
    probes = [
        {
            "input_probability": decimal_text(probability),
            "conservative_probability": decimal_text(
                conservative_probability(
                    probability,
                    blocks,
                    iterations=validated["runtime_iterations"],
                    seed=validated["runtime_seed"],
                    percentile_value=validated["percentile"],
                )
            ),
        }
        for probability in validated["probes"]
    ]
    probe_outputs = [Decimal(row["conservative_probability"]) for row in probes]
    monotonic = probe_outputs == sorted(probe_outputs)
    decision = "CONSERVATIVE_PROBABILITY_READY_DOWNSTREAM_DECIMAL_GATE_REQUIRED" if monotonic else "NO_ADVICE_UNCERTAINTY_GATE_BLOCKED"
    return {
        "schema_version": "1.0.0",
        "manifest_id": "MAN-S10-P02-BLOCK-BOOTSTRAP",
        "fixture_id": FIXTURE_ID,
        "contract_id": CONTRACT_ID,
        "requirement_id": REQUIREMENT_ID,
        "stage_id": STAGE_ID,
        "phase_id": PHASE_ID,
        "product_version": fixture["product_version"],
        "fixed_clock": fixture["fixed_clock"],
        "input_mode": INPUT_MODE,
        "model": "BLOCK_BOOTSTRAP_RESIDUAL_PERCENTILE",
        "predecessor": dict(validated["predecessor"]),
        "parameters": {
            "runtime_block_bootstrap_iterations": validated["runtime_iterations"],
            "evaluation_block_bootstrap_iterations": validated["evaluation_iterations"],
            "conservative_probability_percentile": validated["percentile"],
        },
        "base_probability": decimal_text(base_probability),
        "block_count": len(blocks),
        "block_sha256": _block_digest(blocks),
        "runtime": runtime,
        "evaluation": evaluation,
        "conservative_probability": runtime["conservative_probability"],
        "monotonic_probe": probes,
        "conservative_probability_monotonic": monotonic,
        "decision": decision,
        "next": "S10/P03_READY_NOT_STARTED" if monotonic else "S10/P02_BLOCKED",
        "external_effect_boundary": dict(EXTERNAL_EFFECT_BOUNDARY),
        "financial_target_status": "UNVERIFIED_NOT_GUARANTEED",
        "production_status": "NOT_DEPLOYED_OR_ACTIVATED",
    }


def manifest_sha256(manifest: Mapping[str, Any]) -> str:
    return hashlib.sha256(canonical_json_bytes(manifest)).hexdigest()


def load_json(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise UncertaintyError("cannot read JSON: %s" % path) from exc


def write_manifest(fixture_path: Path, parameters_path: Path, output_path: Path) -> Mapping[str, Any]:
    fixture = load_json(fixture_path)
    parameters = load_json(parameters_path)
    manifest = build_manifest(fixture, parameters)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    temporary = output_path.with_name(output_path.name + ".tmp")
    temporary.write_bytes(canonical_json_bytes(manifest))
    temporary.replace(output_path)
    return {"status": "PASS", "manifest": output_path.as_posix(), "manifest_sha256": manifest_sha256(manifest)}


def main() -> int:
    parser = argparse.ArgumentParser(description="ABD S10/P02 frozen block-bootstrap manifest")
    parser.add_argument("--fixture", default="machine/tests/fixtures/S10_P02.json")
    parser.add_argument("--parameters", default="machine/facts/parameters.json")
    parser.add_argument("--output", default="bootstrap_manifest.json")
    args = parser.parse_args()
    result = write_manifest(Path(args.fixture), Path(args.parameters), Path(args.output))
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
