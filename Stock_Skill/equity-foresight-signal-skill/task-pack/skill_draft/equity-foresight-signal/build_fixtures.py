from __future__ import annotations

import copy
import json
from pathlib import Path

from equity_foresight_signal.canonical import sha256_hex
from equity_foresight_signal.engine import (
    BUNDLE_SCHEMA,
    MODEL_PAYLOAD_KEYS,
    PROMOTION_SCHEMA,
    REQUEST_SCHEMA,
    RUNTIME_VERSION,
    STABLE_ID,
    TRUST_SCHEMA,
)

ROOT = Path(__file__).resolve().parent


def write_json(path: Path, value: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2) + "\n", encoding="utf-8")


def embedded(value: dict, key: str = "artifact_sha256") -> dict:
    result = copy.deepcopy(value)
    result.pop(key, None)
    result[key] = sha256_hex(result)
    return result


def transform_hash(transform_id: str) -> str:
    return sha256_hex({"transform_id": transform_id, "implementation": "fixture-deterministic-v1"})


cost = embedded(
    {
        "id": "us_etf_round_trip_10bps_v1",
        "commission_bps": "0",
        "spread_slippage_bps": "10",
        "borrow_bps": "0",
        "tax_bps": "0",
    },
    key="sha256",
)

binding = {
    "label_contract_id": "net_return_next_open_20d_gt_zero_v1",
    "cost_contract_sha256": cost["sha256"],
    "calendar_id": "XNYS",
    "horizon": 20,
}

feature_contracts = {
    "mom_20": embedded(
        {
            "unit": "decimal_return",
            "transform_id": "identity_v1",
            "transform_sha256": transform_hash("identity_v1"),
            "min_value": "-1.00000000",
            "max_value": "10.00000000",
            "model_min_value": "-0.50000000",
            "model_max_value": "0.50000000",
            "null_policy": "REJECT",
            "allowed_temporal_semantics": ["MARKET_QUOTE", "OBSERVED_FACT"],
            "freshness_clock": "EFFECTIVE_AT",
            "allowed_source_dataset_ids": ["dataset:fixture_price_v1"],
            "allowed_license_ids": ["license:public_fixture_v1"],
            "source_policy": "DECLARED_LICENSED_SOURCE",
        }
    ),
    "realized_vol_20": embedded(
        {
            "unit": "annualized_decimal_volatility",
            "transform_id": "identity_v1",
            "transform_sha256": transform_hash("identity_v1"),
            "min_value": "0.00000000",
            "max_value": "10.00000000",
            "model_min_value": "0.00000000",
            "model_max_value": "2.00000000",
            "null_policy": "REJECT",
            "allowed_temporal_semantics": ["OBSERVED_FACT", "REVISED_SERIES"],
            "freshness_clock": "EFFECTIVE_AT",
            "allowed_source_dataset_ids": ["dataset:fixture_price_v1"],
            "allowed_license_ids": ["license:public_fixture_v1"],
            "source_policy": "DECLARED_LICENSED_SOURCE",
        }
    ),
    "vix_level": embedded(
        {
            "unit": "index_points",
            "transform_id": "identity_v1",
            "transform_sha256": transform_hash("identity_v1"),
            "min_value": "0.00000000",
            "max_value": "200.00000000",
            "model_min_value": "5.00000000",
            "model_max_value": "100.00000000",
            "null_policy": "REJECT",
            "allowed_temporal_semantics": ["MARKET_QUOTE", "OBSERVED_FACT"],
            "freshness_clock": "EFFECTIVE_AT",
            "allowed_source_dataset_ids": ["dataset:fixture_vix_v1"],
            "allowed_license_ids": ["license:public_fixture_v1"],
            "source_policy": "DECLARED_LICENSED_SOURCE",
        }
    ),
    "earnings_date_known": embedded(
        {
            "unit": "binary_flag",
            "transform_id": "identity_v1",
            "transform_sha256": transform_hash("identity_v1"),
            "min_value": "0.00000000",
            "max_value": "1.00000000",
            "model_min_value": "0.00000000",
            "model_max_value": "1.00000000",
            "null_policy": "REJECT",
            "allowed_temporal_semantics": ["SCHEDULED_FUTURE"],
            "freshness_clock": "PUBLISHED_AT",
            "allowed_source_dataset_ids": ["dataset:fixture_calendar_v1"],
            "allowed_license_ids": ["license:public_fixture_v1"],
            "source_policy": "DECLARED_LICENSED_SOURCE",
        }
    ),
}

