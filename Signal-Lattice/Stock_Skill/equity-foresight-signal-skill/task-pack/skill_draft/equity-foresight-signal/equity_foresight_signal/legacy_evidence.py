from __future__ import annotations

import csv
import hashlib
import io
from decimal import Decimal, InvalidOperation
from typing import Any

from .canonical import canonical_decimal, sha256_hex, strict_json_loads
from .errors import EFSError

LEGACY_BACKTEST_RECEIPT_SCHEMA = "efs.legacy_backtest_receipt.v1"
MAX_CSV_BYTES = 2_000_000
MAX_MANIFEST_BYTES = 512_000
MAX_REPORT_BYTES = 2_000_000
REQUIRED_COLUMNS = {
    "model",
    "n",
    "start",
    "end",
    "positive_rate",
    "mean_predicted",
    "brier",
    "log_loss",
    "roc_auc",
    "ece_10_equal_frequency",
    "calibration_slope",
    "calibration_intercept",
    "horizon",
}
BASELINE_MODEL = "rolling_base_rate"
CANDIDATE_MODEL = "regularized_logistic_online_platt"
REQUIRED_HORIZONS = (5, 20, 60)


def _bounded_bytes(value: bytes, *, field: str, limit: int) -> bytes:
    if not isinstance(value, bytes):
        raise EFSError("CONTRACT_INVALID", f"{field} must be bytes")
    if not value or len(value) > limit:
        raise EFSError("RESOURCE_LIMIT", f"{field} is empty or exceeds its byte limit")
    return value


def _decimal(value: str, field: str) -> Decimal:
    try:
        number = Decimal(value)
    except (InvalidOperation, TypeError) as exc:
        raise EFSError("CONTRACT_INVALID", f"{field} is not a finite decimal") from exc
    if not number.is_finite():
        raise EFSError("CONTRACT_INVALID", f"{field} is not a finite decimal")
    return number


def _integer(value: str, field: str, *, minimum: int = 1) -> int:
    try:
        number = int(value)
    except (TypeError, ValueError) as exc:
        raise EFSError("CONTRACT_INVALID", f"{field} is not an integer") from exc
    if str(number) != value or number < minimum:
        raise EFSError("CONTRACT_INVALID", f"{field} is outside its allowed range")
    return number


def _parse_metrics(raw: bytes) -> dict[tuple[int, str], dict[str, str]]:
    raw = _bounded_bytes(raw, field="legacy model metrics CSV", limit=MAX_CSV_BYTES)
    try:
        text = raw.decode("utf-8", errors="strict")
        reader = csv.DictReader(io.StringIO(text, newline=""))
    except UnicodeDecodeError as exc:
        raise EFSError("CONTRACT_INVALID", "legacy model metrics CSV must be UTF-8") from exc
    if set(reader.fieldnames or ()) != REQUIRED_COLUMNS:
        raise EFSError("CONTRACT_INVALID", "legacy model metrics CSV columns do not match the frozen contract")
    rows: dict[tuple[int, str], dict[str, str]] = {}
    for row in reader:
        if None in row or any(value is None for value in row.values()):
            raise EFSError("CONTRACT_INVALID", "legacy model metrics CSV has malformed rows")
        horizon = _integer(row["horizon"], "legacy horizon")
        model = row["model"]
        key = (horizon, model)
        if key in rows:
            raise EFSError("CONTRACT_INVALID", "legacy model metrics CSV has duplicate model/horizon rows")
        rows[key] = row
    if not rows:
        raise EFSError("CONTRACT_INVALID", "legacy model metrics CSV has no rows")
    return rows


