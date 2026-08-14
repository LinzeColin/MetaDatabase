"""Deterministic S16/P01 Champion/Challenger registry and frozen reports engine.

The module is intentionally a local pre-evaluation control.  It records a
market-consensus Champion and already-signed Challenger implementations across
frozen synthetic windows, but it never treats that inventory as empirical
model evidence.  Until S16/P02 supplies a separate signed evaluation, every
Challenger remains at zero active weight.
"""

from __future__ import annotations

import argparse
from datetime import datetime
from decimal import Decimal, InvalidOperation
import hashlib
import json
from pathlib import Path
import re
from typing import Any, Mapping


CONTRACT_ID = "AC-S16-P01"
REQUIREMENT_ID = "REQ-S16-P01"
STAGE_ID = "S16"
PHASE_ID = "P01"
PRODUCT_VERSION = "0.0.0.1"
FIXED_CLOCK = "2026-08-09T00:00:00+10:00"
INPUT_MODE = "FROZEN_SYNTHETIC_NO_NETWORK_NO_ACCOUNT"
FIXTURE_PATH = Path("machine/tests/fixtures/S16_P01.json")
MODEL_REGISTRY_PATH = Path("model_registry.json")
BASELINE_REPORT_PATH = Path("baseline_report.json")
CHALLENGER_REPORT_PATH = Path("challenger_report.json")
_SHA256 = re.compile(r"[0-9a-f]{64}")
_IDENTIFIER = re.compile(r"[A-Z][A-Z0-9_:-]{2,79}")
_ZERO = Decimal("0")

PREDECESSOR_LAYOUT = {
    "AC-S08-P04": {
        "evidence_path": "machine/evidence/EVD-S08-P04.json",
        "next": "S08/STAGE_REVIEW_READY_NOT_STARTED",
    },
    "AC-S09-P04": {
        "evidence_path": "machine/evidence/EVD-S09-P04.json",
        "next": "S09/STAGE_REVIEW_READY_NOT_STARTED",
    },
    "AC-S10-P04": {
        "evidence_path": "machine/evidence/EVD-S10-P04.json",
        "next": "S10/STAGE_REVIEW_READY_NOT_STARTED",
    },
    "AC-S11-P04": {
        "evidence_path": "machine/evidence/EVD-S11-P04.json",
        "next": "S11/STAGE_REVIEW_READY_NOT_STARTED",
    },
}

CHALLENGER_CATALOG = (
    {
        "model_id": "GENERIC_RESIDUAL_CHALLENGER",
        "label": "通用市场残差 Challenger",
        "predecessor_contract_id": "AC-S09-P04",
        "source_artifacts": ("generic_residual.py",),
    },
    {
        "model_id": "TENNIS_CHALLENGER",
        "label": "网球 Challenger",
        "predecessor_contract_id": "AC-S09-P04",
        "source_artifacts": ("tennis_model.py",),
    },
    {
        "model_id": "COMBAT_CHALLENGER",
        "label": "格斗 Challenger",
        "predecessor_contract_id": "AC-S09-P04",
        "source_artifacts": ("combat_model.py",),
    },
    {
        "model_id": "FOOTBALL_SCORE_CHALLENGER",
        "label": "足球比分 Challenger",
        "predecessor_contract_id": "AC-S09-P04",
        "source_artifacts": ("score_models.py", "football_model.py"),
    },
    {
        "model_id": "RACING_FALLBACK_CHALLENGER",
        "label": "赛马保守回退 Challenger",
        "predecessor_contract_id": "AC-S09-P04",
        "source_artifacts": ("racing_model.py",),
    },
    {
        "model_id": "MULTI_SPORT_FALLBACK_CHALLENGER",
        "label": "多运动保守回退 Challenger",
        "predecessor_contract_id": "AC-S09-P04",
        "source_artifacts": ("basketball_model.py", "baseball_model.py", "niche_fallback.json"),
    },
)

CLAIM_BOUNDARY = {
    "external_network_accessed": False,
    "real_market_or_odds_observed": False,
    "empirical_model_increment_verified": False,
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


class ModelChallengeInputError(ValueError):
    """Raised when S16/P01 local model inventory evidence is malformed."""


def canonical_json_bytes(value: Any) -> bytes:
    return (json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2) + "\n").encode("utf-8")


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def artifact_sha256(value: Any) -> str:
    return hashlib.sha256(canonical_json_bytes(value)).hexdigest()