experts = {
    "price": embedded(
        {
            "model_type": "linear_logit_v1",
            "required_features": ["mom_20", "realized_vol_20"],
            "weights": {"mom_20": "1.20000000", "realized_vol_20": "-0.80000000"},
            "intercept": "0.00000000",
            "minimum_evidence_grade": "POINT_IN_TIME_VERIFIED",
            "max_age_seconds": 172800,
            "fit_method": "engineering_fixture_linear_v1",
            "status": "ENGINEERING_VALIDATED",
        }
    ),
    "macro": embedded(
        {
            "model_type": "linear_logit_v1",
            "required_features": ["vix_level"],
            "weights": {"vix_level": "-0.03000000"},
            "intercept": "0.60000000",
            "minimum_evidence_grade": "SOURCE_VERIFIED",
            "max_age_seconds": 172800,
            "fit_method": "engineering_fixture_linear_v1",
            "status": "ENGINEERING_VALIDATED",
        }
    ),
}

admissible_sets = [
    embedded(
        {
            "set_id": "price_macro_v1",
            "experts": ["price", "macro"],
            "aggregator": {"weights": {"price": "0.70000000", "macro": "0.30000000"}, "intercept": "0.00000000"},
            "fit_method": "engineering_fixture_aggregator_v1",
            "status": "ENGINEERING_VALIDATED",
        }
    ),
    embedded(
        {
            "set_id": "price_only_v1",
            "experts": ["price"],
            "aggregator": {"weights": {"price": "1.00000000"}, "intercept": "0.00000000"},
            "fit_method": "engineering_fixture_aggregator_v1",
            "status": "ENGINEERING_VALIDATED",
        }
    ),
]

baseline = embedded({**binding, "prob_up": "0.60000000", "estimation_method": "engineering_fixture_constant_v1", "status": "ENGINEERING_VALIDATED"})
calibration = embedded(
    {
        **binding,
        "type": "platt_v1",
        "a": "1.00000000",
        "b": "0.00000000",
        "expires_at": "2027-01-01T00:00:00Z",
        "fit_method": "engineering_fixture_identity_v1",
        "status": "ENGINEERING_VALIDATED",
    }
)
magnitude_head = embedded(
    {
        **binding,
        "base_quantiles": {"p10": "-0.07000000", "p50": "0.01000000", "p90": "0.10000000"},
        "aggregate_slope": "0.01000000",
        "fit_method": "engineering_fixture_linear_quantile_v1",
        "status": "ENGINEERING_VALIDATED",
    }
)
timing_head = embedded(
    {
        **binding,
        "up_hurdle": "0.05000000",
        "down_hurdle": "-0.05000000",
        "aggregate_sensitivity": "0.30000000",
        "timeout_logit": "0.10000000",
        "buckets": [
            {"start_day": 1, "end_day": 5, "up_logit": "0.10000000", "down_logit": "0.00000000"},
            {"start_day": 6, "end_day": 10, "up_logit": "0.20000000", "down_logit": "-0.10000000"},
            {"start_day": 11, "end_day": 15, "up_logit": "0.10000000", "down_logit": "0.00000000"},
            {"start_day": 16, "end_day": 20, "up_logit": "0.00000000", "down_logit": "0.10000000"},
        ],
        "fit_method": "engineering_fixture_competing_risk_v1",
        "status": "ENGINEERING_VALIDATED",
    }
)
economic_edge_head = embedded(
    {
        **binding,
        "type": "linear_expected_net_return_v1",
        "base_mean_net_return": "0.00200000",
        "aggregate_slope": "0.01000000",
        "fit_method": "engineering_fixture_linear_net_return_v1",
        "status": "ENGINEERING_VALIDATED",
    }
)
reliability_head = embedded(
    {
        **binding,
        "type": "deterministic_penalty_v1",
        "base_score": "80.00000000",
        "missing_expert_penalty": "10.00000000",
        "disagreement_penalty": "5.00000000",
        "fit_method": "engineering_fixture_penalty_v1",
        "status": "ENGINEERING_VALIDATED",
    }
)