def build_legacy_backtest_receipt(
    *,
    model_metrics_csv: bytes,
    run_manifest_json: bytes,
    report_markdown: bytes,
    source_label: str,
) -> dict[str, Any]:
    """Convert a prior research summary into a truth-preserving negative receipt.

    This function deliberately does *not* promote the summary into formal point-in-time
    outcome evidence. Raw source observations, exact code environment, and immutable
    model artifacts are not fully bound by the old package. The receipt is therefore a
    null-baseline regression fact and a capability guard, never promotion evidence.
    """
    if not isinstance(source_label, str) or not source_label or len(source_label.encode("utf-8")) > 256:
        raise EFSError("CONTRACT_INVALID", "legacy source_label must be a bounded non-empty string")
    metrics_raw = _bounded_bytes(model_metrics_csv, field="legacy model metrics CSV", limit=MAX_CSV_BYTES)
    manifest_raw = _bounded_bytes(run_manifest_json, field="legacy run manifest", limit=MAX_MANIFEST_BYTES)
    report_raw = _bounded_bytes(report_markdown, field="legacy report", limit=MAX_REPORT_BYTES)
    manifest = strict_json_loads(manifest_raw, max_bytes=MAX_MANIFEST_BYTES)
    if not isinstance(manifest, dict) or not isinstance(manifest.get("data"), dict) or not isinstance(manifest.get("design"), dict):
        raise EFSError("CONTRACT_INVALID", "legacy run manifest lacks data/design sections")
    rows = _parse_metrics(metrics_raw)

    horizons: list[dict[str, Any]] = []
    all_failed = True
    for horizon in REQUIRED_HORIZONS:
        baseline = rows.get((horizon, BASELINE_MODEL))
        candidate = rows.get((horizon, CANDIDATE_MODEL))
        if baseline is None or candidate is None:
            raise EFSError("CONTRACT_INVALID", f"legacy metrics lack required model pair for {horizon}D")
        baseline_n = _integer(baseline["n"], f"{horizon}D baseline n")
        candidate_n = _integer(candidate["n"], f"{horizon}D candidate n")
        if baseline_n != candidate_n or baseline["start"] != candidate["start"] or baseline["end"] != candidate["end"]:
            raise EFSError("CONTRACT_INVALID", f"legacy {horizon}D model pair is not evaluated on the same observations")
        baseline_brier = _decimal(baseline["brier"], f"{horizon}D baseline brier")
        candidate_brier = _decimal(candidate["brier"], f"{horizon}D candidate brier")
        if baseline_brier <= 0:
            raise EFSError("CONTRACT_INVALID", f"legacy {horizon}D baseline brier must be positive")
        brier_skill = Decimal(1) - candidate_brier / baseline_brier
        passed = candidate_brier < baseline_brier
        all_failed = all_failed and not passed
        horizons.append(
            {
                "horizon_trading_days": horizon,
                "sample_count": baseline_n,
                "start": baseline["start"],
                "end": baseline["end"],
                "positive_rate": canonical_decimal(_decimal(candidate["positive_rate"], f"{horizon}D positive rate")),
                "baseline_brier": canonical_decimal(baseline_brier),
                "candidate_brier": canonical_decimal(candidate_brier),
                "brier_difference_candidate_minus_baseline": canonical_decimal(candidate_brier - baseline_brier),
                "brier_skill": canonical_decimal(brier_skill),
                "candidate_auc": canonical_decimal(_decimal(candidate["roc_auc"], f"{horizon}D candidate AUC")),
                "passed_frozen_null_baseline": passed,
            }
        )
    if not all_failed:
        raise EFSError("CONTRACT_INVALID", "legacy receipt builder only accepts the frozen all-horizon negative baseline")

    data = manifest["data"]
    design = manifest["design"]
    receipt: dict[str, Any] = {
        "schema": LEGACY_BACKTEST_RECEIPT_SCHEMA,
        "source_label": source_label,
        "evidence_class": "LEGACY_RESEARCH_SUMMARY_ONLY",
        "overall_status": "FAIL",
        "capability_limit": "SHADOW_ONLY",
        "formal_outcome_eligible": False,
        "promotion_evidence_eligible": False,
        "preservation_purpose": "NULL_BASELINE_AND_REGRESSION_GUARD",
        "subject": {
            "instrument": "SPY",
            "data_start": data.get("start"),
            "data_end": data.get("end"),
            "row_count": data.get("rows"),
            "horizons_trading_days": list(REQUIRED_HORIZONS),
            "round_trip_cost": canonical_decimal(_decimal(str(design.get("round_trip_cost")), "legacy round-trip cost")),
            "candidate_model": CANDIDATE_MODEL,
            "baseline_model": BASELINE_MODEL,
        },
        "horizon_results": horizons,
        "blocking_reasons": [
            "MODEL_DID_NOT_BEAT_ROLLING_BASELINE_AT_ANY_FROZEN_HORIZON",
            "RAW_POINT_IN_TIME_OBSERVATIONS_NOT_BUNDLED_IN_RECEIPT",
            "SINGLE_ASSET_RESEARCH_BASELINE",
            "NOT_AN_IMMUTABLE_CURRENT_CANDIDATE_SUBJECT",
        ],
        "source_hashes": {
            "model_metrics_csv_sha256": hashlib.sha256(metrics_raw).hexdigest(),
            "run_manifest_json_sha256": hashlib.sha256(manifest_raw).hexdigest(),
            "report_markdown_sha256": hashlib.sha256(report_raw).hexdigest(),
        },
        "agent_invocations_total": 0,
        "llm_requests_total": 0,
        "llm_input_tokens_total": 0,
        "llm_output_tokens_total": 0,
        "network_requests_total": 0,
    }
    receipt["receipt_sha256"] = sha256_hex(receipt)
    return receipt