def strict_json_load(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ModelChallengeInputError("cannot read JSON artifact: %s" % path.as_posix()) from exc


def _closed_mapping(value: Any, fields: set[str], label: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping) or set(value) != fields:
        raise ModelChallengeInputError("%s fields are not exact" % label)
    return value


def _identifier(value: Any, label: str) -> str:
    if not isinstance(value, str) or not _IDENTIFIER.fullmatch(value):
        raise ModelChallengeInputError("%s must be a stable uppercase identifier" % label)
    return value


def _decimal(value: Any, label: str) -> Decimal:
    if not isinstance(value, str):
        raise ModelChallengeInputError("%s must be a decimal string" % label)
    try:
        parsed = Decimal(value)
    except InvalidOperation as exc:
        raise ModelChallengeInputError("%s is not decimal" % label) from exc
    if not parsed.is_finite():
        raise ModelChallengeInputError("%s must be finite" % label)
    return parsed


def _parse_timestamp(value: Any, label: str) -> datetime:
    if not isinstance(value, str):
        raise ModelChallengeInputError("%s must be ISO-8601 text" % label)
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError as exc:
        raise ModelChallengeInputError("%s is not ISO-8601" % label) from exc
    if parsed.tzinfo is None:
        raise ModelChallengeInputError("%s must include an offset" % label)
    return parsed


def _validate_parameters(parameters: Any) -> Mapping[str, Any]:
    if not isinstance(parameters, Mapping):
        raise ModelChallengeInputError("parameters must be an object")
    market_model = parameters.get("market_model")
    if not isinstance(market_model, Mapping):
        raise ModelChallengeInputError("market_model parameters are unavailable")
    expected = {
        "market_prior_weight_min": "0.50",
        "residual_weight_alpha_beta_max": "0.35",
        "residual_weight_when_no_increment": "0.00",
        "future_leakage_tolerance": 0,
    }
    if any(market_model.get(key) != item for key, item in expected.items()):
        raise ModelChallengeInputError("market-model safety parameters do not match the frozen baseline")
    return parameters


def _validate_predecessors(value: Any) -> Mapping[str, Mapping[str, str]]:
    if not isinstance(value, Mapping) or set(value) != set(PREDECESSOR_LAYOUT):
        raise ModelChallengeInputError("fixture predecessors are not exact")
    normalized: dict[str, Mapping[str, str]] = {}
    for contract_id, layout in PREDECESSOR_LAYOUT.items():
        row = _closed_mapping(
            value.get(contract_id),
            {"evidence_path", "evidence_sha256", "status", "next"},
            "predecessor %s" % contract_id,
        )
        if (
            row["evidence_path"] != layout["evidence_path"]
            or not isinstance(row["evidence_sha256"], str)
            or not _SHA256.fullmatch(row["evidence_sha256"])
            or row["status"] != "PASS"
            or row["next"] != layout["next"]
        ):
            raise ModelChallengeInputError("predecessor %s is invalid" % contract_id)
        normalized[contract_id] = row
    return normalized


def _validate_windows(value: Any) -> list[Mapping[str, Any]]:
    if not isinstance(value, list) or len(value) != 3:
        raise ModelChallengeInputError("exactly three frozen comparison windows are required")
    windows: list[Mapping[str, Any]] = []
    prior_end: datetime | None = None
    identifiers: set[str] = set()
    for index, raw in enumerate(value):
        row = _closed_mapping(
            raw,
            {"window_id", "start_at", "end_at", "classification", "observed_outcome_count"},
            "frozen_windows[%d]" % index,
        )
        window_id = _identifier(row["window_id"], "frozen_windows[%d].window_id" % index)
        start = _parse_timestamp(row["start_at"], "frozen_windows[%d].start_at" % index)
        end = _parse_timestamp(row["end_at"], "frozen_windows[%d].end_at" % index)
        if window_id in identifiers or start >= end or (prior_end is not None and start < prior_end):
            raise ModelChallengeInputError("frozen comparison windows must be unique and ordered")
        if row["classification"] != "FROZEN_SYNTHETIC_PRE_EVALUATION_NOT_EMPIRICAL" or row["observed_outcome_count"] != 0:
            raise ModelChallengeInputError("S16/P01 windows must remain synthetic and non-empirical")
        identifiers.add(window_id)
        prior_end = end
        windows.append(row)
    return windows


def _catalog_by_id() -> dict[str, Mapping[str, Any]]:
    return {str(row["model_id"]): row for row in CHALLENGER_CATALOG}


def _validate_assessments(value: Any, windows: list[Mapping[str, Any]]) -> list[Mapping[str, Any]]:
    catalog = _catalog_by_id()
    if not isinstance(value, list) or len(value) != len(catalog):
        raise ModelChallengeInputError("fixture must contain every Challenger exactly once")
    expected_windows = [str(row["window_id"]) for row in windows]
    assessments: list[Mapping[str, Any]] = []
    identifiers: set[str] = set()
    for index, raw in enumerate(value):
        row = _closed_mapping(raw, {"model_id", "windows", "aggregate"}, "challenger_assessments[%d]" % index)
        model_id = _identifier(row["model_id"], "challenger_assessments[%d].model_id" % index)
        if model_id not in catalog or model_id in identifiers:
            raise ModelChallengeInputError("Challenger catalog membership is invalid")
        raw_windows = row["windows"]
        if not isinstance(raw_windows, list) or len(raw_windows) != len(expected_windows):
            raise ModelChallengeInputError("Challenger window assessments are incomplete")
        parsed_windows: list[Mapping[str, Any]] = []
        for window_index, item in enumerate(raw_windows):
            assessment = _closed_mapping(
                item,
                {"window_id", "significant_increment", "assigned_weight", "reason_code", "empirical_evidence_status"},
                "assessment %s[%d]" % (model_id, window_index),
            )
            if (
                assessment["window_id"] != expected_windows[window_index]
                or assessment["significant_increment"] is not False
                or _decimal(assessment["assigned_weight"], "assigned_weight") != _ZERO
                or assessment["reason_code"] != "NO_SIGNIFICANT_INCREMENT_EVIDENCE_PRE_S16_P02"
                or assessment["empirical_evidence_status"] != "NOT_AVAILABLE_IN_S16_P01"
            ):
                raise ModelChallengeInputError("S16/P01 may not assign a non-zero Challenger weight")
            parsed_windows.append(assessment)
        aggregate = _closed_mapping(
            row["aggregate"],
            {"significant_increment", "assigned_weight", "activation"},
            "assessment aggregate %s" % model_id,
        )
        if (
            aggregate["significant_increment"] is not False
            or _decimal(aggregate["assigned_weight"], "aggregate.assigned_weight") != _ZERO
            or aggregate["activation"] != "KEEP_CHAMPION_MARKET_ONLY_PENDING_S16_P02"
        ):
            raise ModelChallengeInputError("S16/P01 aggregate must retain the market Champion")
        assessments.append({"model_id": model_id, "windows": parsed_windows, "aggregate": aggregate})
        identifiers.add(model_id)
    if identifiers != set(catalog):
        raise ModelChallengeInputError("Challenger catalog is incomplete")
    return assessments


def validate_fixture(value: Any) -> Mapping[str, Any]:
    fields = {
        "schema_version",
        "fixture_id",
        "contract_id",
        "requirement_id",
        "stage_id",
        "phase_id",
        "product_version",
        "fixed_clock",
        "input_mode",
        "parameters_sha256",
        "predecessors",
        "frozen_windows",
        "challenger_assessments",
        "minimum_targeted_pytest_cases",
        "expected_decision",
        "expected_next",
        "claim_boundary",
    }
    fixture = _closed_mapping(value, fields, "S16/P01 fixture")
    if (
        fixture["schema_version"] != "1.0.0"
        or fixture["fixture_id"] != "FIX-S16-P01-MARKET-CHAMPION-CHALLENGER"
        or fixture["contract_id"] != CONTRACT_ID
        or fixture["requirement_id"] != REQUIREMENT_ID
        or fixture["stage_id"] != STAGE_ID
        or fixture["phase_id"] != PHASE_ID
        or fixture["product_version"] != PRODUCT_VERSION
        or fixture["fixed_clock"] != FIXED_CLOCK
        or fixture["input_mode"] != INPUT_MODE
        or not isinstance(fixture["parameters_sha256"], str)
        or not _SHA256.fullmatch(fixture["parameters_sha256"])
        or not isinstance(fixture["minimum_targeted_pytest_cases"], int)
        or fixture["minimum_targeted_pytest_cases"] < 20
        or fixture["expected_decision"] != "S16_P01_MARKET_CHAMPION_RETAINED_CHALLENGERS_ZERO_WEIGHT_P02_REQUIRED"
        or fixture["expected_next"] != "S16/P02_READY_NOT_STARTED"
        or fixture["claim_boundary"] != CLAIM_BOUNDARY
    ):
        raise ModelChallengeInputError("S16/P01 fixture header is invalid")
    windows = _validate_windows(fixture["frozen_windows"])
    _validate_predecessors(fixture["predecessors"])
    _validate_assessments(fixture["challenger_assessments"], windows)
    return fixture


def load_fixture(path: Path | str) -> Mapping[str, Any]:
    return validate_fixture(strict_json_load(Path(path)))


def _read_predecessors(root: Path, fixture: Mapping[str, Any]) -> dict[str, Mapping[str, Any]]:
    expected = _validate_predecessors(fixture["predecessors"])
    results: dict[str, Mapping[str, Any]] = {}
    for contract_id, metadata in expected.items():
        path = root / metadata["evidence_path"]
        document = strict_json_load(path)
        if (
            not isinstance(document, Mapping)
            or sha256_file(path) != metadata["evidence_sha256"]
            or document.get("contract_id") != contract_id
            or document.get("status") != metadata["status"]
            or document.get("next") != metadata["next"]
        ):
            raise ModelChallengeInputError("signed predecessor is stale or inconsistent: %s" % contract_id)
        results[contract_id] = {
            "evidence_path": metadata["evidence_path"],
            "evidence_sha256": metadata["evidence_sha256"],
            "contract_id": contract_id,
            "status": metadata["status"],
            "next": metadata["next"],
        }
    return results


def _source_receipts(root: Path, paths: tuple[str, ...]) -> list[dict[str, str]]:
    receipts: list[dict[str, str]] = []
    for relative in paths:
        path = root / relative
        if not path.is_file():
            raise ModelChallengeInputError("required Challenger artifact is missing: %s" % relative)
        receipts.append({"path": relative, "sha256": sha256_file(path)})
    return receipts


def build_artifacts(root: Path, fixture: Mapping[str, Any]) -> dict[str, Mapping[str, Any]]:
    """Build the three P01 artifacts from local frozen inputs only."""

    root = root.resolve()
    fixture = validate_fixture(fixture)
    parameters_path = root / "machine/facts/parameters.json"
    if sha256_file(parameters_path) != fixture["parameters_sha256"]:
        raise ModelChallengeInputError("parameters hash differs from the frozen fixture")
    _validate_parameters(strict_json_load(parameters_path))
    predecessors = _read_predecessors(root, fixture)
    windows = _validate_windows(fixture["frozen_windows"])
    assessments_by_id = {row["model_id"]: row for row in _validate_assessments(fixture["challenger_assessments"], windows)}

    champion_source = _source_receipts(root, ("market_consensus.py", "consensus_vectors.json"))
    champion = {
        "model_id": "MARKET_CONSENSUS_CHAMPION",
        "role": "CHAMPION",
        "label": "市场共识 Champion",
        "source_contract_id": "AC-S08-P04",
        "source_receipt": predecessors["AC-S08-P04"],
        "source_artifacts": champion_source,
        "active_weight": "1.00",
        "activation_status": "MARKET_CHAMPION_ACTIVE_SYNTHETIC_BASELINE_ONLY",
    }
    challengers: list[dict[str, Any]] = []
    for specification in CHALLENGER_CATALOG:
        model_id = str(specification["model_id"])
        assessment = assessments_by_id[model_id]
        challengers.append(
            {
                "model_id": model_id,
                "role": "CHALLENGER",
                "label": specification["label"],
                "source_contract_id": specification["predecessor_contract_id"],
                "source_receipt": predecessors[str(specification["predecessor_contract_id"])],
                "source_artifacts": _source_receipts(root, tuple(specification["source_artifacts"])),
                "window_assessments": assessment["windows"],
                "significant_increment": assessment["aggregate"]["significant_increment"],
                "active_weight": assessment["aggregate"]["assigned_weight"],
                "activation_status": assessment["aggregate"]["activation"],
            }
        )
    challengers.sort(key=lambda row: row["model_id"])
    registry: dict[str, Any] = {
        "schema_version": "1.0.0",
        "artifact_id": "ART-S16-P01-01",
        "contract_id": CONTRACT_ID,
        "requirement_id": REQUIREMENT_ID,
        "stage_id": STAGE_ID,
        "phase_id": PHASE_ID,
        "product_version": PRODUCT_VERSION,
        "fixed_clock": FIXED_CLOCK,
        "input_mode": INPUT_MODE,
        "signed_predecessors": [predecessors[contract_id] for contract_id in sorted(predecessors)],
        "champion": champion,
        "challengers": challengers,
        "selection_policy": {
            "comparison_mode": "FROZEN_TIME_WINDOW_PRE_EVALUATION",
            "significant_increment_required": True,
            "weight_when_increment_not_significant": "0.00",
            "market_prior_weight_min": "0.50",
            "candidate_residual_weight_cap": "0.35",
            "activation_requires_contract": "AC-S16-P02",
            "safe_action_before_s16_p02": "KEEP_CHAMPION_MARKET_ONLY",
        },
        "claim_boundary": dict(CLAIM_BOUNDARY),
        "financial_target_status": "UNVERIFIED_NOT_GUARANTEED",
        "production_status": "NOT_DEPLOYED_OR_ACTIVATED",
    }
    baseline_report: dict[str, Any] = {
        "schema_version": "1.0.0",
        "artifact_id": "ART-S16-P01-02",
        "contract_id": CONTRACT_ID,
        "stage_id": STAGE_ID,
        "phase_id": PHASE_ID,
        "product_version": PRODUCT_VERSION,
        "fixed_clock": FIXED_CLOCK,
        "input_mode": INPUT_MODE,
        "registry_sha256": artifact_sha256(registry),
        "champion_model_id": champion["model_id"],
        "champion_active_weight": champion["active_weight"],
        "frozen_windows": windows,
        "window_comparison_status": "PRE_EVALUATION_SYNTHETIC_ONLY_NO_EMPIRICAL_SCORE",
        "claim_boundary": dict(CLAIM_BOUNDARY),
    }
    challenger_rows = [
        {
            "model_id": row["model_id"],
            "source_contract_id": row["source_contract_id"],
            "window_assessments": row["window_assessments"],
            "significant_increment": row["significant_increment"],
            "assigned_weight": row["active_weight"],
            "activation_status": row["activation_status"],
        }
        for row in challengers
    ]
    challenger_report: dict[str, Any] = {
        "schema_version": "1.0.0",
        "artifact_id": "ART-S16-P01-03",
        "contract_id": CONTRACT_ID,
        "stage_id": STAGE_ID,
        "phase_id": PHASE_ID,
        "product_version": PRODUCT_VERSION,
        "fixed_clock": FIXED_CLOCK,
        "input_mode": INPUT_MODE,
        "registry_sha256": artifact_sha256(registry),
        "baseline_report_sha256": artifact_sha256(baseline_report),
        "champion_model_id": champion["model_id"],
        "challengers": challenger_rows,
        "summary": {
            "challenger_count": len(challenger_rows),
            "significant_increment_count": 0,
            "nonzero_active_weight_count": 0,
            "safe_action": "KEEP_CHAMPION_MARKET_ONLY_PENDING_S16_P02",
        },
        "claim_boundary": dict(CLAIM_BOUNDARY),
        "financial_target_status": "UNVERIFIED_NOT_GUARANTEED",
        "production_status": "NOT_DEPLOYED_OR_ACTIVATED",
    }
    return {
        MODEL_REGISTRY_PATH.as_posix(): registry,
        BASELINE_REPORT_PATH.as_posix(): baseline_report,
        CHALLENGER_REPORT_PATH.as_posix(): challenger_report,
    }


def validate_artifacts(root: Path, fixture: Mapping[str, Any]) -> dict[str, Mapping[str, Any]]:
    expected = build_artifacts(root, fixture)
    for relative, value in expected.items():
        actual = strict_json_load(root / relative)
        if actual != value:
            raise ModelChallengeInputError("artifact differs from frozen local replay: %s" % relative)
    return expected


def _atomic_write(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(".%s.tmp" % path.name)
    temporary.write_bytes(data)
    temporary.replace(path)


def write_artifacts(root: Path, fixture_path: Path | str = FIXTURE_PATH) -> dict[str, Mapping[str, Any]]:
    root = root.resolve()
    fixture = load_fixture(root / fixture_path)
    artifacts = build_artifacts(root, fixture)
    for relative, value in artifacts.items():
        _atomic_write(root / relative, canonical_json_bytes(value))
    return artifacts


def main() -> int:
    parser = argparse.ArgumentParser(description="write deterministic S16/P01 local model artifacts")
    parser.add_argument("--root", default=".", help="ABD project root")
    parser.add_argument("--fixture", default=FIXTURE_PATH.as_posix(), help="fixture relative to root")
    args = parser.parse_args()
    artifacts = write_artifacts(Path(args.root), args.fixture)
    print(json.dumps({"status": "PASS", "artifacts": sorted(artifacts)}, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