bundle = {
    "schema": BUNDLE_SCHEMA,
    "stable_id": STABLE_ID,
    "runtime_version": RUNTIME_VERSION,
    "bundle_id": "fixture_spy_20d_v0_0_0_1",
    "created_at": "2026-01-01T00:00:00Z",
    "expires_at": "2027-01-01T00:00:00Z",
    "scope": {"type": "single_instrument_v1", "instrument_id": "FIGI:BBG000BDTBL9"},
    "horizons": [20],
    "calendar_id": "XNYS",
    "label_contract": {
        "id": binding["label_contract_id"],
        "signal_price": "close_t",
        "entry_price": "open_t_plus_1",
        "exit_price": "open_t_plus_21",
        "hurdle": "0",
    },
    "cost_contract": cost,
    "feature_contracts": feature_contracts,
    "experts": experts,
    "admissible_expert_sets": admissible_sets,
    "baseline": baseline,
    "calibration": calibration,
    "magnitude_head": magnitude_head,
    "timing_head": timing_head,
    "economic_edge_head": economic_edge_head,
    "reliability_head": reliability_head,
    "usage_policy": {
        "RESEARCH": {"minimum_head_status": "ENGINEERING_VALIDATED", "minimum_trust_assurance": "NONE"},
        "SHADOW": {"minimum_head_status": "OOS_VALIDATED", "minimum_trust_assurance": "HOST_POLICY_BOUND"},
        "DECISION_SUPPORT": {"minimum_head_status": "OUTCOME_PROVEN", "minimum_trust_assurance": "CRYPTOGRAPHICALLY_VERIFIED"},
    },
    "runtime_limits": {"max_features": 32, "max_experts": 8, "max_buckets": 16, "max_batch": 64},
}
bundle["model_set_sha256"] = sha256_hex({key: copy.deepcopy(bundle[key]) for key in MODEL_PAYLOAD_KEYS})

promotion_heads = {}
for logical, source in {
    "baseline": baseline,
    "direction": calibration,
    "magnitude": magnitude_head,
    "timing": timing_head,
    "economic_edge": economic_edge_head,
    "reliability": reliability_head,
}.items():
    promotion_heads[logical] = {
        "status": source["status"],
        "effective_sample_size": 0,
        "oos_predictions_sha256": None,
        "untouched_holdout_sha256": None,
        "evaluation_start": None,
        "evaluation_end": None,
        "cost_stress_2x_pass": False,
    }

promotion = {
    "schema": PROMOTION_SCHEMA,
    "receipt_id": "fixture_promotion_receipt_v0_0_0_1",
    "subject_model_set_sha256": bundle["model_set_sha256"],
    "evidence_set_sha256": sha256_hex({"type": "synthetic_engineering_fixture", "version": "0.0.0.1"}),
    "trial_ledger_sha256": sha256_hex({"trials": [], "note": "no outcome claim"}),
    "heads": promotion_heads,
}
bundle["promotion_evidence"] = embedded(promotion, key="receipt_sha256")
bundle["payload_sha256"] = sha256_hex(bundle)

trust_context_shadow = {
    "schema": TRUST_SCHEMA,
    "source": "HOST_INJECTED_OUT_OF_BAND",
    "policy_id": "fixture_host_policy_v1",
    "authority_id": "host:efs_release_controller",
    "assurance_level": "HOST_POLICY_BOUND",
    "allowed_usage_modes": ["SHADOW"],
    "approved_bundle_sha256": bundle["payload_sha256"],
    "approved_promotion_receipt_sha256": bundle["promotion_evidence"]["receipt_sha256"],
    "valid_from": "2026-01-01T00:00:00Z",
    "valid_until": "2027-01-01T00:00:00Z",
}
trust_context_shadow = embedded(trust_context_shadow, key="policy_sha256")


def feature(
    name: str,
    value: str,
    effective_at: str,
    published_at: str,
    available_at: str,
    revision_id: str,
    source: str,
    source_dataset_id: str,
    license_id: str,
    evidence_grade: str,
    temporal_semantics: str,
) -> dict:
    contract = feature_contracts[name]
    record = {
        "name": name,
        "value": value,
        "effective_at": effective_at,
        "published_at": published_at,
        "available_at": available_at,
        "revision_id": revision_id,
        "source": source,
        "source_dataset_id": source_dataset_id,
        "license_id": license_id,
        "evidence_grade": evidence_grade,
        "temporal_semantics": temporal_semantics,
        "unit": contract["unit"],
        "transform_id": contract["transform_id"],
        "transform_sha256": contract["transform_sha256"],
    }
    record["source_record_sha256"] = sha256_hex({
        "source": source,
        "source_dataset_id": source_dataset_id,
        "revision_id": revision_id,
        "effective_at": effective_at,
        "published_at": published_at,
        "available_at": available_at,
        "value": value,
    })
    record["feature_payload_sha256"] = sha256_hex(record)
    return record


request = {
    "schema": REQUEST_SCHEMA,
    "request_id": "fixture_request_001",
    "instrument_id": "FIGI:BBG000BDTBL9",
    "as_of": "2026-07-24T21:00:00Z",
    "horizon": 20,
    "calendar_id": "XNYS",
    "label_contract_id": bundle["label_contract"]["id"],
    "cost_contract_sha256": bundle["cost_contract"]["sha256"],
    "usage_mode": "RESEARCH",
    "features": [
        feature(
            "mom_20",
            "0.08000000",
            "2026-07-24T20:00:00Z",
            "2026-07-24T20:01:00Z",
            "2026-07-24T20:02:00Z",
            "price_20260724",
            "public_fixture_price",
            "dataset:fixture_price_v1",
            "license:public_fixture_v1",
            "POINT_IN_TIME_VERIFIED",
            "MARKET_QUOTE",
        ),
        feature(
            "realized_vol_20",
            "0.18000000",
            "2026-07-24T20:00:00Z",
            "2026-07-24T20:01:00Z",
            "2026-07-24T20:02:00Z",
            "price_20260724",
            "public_fixture_price",
            "dataset:fixture_price_v1",
            "license:public_fixture_v1",
            "POINT_IN_TIME_VERIFIED",
            "OBSERVED_FACT",
        ),
        feature(
            "vix_level",
            "18.00000000",
            "2026-07-24T20:00:00Z",
            "2026-07-24T20:01:00Z",
            "2026-07-24T20:02:00Z",
            "vix_20260724",
            "public_fixture_vix",
            "dataset:fixture_vix_v1",
            "license:public_fixture_v1",
            "SOURCE_VERIFIED",
            "MARKET_QUOTE",
        ),
    ],
}

write_json(ROOT / "fixtures" / "bundle.json", bundle)
write_json(ROOT / "fixtures" / "request.json", request)
write_json(ROOT / "fixtures" / "trust_context_shadow.json", trust_context_shadow)
print(json.dumps({"bundle_sha256": bundle["payload_sha256"], "model_set_sha256": bundle["model_set_sha256"]}, indent=2))

# Point-in-time dataset fixture for deterministic training/evaluation pipeline tests.
def pit_row(
    row_id: str,
    signal_as_of: str,
    label_matured_at: str,
    split: str,
    mom: str,
    vol: str,
    vix: str,
    net_1x: str,
    net_2x: str,
    net_3x: str,
) -> dict:
    row = {
        "row_id": row_id,
        "instrument_id": "FIGI:BBG000BDTBL9",
        "signal_as_of": signal_as_of,
        "label_matured_at": label_matured_at,
        "split": split,
        "label": 1 if net_1x.startswith("+") or (not net_1x.startswith("-") and float(net_1x) > 0) else 0,
        "net_return_1x": net_1x.lstrip("+"),
        "net_return_2x": net_2x.lstrip("+"),
        "net_return_3x": net_3x.lstrip("+"),
        "features": {"mom_20": mom, "realized_vol_20": vol, "vix_level": vix},
        "source_snapshot_sha256": sha256_hex({"fixture": "pit_source_v1", "row_id": row_id}),
    }
    row["row_payload_sha256"] = sha256_hex(row)
    return row


pit_dataset = {
    "schema": "efs.pit_training_dataset.v1",
    "dataset_id": "fixture_spy_pit_20d_v1",
    "created_at": "2026-01-01T00:00:00Z",
    "calendar_id": "XNYS",
    "horizon": 20,
    "label_contract_id": bundle["label_contract"]["id"],
    "cost_contract_sha256": bundle["cost_contract"]["sha256"],
    "label_hurdle": "0",
    "scope": {"type": "single_instrument_v1", "instrument_id": "FIGI:BBG000BDTBL9"},
    "feature_names": ["mom_20", "realized_vol_20", "vix_level"],
    "rows": [
        pit_row("r001", "2025-01-02T21:00:00Z", "2025-02-03T21:00:00Z", "TRAIN", "-0.12", "0.35", "32", "-0.08", "-0.081", "-0.082"),
        pit_row("r002", "2025-01-03T21:00:00Z", "2025-02-04T21:00:00Z", "TRAIN", "0.10", "0.15", "16", "0.07", "0.069", "0.068"),
        pit_row("r003", "2025-01-06T21:00:00Z", "2025-02-05T21:00:00Z", "TRAIN", "-0.07", "0.28", "28", "-0.04", "-0.041", "-0.042"),
        pit_row("r004", "2025-01-07T21:00:00Z", "2025-02-06T21:00:00Z", "TRAIN", "0.08", "0.17", "18", "0.05", "0.049", "0.048"),
        pit_row("r005", "2025-03-03T21:00:00Z", "2025-04-02T21:00:00Z", "CALIBRATION", "-0.09", "0.30", "30", "-0.06", "-0.061", "-0.062"),
        pit_row("r006", "2025-03-04T21:00:00Z", "2025-04-03T21:00:00Z", "CALIBRATION", "0.12", "0.14", "15", "0.08", "0.079", "0.078"),
        pit_row("r007", "2025-03-05T21:00:00Z", "2025-04-04T21:00:00Z", "CALIBRATION", "-0.04", "0.25", "25", "-0.02", "-0.021", "-0.022"),
        pit_row("r008", "2025-03-06T21:00:00Z", "2025-04-07T21:00:00Z", "CALIBRATION", "0.06", "0.18", "19", "0.04", "0.039", "0.038"),
        pit_row("r009", "2025-05-01T21:00:00Z", "2025-06-02T21:00:00Z", "HOLDOUT", "-0.11", "0.33", "31", "-0.07", "-0.071", "-0.072"),
        pit_row("r010", "2025-05-02T21:00:00Z", "2025-06-03T21:00:00Z", "HOLDOUT", "0.11", "0.16", "17", "0.06", "0.059", "0.058"),
        pit_row("r011", "2025-05-05T21:00:00Z", "2025-06-04T21:00:00Z", "HOLDOUT", "-0.05", "0.27", "27", "-0.03", "-0.031", "-0.032"),
        pit_row("r012", "2025-05-06T21:00:00Z", "2025-06-05T21:00:00Z", "HOLDOUT", "0.09", "0.17", "18", "0.05", "0.049", "0.048"),
    ],
}
pit_dataset["payload_sha256"] = sha256_hex(pit_dataset)
write_json(ROOT / "fixtures" / "pit_dataset.json", pit_dataset)

training_config = {
    "schema": "efs.deterministic_training_config.v1",
    "config_id": "fixture_linear_direction_v1",
    "feature_names": ["mom_20", "realized_vol_20", "vix_level"],
    "iterations": 160,
    "learning_rate": "0.08",
    "l2": "0.01",
    "calibration_iterations": 120,
    "calibration_learning_rate": "0.05",
    "score_clip": "30",
    "probability_clip": "0.0001",
}
training_config["config_sha256"] = sha256_hex(training_config)
write_json(ROOT / "fixtures" / "training_config.json", training_config)
