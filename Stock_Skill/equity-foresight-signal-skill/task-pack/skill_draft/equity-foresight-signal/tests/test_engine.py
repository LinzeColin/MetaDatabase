from __future__ import annotations

import ast
import copy
import json
import os
import socket
import subprocess
import sys
import tracemalloc
import unittest
from decimal import Decimal
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from equity_foresight_signal import EFSError, batch_evaluate, evaluate, self_check, validate_bundle
from equity_foresight_signal.canonical import canonical_json_bytes, decimal_from, sha256_hex, strict_json_loads
from equity_foresight_signal.engine import HEAD_STATUS_MAP, MODEL_PAYLOAD_KEYS, PROMOTION_SCHEMA, TRUST_SCHEMA


def load(name: str):
    return strict_json_loads((ROOT / "fixtures" / name).read_bytes())


def embedded(value: dict, key: str = "artifact_sha256") -> dict:
    result = copy.deepcopy(value)
    result.pop(key, None)
    result[key] = sha256_hex(result)
    return result


def payload_only(bundle: dict) -> dict:
    result = copy.deepcopy(bundle)
    result.pop("payload_sha256", None)
    result["payload_sha256"] = sha256_hex(result)
    return result


def rebuild_bundle(bundle: dict) -> dict:
    result = copy.deepcopy(bundle)
    result["cost_contract"] = embedded(result["cost_contract"], "sha256")
    result["feature_contracts"] = {name: embedded(item) for name, item in result["feature_contracts"].items()}
    result["experts"] = {name: embedded(item) for name, item in result["experts"].items()}
    result["admissible_expert_sets"] = [embedded(item) for item in result["admissible_expert_sets"]]
    for key in ("baseline", "calibration", "magnitude_head", "timing_head", "economic_edge_head", "reliability_head"):
        result[key]["cost_contract_sha256"] = result["cost_contract"]["sha256"]
        result[key] = embedded(result[key])
    result["model_set_sha256"] = sha256_hex({key: copy.deepcopy(result[key]) for key in MODEL_PAYLOAD_KEYS})
    promotion = copy.deepcopy(result["promotion_evidence"])
    promotion["schema"] = PROMOTION_SCHEMA
    promotion["subject_model_set_sha256"] = result["model_set_sha256"]
    for logical, bundle_key in HEAD_STATUS_MAP.items():
        status = result[bundle_key]["status"]
        head = promotion["heads"][logical]
        head["status"] = status
        if status in {"OOS_VALIDATED", "OUTCOME_PROVEN"}:
            head["effective_sample_size"] = max(int(head.get("effective_sample_size") or 0), 500)
            head["oos_predictions_sha256"] = sha256_hex({"head": logical, "type": "fixture_oos"})
            head["evaluation_start"] = "2015-01-01T00:00:00Z"
            head["evaluation_end"] = "2025-12-31T00:00:00Z"
        else:
            head["effective_sample_size"] = 0
            head["oos_predictions_sha256"] = None
            head["evaluation_start"] = None
            head["evaluation_end"] = None
        if status == "OUTCOME_PROVEN":
            head["untouched_holdout_sha256"] = sha256_hex({"head": logical, "type": "fixture_holdout"})
            head["cost_stress_2x_pass"] = True
        else:
            head["untouched_holdout_sha256"] = None
            head["cost_stress_2x_pass"] = False
    result["promotion_evidence"] = embedded(promotion, "receipt_sha256")
    result.pop("payload_sha256", None)
    result["payload_sha256"] = sha256_hex(result)
    return result


def promote(bundle: dict, status: str) -> dict:
    result = copy.deepcopy(bundle)
    for expert in result["experts"].values():
        expert["status"] = status
        expert["fit_method"] = "walk_forward_oof_linear_v1"
    for expert_set in result["admissible_expert_sets"]:
        expert_set["status"] = status
        expert_set["fit_method"] = "walk_forward_oof_aggregator_v1"
    for key in ("baseline", "calibration", "magnitude_head", "timing_head", "economic_edge_head", "reliability_head"):
        result[key]["status"] = status
    result["baseline"]["estimation_method"] = "walk_forward_null_baseline_v1"
    result["calibration"]["fit_method"] = "walk_forward_oof_platt_v1"
    result["magnitude_head"]["fit_method"] = "walk_forward_oof_quantile_v1"
    result["timing_head"]["fit_method"] = "walk_forward_oof_competing_risk_v1"
    result["economic_edge_head"]["fit_method"] = "walk_forward_oof_expected_net_return_v1"
    result["reliability_head"]["fit_method"] = "walk_forward_oof_reliability_v1"
    return rebuild_bundle(result)


def trust_for(bundle: dict, assurance: str = "HOST_POLICY_BOUND", modes: list[str] | None = None) -> dict:
    modes = modes or ["SHADOW"]
    context = {
        "schema": TRUST_SCHEMA,
        "source": "HOST_INJECTED_OUT_OF_BAND",
        "policy_id": "fixture_host_policy_v1",
        "authority_id": "host:efs_release_controller",
        "assurance_level": assurance,
        "allowed_usage_modes": modes,
        "approved_bundle_sha256": bundle["payload_sha256"],
        "approved_promotion_receipt_sha256": bundle["promotion_evidence"]["receipt_sha256"],
        "valid_from": "2026-01-01T00:00:00Z",
        "valid_until": "2027-01-01T00:00:00Z",
    }
    return embedded(context, "policy_sha256")



def rehash_feature(item: dict) -> dict:
    result = copy.deepcopy(item)
    result.pop("feature_payload_sha256", None)
    result["feature_payload_sha256"] = sha256_hex(result)
    return result


def scheduled_feature(bundle: dict) -> dict:
    contract = bundle["feature_contracts"]["earnings_date_known"]
    item = {
        "name": "earnings_date_known",
        "value": "1",
        "effective_at": "2026-08-01T00:00:00Z",
        "published_at": "2026-07-20T00:00:00Z",
        "available_at": "2026-07-20T00:01:00Z",
        "revision_id": "schedule_1",
        "source": "public_fixture_calendar",
        "source_dataset_id": "dataset:fixture_calendar_v1",
        "license_id": "license:public_fixture_v1",
        "evidence_grade": "SOURCE_VERIFIED",
        "temporal_semantics": "SCHEDULED_FUTURE",
        "unit": contract["unit"],
        "transform_id": contract["transform_id"],
        "transform_sha256": contract["transform_sha256"],
    }
    item["source_record_sha256"] = sha256_hex(item)
    item["feature_payload_sha256"] = sha256_hex(item)
    return item


class EngineTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.bundle = load("bundle.json")
        cls.request = load("request.json")
        cls.shadow_trust = load("trust_context_shadow.json")

    def test_001_bundle_validates(self):
        self.assertTrue(validate_bundle(self.bundle)["valid"])

    def test_002_golden_research_forecast(self):
        self.assertEqual(evaluate(self.request, self.bundle)["status"], "FORECAST")

    def test_003_unproven_direction_not_published(self):
        result = evaluate(self.request, self.bundle)
        self.assertIsNone(result["prob_up"])
        self.assertIsNotNone(result["candidate_prob_up"])

    def test_004_unproven_baseline_not_published(self):
        result = evaluate(self.request, self.bundle)
        self.assertIsNone(result["base_prob"])
        self.assertIsNotNone(result["candidate_base_prob"])

    def test_005_unproven_efs_not_published(self):
        result = evaluate(self.request, self.bundle)
        self.assertIsNone(result["efs"])
        self.assertIsNotNone(result["candidate_efs"])

    def test_006_unproven_magnitude_not_published(self):
        result = evaluate(self.request, self.bundle)
        self.assertIsNone(result["expected_move"])
        self.assertIsNotNone(result["candidate_expected_move"])

    def test_007_unproven_timing_not_published(self):
        result = evaluate(self.request, self.bundle)
        self.assertIsNone(result["timing"])
        self.assertIsNotNone(result["candidate_timing"])

    def test_008_unproven_reliability_not_published(self):
        result = evaluate(self.request, self.bundle)
        self.assertIsNone(result["reliability"])
        self.assertIsNotNone(result["candidate_reliability"])

    def test_009_candidate_semantics_explicit(self):
        result = evaluate(self.request, self.bundle)
        self.assertEqual(result["probability_semantics"], "CANDIDATE_SCORE_NOT_A_VALIDATED_PROBABILITY")
        self.assertIn("ENGINEERING_CANDIDATE", result["magnitude_semantics"])
        self.assertIn("ENGINEERING_CANDIDATE", result["timing_semantics"])

    def test_010_deterministic_1000(self):
        hashes = {evaluate(self.request, self.bundle)["result_sha256"] for _ in range(1000)}
        self.assertEqual(len(hashes), 1)

    def test_011_bundle_payload_tamper(self):
        bundle = copy.deepcopy(self.bundle)
        bundle["baseline"]["prob_up"] = "0.7"
        self.assertEqual(evaluate(self.request, bundle)["reason_code"], "BUNDLE_INTEGRITY_FAILED")

    def test_012_model_set_tamper(self):
        bundle = copy.deepcopy(self.bundle)
        bundle["model_set_sha256"] = "0" * 64
        bundle = payload_only(bundle)
        self.assertEqual(evaluate(self.request, bundle)["reason_code"], "BUNDLE_INTEGRITY_FAILED")

    def test_013_promotion_subject_mismatch(self):
        bundle = copy.deepcopy(self.bundle)
        bundle["promotion_evidence"]["subject_model_set_sha256"] = "0" * 64
        bundle["promotion_evidence"] = embedded(bundle["promotion_evidence"], "receipt_sha256")
        bundle = payload_only(bundle)
        self.assertEqual(evaluate(self.request, bundle)["reason_code"], "PROMOTION_EVIDENCE_INVALID")

    def test_014_promotion_receipt_tamper(self):
        bundle = copy.deepcopy(self.bundle)
        bundle["promotion_evidence"]["receipt_sha256"] = "0" * 64
        bundle = payload_only(bundle)
        self.assertEqual(evaluate(self.request, bundle)["reason_code"], "BUNDLE_INTEGRITY_FAILED")

    def test_015_expert_artifact_tamper(self):
        bundle = copy.deepcopy(self.bundle)
        bundle["experts"]["price"]["weights"]["mom_20"] = "9"
        bundle = payload_only(bundle)
        self.assertEqual(evaluate(self.request, bundle)["reason_code"], "BUNDLE_INTEGRITY_FAILED")

    def test_016_feature_contract_artifact_tamper(self):
        bundle = copy.deepcopy(self.bundle)
        bundle["feature_contracts"]["mom_20"]["unit"] = "percent"
        bundle = payload_only(bundle)
        self.assertEqual(evaluate(self.request, bundle)["reason_code"], "BUNDLE_INTEGRITY_FAILED")

    def test_017_aggregator_artifact_tamper(self):
        bundle = copy.deepcopy(self.bundle)
        bundle["admissible_expert_sets"][0]["aggregator"]["weights"]["price"] = "1"
        bundle = payload_only(bundle)
        self.assertEqual(evaluate(self.request, bundle)["reason_code"], "BUNDLE_INTEGRITY_FAILED")

    def test_018_head_artifact_tamper(self):
        bundle = copy.deepcopy(self.bundle)
        bundle["magnitude_head"]["aggregate_slope"] = "2"
        bundle = payload_only(bundle)
        self.assertEqual(evaluate(self.request, bundle)["reason_code"], "BUNDLE_INTEGRITY_FAILED")

    def test_019_cost_contract_tamper(self):
        bundle = copy.deepcopy(self.bundle)
        bundle["cost_contract"]["commission_bps"] = "1"
        bundle = payload_only(bundle)
        self.assertEqual(evaluate(self.request, bundle)["reason_code"], "BUNDLE_INTEGRITY_FAILED")

    def test_020_wrong_instrument(self):
        request = copy.deepcopy(self.request)
        request["instrument_id"] = "FIGI:OTHER"
        self.assertEqual(evaluate(request, self.bundle)["reason_code"], "UNIVERSE_MISMATCH")

    def test_021_non_ascii_machine_id_rejected(self):
        request = copy.deepcopy(self.request)
        request["request_id"] = "预测_1"
        self.assertEqual(evaluate(request, self.bundle)["reason_code"], "CONTRACT_INVALID")

    def test_022_wrong_horizon(self):
        request = copy.deepcopy(self.request)
        request["horizon"] = 5
        self.assertEqual(evaluate(request, self.bundle)["reason_code"], "HORIZON_UNSUPPORTED")

    def test_023_wrong_calendar(self):
        request = copy.deepcopy(self.request)
        request["calendar_id"] = "XASX"
        self.assertEqual(evaluate(request, self.bundle)["reason_code"], "CONTRACT_INVALID")

    def test_024_wrong_label(self):
        request = copy.deepcopy(self.request)
        request["label_contract_id"] = "wrong"
        self.assertEqual(evaluate(request, self.bundle)["reason_code"], "CONTRACT_INVALID")

    def test_025_wrong_cost(self):
        request = copy.deepcopy(self.request)
        request["cost_contract_sha256"] = "0" * 64
        self.assertEqual(evaluate(request, self.bundle)["reason_code"], "CONTRACT_INVALID")

    def test_026_bundle_expired(self):
        request = copy.deepcopy(self.request)
        request["as_of"] = "2028-01-01T00:00:00Z"
        self.assertEqual(evaluate(request, self.bundle)["reason_code"], "BUNDLE_EXPIRED")

    def test_027_calibration_expired(self):
        bundle = copy.deepcopy(self.bundle)
        bundle["calibration"]["expires_at"] = "2026-06-01T00:00:00Z"
        bundle = rebuild_bundle(bundle)
        self.assertEqual(evaluate(self.request, bundle)["reason_code"], "CALIBRATION_EXPIRED")

    def test_028_future_available_at(self):
        request = copy.deepcopy(self.request)
        request["features"][0]["available_at"] = "2026-07-25T00:00:00Z"
        self.assertEqual(evaluate(request, self.bundle)["reason_code"], "TEMPORAL_LEAKAGE")

    def test_029_future_published_at(self):
        request = copy.deepcopy(self.request)
        request["features"][0]["published_at"] = "2026-07-25T00:00:00Z"
        request["features"][0]["available_at"] = "2026-07-25T00:00:00Z"
        self.assertEqual(evaluate(request, self.bundle)["reason_code"], "TEMPORAL_LEAKAGE")

    def test_030_future_observed_fact(self):
        request = copy.deepcopy(self.request)
        request["features"][1]["effective_at"] = "2026-07-25T00:00:00Z"
        self.assertEqual(evaluate(request, self.bundle)["reason_code"], "TEMPORAL_LEAKAGE")

    def test_031_scheduled_future_allowed(self):
        request = copy.deepcopy(self.request)
        request["features"].append(scheduled_feature(self.bundle))
        self.assertEqual(evaluate(request, self.bundle)["status"], "FORECAST")

    def test_032_scheduled_future_not_future_rejected(self):
        request = copy.deepcopy(self.request)
        item = scheduled_feature(self.bundle)
        item["effective_at"] = "2026-07-01T00:00:00Z"
        request["features"].append(item)
        self.assertEqual(evaluate(request, self.bundle)["reason_code"], "CONTRACT_INVALID")

    def test_033_temporal_contract_mismatch(self):
        request = copy.deepcopy(self.request)
        request["features"][0]["temporal_semantics"] = "SCHEDULED_FUTURE"
        request["features"][0]["effective_at"] = "2026-08-01T00:00:00Z"
        self.assertEqual(evaluate(request, self.bundle)["reason_code"], "FEATURE_CONTRACT_MISMATCH")

    def test_034_revision_id_required(self):
        request = copy.deepcopy(self.request)
        request["features"][1]["revision_id"] = ""
        self.assertEqual(evaluate(request, self.bundle)["reason_code"], "CONTRACT_INVALID")

    def test_035_data_conflict(self):
        request = copy.deepcopy(self.request)
        request["features"][0]["conflict"] = True
        request["features"][0] = rehash_feature(request["features"][0])
        self.assertEqual(evaluate(request, self.bundle)["reason_code"], "DATA_CONFLICT")

    def test_036_stale_macro_drops_to_price_only(self):
        request = copy.deepcopy(self.request)
        for key in ("effective_at", "published_at", "available_at"):
            request["features"][2][key] = "2026-01-01T00:00:00Z"
        request["features"][2] = rehash_feature(request["features"][2])
        self.assertEqual(evaluate(request, self.bundle)["active_expert_set"], "price_only_v1")

    def test_037_stale_all_abstains(self):
        request = copy.deepcopy(self.request)
        for index, feature in enumerate(request["features"]):
            for key in ("effective_at", "published_at", "available_at"):
                feature[key] = "2026-01-01T00:00:00Z"
            request["features"][index] = rehash_feature(feature)
        self.assertEqual(evaluate(request, self.bundle)["reason_code"], "EXPERT_SET_UNVALIDATED")

    def test_038_low_grade_drops_price(self):
        request = copy.deepcopy(self.request)
        request["features"][0]["evidence_grade"] = "RAW"
        request["features"][0] = rehash_feature(request["features"][0])
        self.assertEqual(evaluate(request, self.bundle)["reason_code"], "EXPERT_SET_UNVALIDATED")

    def test_039_missing_macro_uses_frozen_subset(self):
        request = copy.deepcopy(self.request)
        request["features"] = request["features"][:2]
        self.assertEqual(evaluate(request, self.bundle)["active_expert_set"], "price_only_v1")

    def test_040_missing_price_not_silently_renormalized(self):
        request = copy.deepcopy(self.request)
        request["features"] = request["features"][2:]
        self.assertEqual(evaluate(request, self.bundle)["reason_code"], "EXPERT_SET_UNVALIDATED")

    def test_041_unknown_feature_rejected(self):
        request = copy.deepcopy(self.request)
        item = copy.deepcopy(request["features"][0])
        item["name"] = "unknown_feature"
        request["features"].append(item)
        self.assertEqual(evaluate(request, self.bundle)["reason_code"], "FEATURE_CONTRACT_MISMATCH")

    def test_042_unit_mismatch(self):
        request = copy.deepcopy(self.request)
        request["features"][0]["unit"] = "percent"
        self.assertEqual(evaluate(request, self.bundle)["reason_code"], "FEATURE_CONTRACT_MISMATCH")

    def test_043_transform_id_mismatch(self):
        request = copy.deepcopy(self.request)
        request["features"][0]["transform_id"] = "other_v1"
        self.assertEqual(evaluate(request, self.bundle)["reason_code"], "FEATURE_CONTRACT_MISMATCH")

    def test_044_transform_hash_mismatch(self):
        request = copy.deepcopy(self.request)
        request["features"][0]["transform_sha256"] = "0" * 64
        self.assertEqual(evaluate(request, self.bundle)["reason_code"], "FEATURE_CONTRACT_MISMATCH")

    def test_045_feature_range_violation(self):
        request = copy.deepcopy(self.request)
        request["features"][2]["value"] = "999"
        self.assertEqual(evaluate(request, self.bundle)["reason_code"], "FEATURE_CONTRACT_MISMATCH")

    def test_046_license_id_required(self):
        request = copy.deepcopy(self.request)
        request["features"][0]["license_id"] = ""
        self.assertEqual(evaluate(request, self.bundle)["reason_code"], "CONTRACT_INVALID")

    def test_047_source_record_hash_format(self):
        request = copy.deepcopy(self.request)
        request["features"][0]["source_record_sha256"] = "not-a-hash"
        self.assertEqual(evaluate(request, self.bundle)["reason_code"], "CONTRACT_INVALID")

    def test_048_duplicate_feature(self):
        request = copy.deepcopy(self.request)
        request["features"].append(copy.deepcopy(request["features"][0]))
        self.assertEqual(evaluate(request, self.bundle)["reason_code"], "CONTRACT_INVALID")

    def test_049_shadow_requires_calibration(self):
        request = copy.deepcopy(self.request)
        request["usage_mode"] = "SHADOW"
        self.assertEqual(evaluate(request, self.bundle, self.shadow_trust)["reason_code"], "OOS_VALIDATION_NOT_PROVEN")

    def test_050_calibrated_shadow_requires_trust_context(self):
        bundle = promote(self.bundle, "OOS_VALIDATED")
        request = copy.deepcopy(self.request)
        request["usage_mode"] = "SHADOW"
        self.assertEqual(evaluate(request, bundle)["reason_code"], "TRUST_CONTEXT_REQUIRED")

    def test_051_calibrated_shadow_with_valid_trust(self):
        bundle = promote(self.bundle, "OOS_VALIDATED")
        request = copy.deepcopy(self.request)
        request["usage_mode"] = "SHADOW"
        result = evaluate(request, bundle, trust_for(bundle))
        self.assertEqual(result["status"], "FORECAST")
        self.assertIsNotNone(result["prob_up"])
        self.assertIsNotNone(result["expected_move"])
        self.assertIsNotNone(result["timing"])
        self.assertIsNotNone(result["reliability"])

    def test_052_trust_wrong_bundle(self):
        bundle = promote(self.bundle, "OOS_VALIDATED")
        request = copy.deepcopy(self.request)
        request["usage_mode"] = "SHADOW"
        trust = trust_for(bundle)
        trust["approved_bundle_sha256"] = "0" * 64
        trust = embedded(trust, "policy_sha256")
        self.assertEqual(evaluate(request, bundle, trust)["reason_code"], "BUNDLE_NOT_APPROVED")

    def test_053_trust_wrong_receipt(self):
        bundle = promote(self.bundle, "OOS_VALIDATED")
        request = copy.deepcopy(self.request)
        request["usage_mode"] = "SHADOW"
        trust = trust_for(bundle)
        trust["approved_promotion_receipt_sha256"] = "0" * 64
        trust = embedded(trust, "policy_sha256")
        self.assertEqual(evaluate(request, bundle, trust)["reason_code"], "BUNDLE_NOT_APPROVED")

    def test_054_trust_expired(self):
        bundle = promote(self.bundle, "OOS_VALIDATED")
        request = copy.deepcopy(self.request)
        request["usage_mode"] = "SHADOW"
        trust = trust_for(bundle)
        trust["valid_until"] = "2026-01-02T00:00:00Z"
        trust = embedded(trust, "policy_sha256")
        self.assertEqual(evaluate(request, bundle, trust)["reason_code"], "TRUST_CONTEXT_EXPIRED")

    def test_055_trust_payload_tamper(self):
        bundle = promote(self.bundle, "OOS_VALIDATED")
        request = copy.deepcopy(self.request)
        request["usage_mode"] = "SHADOW"
        trust = trust_for(bundle)
        trust["authority_id"] = "host:attacker"
        self.assertEqual(evaluate(request, bundle, trust)["reason_code"], "BUNDLE_INTEGRITY_FAILED")

    def test_056_trust_source_must_be_out_of_band(self):
        bundle = promote(self.bundle, "OOS_VALIDATED")
        request = copy.deepcopy(self.request)
        request["usage_mode"] = "SHADOW"
        trust = trust_for(bundle)
        trust["source"] = "REQUEST_EMBEDDED"
        trust = embedded(trust, "policy_sha256")
        self.assertEqual(evaluate(request, bundle, trust)["reason_code"], "TRUST_CONTEXT_INVALID")

    def test_057_decision_support_is_not_release_authorized(self):
        bundle = promote(self.bundle, "OUTCOME_PROVEN")
        request = copy.deepcopy(self.request)
        request["usage_mode"] = "DECISION_SUPPORT"
        trust = trust_for(bundle, "HOST_POLICY_BOUND", ["DECISION_SUPPORT"])
        self.assertEqual(evaluate(request, bundle, trust)["reason_code"], "CAPABILITY_NOT_RELEASED")

    def test_058_calibrated_promotion_needs_sample_support(self):
        bundle = promote(self.bundle, "OOS_VALIDATED")
        bundle["promotion_evidence"]["heads"]["direction"]["effective_sample_size"] = 1
        bundle["promotion_evidence"] = embedded(bundle["promotion_evidence"], "receipt_sha256")
        bundle = payload_only(bundle)
        self.assertEqual(evaluate(self.request, bundle)["reason_code"], "PROMOTION_EVIDENCE_INVALID")

    def test_059_outcome_promotion_needs_holdout(self):
        bundle = promote(self.bundle, "OUTCOME_PROVEN")
        bundle["promotion_evidence"]["heads"]["timing"]["untouched_holdout_sha256"] = None
        bundle["promotion_evidence"] = embedded(bundle["promotion_evidence"], "receipt_sha256")
        bundle = payload_only(bundle)
        self.assertEqual(evaluate(self.request, bundle)["reason_code"], "PROMOTION_EVIDENCE_INVALID")

    def test_060_promotion_status_mismatch(self):
        bundle = copy.deepcopy(self.bundle)
        bundle["calibration"]["status"] = "OOS_VALIDATED"
        bundle["calibration"] = embedded(bundle["calibration"])
        bundle["model_set_sha256"] = sha256_hex({key: copy.deepcopy(bundle[key]) for key in MODEL_PAYLOAD_KEYS})
        bundle["promotion_evidence"]["subject_model_set_sha256"] = bundle["model_set_sha256"]
        bundle["promotion_evidence"] = embedded(bundle["promotion_evidence"], "receipt_sha256")
        bundle = payload_only(bundle)
        self.assertEqual(evaluate(self.request, bundle)["reason_code"], "PROMOTION_EVIDENCE_INVALID")

    def test_061_candidate_efs_is_probability_percent(self):
        result = evaluate(self.request, self.bundle)
        expected = Decimal(result["candidate_prob_up"]) * Decimal(100)
        self.assertEqual(Decimal(result["candidate_efs"]), expected)
        self.assertEqual(result["efs_semantics"], "UP_PROBABILITY_PERCENT_0_TO_100")

    def test_062_candidate_magnitude_ordered(self):
        move = evaluate(self.request, self.bundle)["candidate_expected_move"]
        self.assertLessEqual(Decimal(move["p10"]), Decimal(move["p50"]))
        self.assertLessEqual(Decimal(move["p50"]), Decimal(move["p90"]))

    def test_063_quantile_crossing_rejected(self):
        bundle = copy.deepcopy(self.bundle)
        bundle["magnitude_head"]["base_quantiles"] = {"p10": "0.1", "p50": "0", "p90": "0.2"}
        bundle = rebuild_bundle(bundle)
        self.assertEqual(evaluate(self.request, bundle)["reason_code"], "CONTRACT_INVALID")

    def test_064_timing_sums_to_one(self):
        timing = evaluate(self.request, self.bundle)["candidate_timing"]
        total = Decimal(timing["barrier_up"]) + Decimal(timing["barrier_down"]) + Decimal(timing["timeout"])
        self.assertAlmostEqual(float(total), 1.0, places=7)

    def test_065_timing_buckets_contiguous(self):
        bundle = copy.deepcopy(self.bundle)
        bundle["timing_head"]["buckets"][1]["start_day"] = 7
        bundle = rebuild_bundle(bundle)
        self.assertEqual(evaluate(self.request, bundle)["reason_code"], "CONTRACT_INVALID")

    def test_066_timing_ends_at_horizon(self):
        bundle = copy.deepcopy(self.bundle)
        bundle["timing_head"]["buckets"][-1]["end_day"] = 19
        bundle = rebuild_bundle(bundle)
        self.assertEqual(evaluate(self.request, bundle)["reason_code"], "CONTRACT_INVALID")

    def test_067_timing_barriers_straddle_zero(self):
        bundle = copy.deepcopy(self.bundle)
        bundle["timing_head"]["down_hurdle"] = "0.01"
        bundle = rebuild_bundle(bundle)
        self.assertEqual(evaluate(self.request, bundle)["reason_code"], "CONTRACT_INVALID")

    def test_068_duplicate_json_key(self):
        self.assertEqual(evaluate('{"schema":"x","schema":"y"}', self.bundle)["reason_code"], "CONTRACT_INVALID")

    def test_069_unicode_equivalent_json_key(self):
        with self.assertRaises(EFSError):
            strict_json_loads('{"caf\\u00e9":1,"cafe\\u0301":2}')

    def test_070_nan_rejected(self):
        with self.assertRaises(EFSError):
            strict_json_loads('{"x":NaN}')

    def test_071_infinity_rejected(self):
        with self.assertRaises(EFSError):
            strict_json_loads('{"x":Infinity}')

    def test_072_deep_json_rejected(self):
        raw = "0"
        for _ in range(40):
            raw = "[" + raw + "]"
        with self.assertRaises(EFSError):
            strict_json_loads(raw)

    def test_073_large_array_rejected(self):
        with self.assertRaises(EFSError):
            strict_json_loads(json.dumps([0] * 5000))

    def test_074_long_string_rejected(self):
        with self.assertRaises(EFSError):
            strict_json_loads(json.dumps({"x": "a" * 17000}))

    def test_075_huge_integer_rejected(self):
        with self.assertRaises(EFSError):
            strict_json_loads('{"x":10000000000000000000}')

    def test_076_huge_decimal_exponent_rejected(self):
        with self.assertRaises(EFSError):
            decimal_from("1e100", "x")

    def test_077_tiny_decimal_exponent_rejected(self):
        with self.assertRaises(EFSError):
            decimal_from("1e-100", "x")

    def test_078_oversize_request(self):
        self.assertEqual(evaluate(b" " * 256001, self.bundle)["reason_code"], "RESOURCE_LIMIT")

    def test_079_unsafe_model_type_rejected(self):
        bundle = copy.deepcopy(self.bundle)
        bundle["experts"]["price"]["model_type"] = "pickle"
        bundle = rebuild_bundle(bundle)
        self.assertEqual(evaluate(self.request, bundle)["reason_code"], "CONTRACT_INVALID")

    def test_080_no_remote_visualization_resources(self):
        result = evaluate(self.request, self.bundle)
        self.assertEqual(result["visualization"]["remote_resources"], [])
        self.assertNotIn("http", json.dumps(result["visualization"]))

    def test_081_no_order_fields(self):
        raw = json.dumps(evaluate(self.request, self.bundle)).lower()
        for token in ("order_id", "broker", "position_size", "place_order"):
            self.assertNotIn(token, raw)

    def test_082_zero_agent_token_metrics(self):
        result = evaluate(self.request, self.bundle)
        self.assertEqual(result["agent_invocations_total"], 0)
        self.assertEqual(result["llm_requests_total"], 0)
        self.assertEqual(result["llm_input_tokens_total"], 0)
        self.assertEqual(result["llm_output_tokens_total"], 0)

    def test_083_no_api_key_required(self):
        with mock.patch.dict(os.environ, {}, clear=True):
            self.assertEqual(evaluate(self.request, self.bundle)["status"], "FORECAST")

    def test_084_network_socket_blocked_still_runs(self):
        with mock.patch.object(socket, "socket", side_effect=AssertionError("network forbidden")):
            self.assertEqual(evaluate(self.request, self.bundle)["status"], "FORECAST")

    def test_085_subprocess_blocked_still_runs(self):
        with mock.patch.object(subprocess, "Popen", side_effect=AssertionError("subprocess forbidden")):
            self.assertEqual(evaluate(self.request, self.bundle)["status"], "FORECAST")

    def test_086_static_forbidden_imports_absent(self):
        forbidden = ("openai", "anthropic", "langchain", "autogen", "crewai", "mcp", "requests", "httpx", "urllib", "socket", "subprocess", "pickle", "joblib")
        source = "\n".join(path.read_text(encoding="utf-8") for path in (ROOT / "equity_foresight_signal").glob("*.py"))
        for name in forbidden:
            self.assertNotRegex(source, rf"(^|\n)\s*(from|import)\s+{name}(\.|\s|$)")

    def test_087_self_check_zero_runtime_dependencies(self):
        profile = self_check()["runtime_profile"]
        self.assertTrue(all(value == 0 for value in profile.values()))

    def test_088_batch_limit(self):
        with self.assertRaises(EFSError):
            batch_evaluate([self.request] * 65, self.bundle)

    def test_089_batch_deterministic(self):
        results = batch_evaluate([self.request, self.request], self.bundle)
        self.assertEqual(results[0]["result_sha256"], results[1]["result_sha256"])

    def test_090_malformed_fuzz_no_uncaught_exception(self):
        for index in range(1000):
            raw = ("{" + ("x" * (index % 29))).encode("utf-8")
            self.assertEqual(evaluate(raw, self.bundle)["status"], "ABSTAIN")

    def test_091_universe_snapshot_valid(self):
        bundle = copy.deepcopy(self.bundle)
        members = ["FIGI:A", "FIGI:B"]
        bundle["scope"] = {"type": "universe_snapshot_v1", "members": members, "snapshot_sha256": sha256_hex(sorted(members))}
        bundle = rebuild_bundle(bundle)
        request = copy.deepcopy(self.request)
        request["instrument_id"] = "FIGI:A"
        request["universe_snapshot_sha256"] = bundle["scope"]["snapshot_sha256"]
        self.assertEqual(evaluate(request, bundle)["status"], "FORECAST")

    def test_092_universe_snapshot_wrong_hash(self):
        bundle = copy.deepcopy(self.bundle)
        members = ["FIGI:A", "FIGI:B"]
        bundle["scope"] = {"type": "universe_snapshot_v1", "members": members, "snapshot_sha256": "0" * 64}
        bundle = rebuild_bundle(bundle)
        self.assertEqual(evaluate(self.request, bundle)["reason_code"], "BUNDLE_INTEGRITY_FAILED")

    def test_093_suspended_expert_not_used(self):
        bundle = copy.deepcopy(self.bundle)
        bundle["experts"]["macro"]["status"] = "SUSPENDED"
        bundle = rebuild_bundle(bundle)
        result = evaluate(self.request, bundle)
        self.assertEqual(result["active_expert_set"], "price_only_v1")
        self.assertIn("macro", result["suspended_experts"])

    def test_094_unsupported_usage_mode(self):
        request = copy.deepcopy(self.request)
        request["usage_mode"] = "LIVE_TRADING"
        self.assertEqual(evaluate(request, self.bundle)["reason_code"], "CONTRACT_INVALID")

    def test_095_request_schema(self):
        request = copy.deepcopy(self.request)
        request["schema"] = "wrong"
        self.assertEqual(evaluate(request, self.bundle)["reason_code"], "CONTRACT_INVALID")

    def test_096_same_bar_execution_rejected(self):
        bundle = copy.deepcopy(self.bundle)
        bundle["label_contract"]["entry_price"] = bundle["label_contract"]["signal_price"]
        bundle = rebuild_bundle(bundle)
        self.assertEqual(evaluate(self.request, bundle)["reason_code"], "CONTRACT_INVALID")

    def test_097_bundle_wrong_runtime(self):
        bundle = copy.deepcopy(self.bundle)
        bundle["runtime_version"] = "999"
        bundle = payload_only(bundle)
        self.assertEqual(evaluate(self.request, bundle)["reason_code"], "CONTRACT_INVALID")

    def test_098_internal_error_fail_closed(self):
        with mock.patch("equity_foresight_signal.engine._timing", side_effect=RuntimeError("boom")):
            result = evaluate(self.request, self.bundle)
        self.assertEqual(result["reason_code"], "INTERNAL_ERROR")
        self.assertNotIn("boom", json.dumps(result))

    def test_099_canonical_hash_key_order(self):
        self.assertEqual(sha256_hex({"a": 1, "b": 2}), sha256_hex({"b": 2, "a": 1}))

    def test_100_resource_memory_small_fixture(self):
        tracemalloc.start()
        for _ in range(100):
            evaluate(self.request, self.bundle)
        _, peak = tracemalloc.get_traced_memory()
        tracemalloc.stop()
        self.assertLess(peak, 3_000_000)

    def test_101_expert_feature_contract_must_exist(self):
        bundle = copy.deepcopy(self.bundle)
        bundle["experts"]["price"]["required_features"].append("undefined")
        bundle["experts"]["price"]["weights"]["undefined"] = "1"
        bundle = rebuild_bundle(bundle)
        self.assertEqual(evaluate(self.request, bundle)["reason_code"], "CONTRACT_INVALID")

    def test_102_costs_non_negative(self):
        bundle = copy.deepcopy(self.bundle)
        bundle["cost_contract"]["commission_bps"] = "-1"
        bundle = rebuild_bundle(bundle)
        self.assertEqual(evaluate(self.request, bundle)["reason_code"], "CONTRACT_INVALID")

    def test_103_research_visualization_has_candidate_only(self):
        layers = evaluate(self.request, self.bundle)["visualization"]
        self.assertIsNotNone(layers["candidate_layers"]["direction"])
        self.assertIsNone(layers["validated_layers"]["direction"])

    def test_104_shadow_visualization_has_validated_layers(self):
        bundle = promote(self.bundle, "OOS_VALIDATED")
        request = copy.deepcopy(self.request)
        request["usage_mode"] = "SHADOW"
        result = evaluate(request, bundle, trust_for(bundle))
        self.assertIsNotNone(result["visualization"]["validated_layers"]["direction"])
        self.assertEqual(result["visualization"]["warnings"], [])

    def test_105_data_quality_binds_license_and_record_hash(self):
        quality = evaluate(self.request, self.bundle)["data_quality"]
        self.assertTrue(quality["source_record_hashes_bound"])
        self.assertTrue(quality["feature_payload_hashes_verified"])
        self.assertTrue(quality["source_dataset_allowlists_enforced"])
        self.assertTrue(quality["license_allowlists_enforced"])
        self.assertTrue(quality["freshness_clocks_enforced"])

    def test_106_request_embedded_trust_is_not_accepted(self):
        bundle = promote(self.bundle, "OOS_VALIDATED")
        request = copy.deepcopy(self.request)
        request["usage_mode"] = "SHADOW"
        request["trust_context"] = trust_for(bundle)
        self.assertEqual(evaluate(request, bundle)["reason_code"], "CONTRACT_INVALID")

    def test_107_head_binding_mismatch(self):
        bundle = copy.deepcopy(self.bundle)
        bundle["timing_head"]["label_contract_id"] = "wrong"
        bundle = rebuild_bundle(bundle)
        self.assertEqual(evaluate(self.request, bundle)["reason_code"], "CONTRACT_INVALID")

    def test_108_feature_contract_range_inverted(self):
        bundle = copy.deepcopy(self.bundle)
        bundle["feature_contracts"]["mom_20"]["min_value"] = "2"
        bundle["feature_contracts"]["mom_20"]["max_value"] = "1"
        bundle = rebuild_bundle(bundle)
        self.assertEqual(evaluate(self.request, bundle)["reason_code"], "CONTRACT_INVALID")

    def test_109_promotion_receipt_is_exposed_for_audit(self):
        result = evaluate(self.request, self.bundle)
        self.assertEqual(result["promotion_receipt_sha256"], self.bundle["promotion_evidence"]["receipt_sha256"])

    def test_110_model_set_hash_is_exposed_for_audit(self):
        result = evaluate(self.request, self.bundle)
        self.assertEqual(result["model_set_sha256"], self.bundle["model_set_sha256"])

    def test_114_disabled_decision_support_fails_before_trust_adapter(self):
        bundle = promote(self.bundle, "OUTCOME_PROVEN")
        request = copy.deepcopy(self.request)
        request["usage_mode"] = "DECISION_SUPPORT"
        trust = trust_for(bundle, "CRYPTOGRAPHICALLY_VERIFIED", ["DECISION_SUPPORT"])
        self.assertEqual(evaluate(request, bundle, trust)["reason_code"], "CAPABILITY_NOT_RELEASED")

    def test_119_no_private_key_artifact_persisted(self):
        forbidden_suffixes = {".key", ".pem", ".p12", ".pfx"}
        files = [path for path in ROOT.rglob("*") if path.is_file() and "__pycache__" not in path.parts]
        self.assertFalse(any(path.suffix.lower() in forbidden_suffixes for path in files))
        runtime_and_fixtures = [path for path in files if "tests" not in path.parts]
        source = "\n".join(path.read_text(encoding="utf-8", errors="ignore") for path in runtime_and_fixtures)
        self.assertNotIn("BEGIN PRIVATE KEY", source)
        self.assertNotIn("private_key_b64", source)

    def test_120_formal_release_has_no_cryptographic_adapter_or_import(self):
        self.assertFalse((ROOT / "equity_foresight_signal" / "trust_ed25519.py").exists())
        source = (ROOT / "equity_foresight_signal" / "engine.py").read_text(encoding="utf-8")
        tree = ast.parse(source)
        imports = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imports.update(alias.name.split(".")[0] for alias in node.names)
            elif isinstance(node, ast.ImportFrom) and node.module:
                imports.add(node.module.split(".")[0])
        self.assertNotIn("cryptography", imports)
        self.assertEqual(evaluate(self.request, self.bundle)["status"], "FORECAST")


    def test_121_unproven_economic_edge_not_published(self):
        result = evaluate(self.request, self.bundle)
        self.assertIsNotNone(result["candidate_expected_net_return"])
        self.assertIsNone(result["expected_net_return"])
        self.assertIsNone(result["positive_economic_edge"])

    def test_122_calibrated_shadow_publishes_economic_edge(self):
        bundle = promote(self.bundle, "OOS_VALIDATED")
        request = copy.deepcopy(self.request)
        request["usage_mode"] = "SHADOW"
        result = evaluate(request, bundle, trust_for(bundle))
        self.assertEqual(result["status"], "FORECAST")
        self.assertIsNotNone(result["expected_net_return"])
        self.assertIsInstance(result["positive_economic_edge"], bool)
        self.assertIsNotNone(result["visualization"]["validated_layers"]["economic_edge"])

    def test_123_high_up_probability_can_have_negative_economic_edge(self):
        bundle = copy.deepcopy(self.bundle)
        bundle["economic_edge_head"]["base_mean_net_return"] = "-0.10000000"
        bundle["calibration"]["b"] = "2.00000000"
        bundle = rebuild_bundle(bundle)
        result = evaluate(self.request, bundle)
        self.assertGreater(Decimal(result["candidate_prob_up"]), Decimal("0.5"))
        self.assertLess(Decimal(result["candidate_expected_net_return"]), Decimal("0"))
        self.assertFalse(result["candidate_positive_economic_edge"])

    def test_124_timeout_is_single_horizon_event(self):
        timing = evaluate(self.request, self.bundle)["candidate_timing"]
        self.assertEqual(timing["timeout_semantics"], "NO_UP_OR_DOWN_BARRIER_TOUCH_BY_HORIZON")
        self.assertTrue(all("timeout" not in bucket for bucket in timing["buckets"]))
        event_mass = sum((Decimal(bucket["event_mass"]) for bucket in timing["buckets"]), Decimal(0))
        self.assertAlmostEqual(float(event_mass + Decimal(timing["timeout"])), 1.0, places=7)

    def test_125_timeout_can_be_most_likely_outcome(self):
        bundle = copy.deepcopy(self.bundle)
        bundle["timing_head"]["timeout_logit"] = "20.00000000"
        bundle = rebuild_bundle(bundle)
        window = evaluate(self.request, bundle)["candidate_timing"]["most_likely_window"]
        self.assertEqual(window["cause"], "timeout")
        self.assertIsNone(window["start_day"])
        self.assertIsNone(window["end_day"])

    def test_126_per_bucket_timeout_is_rejected(self):
        bundle = copy.deepcopy(self.bundle)
        bundle["timing_head"]["buckets"][0]["timeout_logit"] = "0"
        bundle = rebuild_bundle(bundle)
        self.assertEqual(evaluate(self.request, bundle)["reason_code"], "CONTRACT_INVALID")

    def test_127_late_ingestion_does_not_refresh_old_market_quote(self):
        request = copy.deepcopy(self.request)
        request["features"][2]["effective_at"] = "2026-01-01T00:00:00Z"
        request["features"][2]["published_at"] = "2026-07-24T20:01:00Z"
        request["features"][2]["available_at"] = "2026-07-24T20:59:00Z"
        request["features"][2] = rehash_feature(request["features"][2])
        result = evaluate(request, self.bundle)
        self.assertEqual(result["active_expert_set"], "price_only_v1")
        self.assertIn("macro", result["unavailable_experts"])

    def test_128_invalid_freshness_clock_rejected(self):
        bundle = copy.deepcopy(self.bundle)
        bundle["feature_contracts"]["vix_level"]["freshness_clock"] = "INGESTED_WHENEVER"
        bundle = rebuild_bundle(bundle)
        self.assertEqual(evaluate(self.request, bundle)["reason_code"], "CONTRACT_INVALID")

    def test_129_unapproved_source_dataset_rejected(self):
        request = copy.deepcopy(self.request)
        request["features"][0]["source_dataset_id"] = "dataset:unapproved_v1"
        request["features"][0] = rehash_feature(request["features"][0])
        self.assertEqual(evaluate(request, self.bundle)["reason_code"], "FEATURE_CONTRACT_MISMATCH")

    def test_130_unapproved_license_rejected(self):
        request = copy.deepcopy(self.request)
        request["features"][0]["license_id"] = "license:unapproved_v1"
        request["features"][0] = rehash_feature(request["features"][0])
        self.assertEqual(evaluate(request, self.bundle)["reason_code"], "FEATURE_CONTRACT_MISMATCH")

    def test_131_feature_payload_tamper_rejected(self):
        request = copy.deepcopy(self.request)
        request["features"][0]["value"] = "0.09000000"
        self.assertEqual(evaluate(request, self.bundle)["reason_code"], "FEATURE_INTEGRITY_FAILED")

    def test_132_ood_inside_hard_range_rejected(self):
        request = copy.deepcopy(self.request)
        request["features"][2]["value"] = "150.00000000"
        request["features"][2] = rehash_feature(request["features"][2])
        self.assertEqual(evaluate(request, self.bundle)["reason_code"], "OUT_OF_DISTRIBUTION")

    def test_133_model_range_must_be_inside_hard_range(self):
        bundle = copy.deepcopy(self.bundle)
        bundle["feature_contracts"]["mom_20"]["model_min_value"] = "-2"
        bundle = rebuild_bundle(bundle)
        self.assertEqual(evaluate(self.request, bundle)["reason_code"], "CONTRACT_INVALID")

    def test_134_calibrated_head_cannot_keep_engineering_method(self):
        bundle = copy.deepcopy(self.bundle)
        bundle["calibration"]["status"] = "OOS_VALIDATED"
        bundle = rebuild_bundle(bundle)
        self.assertEqual(evaluate(self.request, bundle)["reason_code"], "PROMOTION_EVIDENCE_INVALID")

    def test_135_calibrated_expert_cannot_keep_engineering_method(self):
        bundle = copy.deepcopy(self.bundle)
        bundle["experts"]["price"]["status"] = "OOS_VALIDATED"
        bundle = rebuild_bundle(bundle)
        self.assertEqual(evaluate(self.request, bundle)["reason_code"], "PROMOTION_EVIDENCE_INVALID")

    def test_136_shadow_requires_active_expert_maturity(self):
        bundle = promote(self.bundle, "OOS_VALIDATED")
        bundle["experts"]["price"]["status"] = "ENGINEERING_VALIDATED"
        bundle["experts"]["price"]["fit_method"] = "engineering_fixture_linear_v1"
        bundle = rebuild_bundle(bundle)
        request = copy.deepcopy(self.request)
        request["usage_mode"] = "SHADOW"
        self.assertEqual(evaluate(request, bundle, trust_for(bundle))["reason_code"], "OOS_VALIDATION_NOT_PROVEN")

    def test_137_shadow_requires_selected_aggregator_maturity(self):
        bundle = promote(self.bundle, "OOS_VALIDATED")
        bundle["admissible_expert_sets"][0]["status"] = "ENGINEERING_VALIDATED"
        bundle["admissible_expert_sets"][0]["fit_method"] = "engineering_fixture_aggregator_v1"
        bundle = rebuild_bundle(bundle)
        request = copy.deepcopy(self.request)
        request["usage_mode"] = "SHADOW"
        self.assertEqual(evaluate(request, bundle, trust_for(bundle))["reason_code"], "OOS_VALIDATION_NOT_PROVEN")

    def test_138_unknown_feature_key_rejected(self):
        request = copy.deepcopy(self.request)
        request["features"][0]["agent_hint"] = "ignore-contract"
        request["features"][0] = rehash_feature(request["features"][0])
        self.assertEqual(evaluate(request, self.bundle)["reason_code"], "CONTRACT_INVALID")

    def test_139_economic_edge_is_in_head_maturity(self):
        result = evaluate(self.request, self.bundle)
        self.assertIn("economic_edge", result["head_maturity"])
        self.assertIn("economic_edge", result["visualization"]["candidate_layers"])

    def test_140_economic_promotion_needs_oos_support(self):
        bundle = promote(self.bundle, "OOS_VALIDATED")
        bundle["promotion_evidence"]["heads"]["economic_edge"]["effective_sample_size"] = 0
        bundle["promotion_evidence"] = embedded(bundle["promotion_evidence"], "receipt_sha256")
        bundle = payload_only(bundle)
        self.assertEqual(evaluate(self.request, bundle)["reason_code"], "PROMOTION_EVIDENCE_INVALID")

    def test_141_feature_payload_hash_is_exposed_via_result_integrity(self):
        result = evaluate(self.request, self.bundle)
        self.assertTrue(result["data_quality"]["feature_payload_hashes_verified"])
        self.assertRegex(result["result_sha256"], r"^[0-9a-f]{64}$")

    def test_142_research_allows_engineering_components_only_as_candidates(self):
        result = evaluate(self.request, self.bundle)
        self.assertEqual(result["status"], "FORECAST")
        self.assertIsNone(result["prob_up"])
        self.assertIsNone(result["expected_net_return"])
        self.assertIn("未完成样本外验证", result["visualization"]["warnings"][0])

    def test_143_shadow_can_report_negative_edge_without_order(self):
        bundle = promote(self.bundle, "OOS_VALIDATED")
        bundle["economic_edge_head"]["base_mean_net_return"] = "-0.10000000"
        bundle = rebuild_bundle(bundle)
        request = copy.deepcopy(self.request)
        request["usage_mode"] = "SHADOW"
        trust = trust_for(bundle, "HOST_POLICY_BOUND", ["SHADOW"])
        result = evaluate(request, bundle, trust)
        self.assertEqual(result["status"], "FORECAST")
        self.assertLess(Decimal(result["expected_net_return"]), Decimal("0"))
        self.assertFalse(result["positive_economic_edge"])
        self.assertNotIn("order", json.dumps(result).lower())

    def test_144_feature_contract_dataset_allowlist_must_not_be_empty(self):
        bundle = copy.deepcopy(self.bundle)
        bundle["feature_contracts"]["mom_20"]["allowed_source_dataset_ids"] = []
        bundle = rebuild_bundle(bundle)
        self.assertEqual(evaluate(self.request, bundle)["reason_code"], "CONTRACT_INVALID")

    def test_145_feature_contract_license_allowlist_must_not_be_empty(self):
        bundle = copy.deepcopy(self.bundle)
        bundle["feature_contracts"]["mom_20"]["allowed_license_ids"] = []
        bundle = rebuild_bundle(bundle)
        self.assertEqual(evaluate(self.request, bundle)["reason_code"], "CONTRACT_INVALID")


    def test_146_multi_horizon_bundle_rejected(self):
        bundle = copy.deepcopy(self.bundle)
        bundle["horizons"] = [5, 20]
        bundle = rebuild_bundle(bundle)
        self.assertEqual(evaluate(self.request, bundle)["reason_code"], "CONTRACT_INVALID")

    def test_147_universe_members_must_be_canonically_sorted(self):
        bundle = copy.deepcopy(self.bundle)
        members = ["FIGI:B", "FIGI:A"]
        bundle["scope"] = {"type": "universe_snapshot_v1", "members": members, "snapshot_sha256": sha256_hex(sorted(members))}
        bundle = rebuild_bundle(bundle)
        request = copy.deepcopy(self.request)
        request["instrument_id"] = "FIGI:A"
        request["universe_snapshot_sha256"] = bundle["scope"]["snapshot_sha256"]
        self.assertEqual(evaluate(request, bundle)["reason_code"], "CONTRACT_INVALID")

    def test_148_duplicate_expert_set_id_rejected(self):
        bundle = copy.deepcopy(self.bundle)
        bundle["admissible_expert_sets"][1]["set_id"] = bundle["admissible_expert_sets"][0]["set_id"]
        bundle = rebuild_bundle(bundle)
        self.assertEqual(evaluate(self.request, bundle)["reason_code"], "CONTRACT_INVALID")

    def test_149_unknown_bundle_top_level_key_rejected(self):
        bundle = copy.deepcopy(self.bundle)
        bundle["agent_fallback"] = True
        bundle = payload_only(bundle)
        self.assertEqual(evaluate(self.request, bundle)["reason_code"], "CONTRACT_INVALID")

    def test_150_dict_input_obeys_json_string_limit(self):
        request = copy.deepcopy(self.request)
        request["request_id"] = "x" * 20000
        self.assertEqual(evaluate(request, self.bundle)["reason_code"], "RESOURCE_LIMIT")

    def test_151_dict_input_with_custom_object_fails_closed(self):
        class Unsupported:
            pass
        request = copy.deepcopy(self.request)
        request["request_id"] = Unsupported()
        result = evaluate(request, self.bundle)
        self.assertEqual(result["status"], "ABSTAIN")
        self.assertEqual(result["reason_code"], "CONTRACT_INVALID")
        self.assertRegex(result["result_sha256"], r"^[0-9a-f]{64}$")

    def test_152_bundle_dict_with_custom_object_fails_closed(self):
        class Unsupported:
            pass
        bundle = copy.deepcopy(self.bundle)
        bundle["bundle_id"] = Unsupported()
        result = evaluate(self.request, bundle)
        self.assertEqual(result["status"], "ABSTAIN")
        self.assertEqual(result["reason_code"], "CONTRACT_INVALID")

    def test_153_infinite_batch_generator_is_bounded(self):
        consumed = {"count": 0}
        def endless():
            while True:
                consumed["count"] += 1
                yield self.request
        with self.assertRaises(EFSError) as caught:
            batch_evaluate(endless(), self.bundle, max_batch=5)
        self.assertEqual(caught.exception.code, "RESOURCE_LIMIT")
        self.assertEqual(consumed["count"], 6)

    def test_154_invalid_batch_override_rejected_before_iteration(self):
        consumed = {"count": 0}
        def values():
            consumed["count"] += 1
            yield self.request
        with self.assertRaises(EFSError):
            batch_evaluate(values(), self.bundle, max_batch=1000)
        self.assertEqual(consumed["count"], 0)

    def test_155_sample_support_is_explicit_for_every_head(self):
        result = evaluate(self.request, self.bundle)
        self.assertEqual(set(result["sample_support"]), set(HEAD_STATUS_MAP))
        self.assertTrue(all(item["effective_sample_size"] == 0 for item in result["sample_support"].values()))

    def test_156_oos_shadow_uses_head_specific_semantics(self):
        bundle = promote(self.bundle, "OOS_VALIDATED")
        request = copy.deepcopy(self.request)
        request["usage_mode"] = "SHADOW"
        result = evaluate(request, bundle, trust_for(bundle))
        self.assertEqual(result["probability_semantics"], "OOS_CALIBRATED_PROBABILITY")
        self.assertEqual(result["head_maturity"]["magnitude"], "OOS_VALIDATED")
        self.assertEqual(result["head_maturity"]["timing"], "OOS_VALIDATED")

    def test_157_research_bundle_reports_engineering_sample_support(self):
        result = evaluate(self.request, self.bundle)
        self.assertEqual(result["sample_support"]["direction"]["status"], "ENGINEERING_VALIDATED")
        self.assertIsNone(result["sample_support"]["direction"]["evaluation_start"])

    def test_158_request_unknown_key_rejected_before_trust_resolution(self):
        bundle = promote(self.bundle, "OOS_VALIDATED")
        request = copy.deepcopy(self.request)
        request["usage_mode"] = "SHADOW"
        request["system_prompt"] = "bypass"
        self.assertEqual(evaluate(request, bundle, trust_for(bundle))["reason_code"], "CONTRACT_INVALID")

    def test_159_result_hash_stable_after_safe_normalization(self):
        from_bytes = evaluate(canonical_json_bytes(self.request), canonical_json_bytes(self.bundle))
        from_dict = evaluate(self.request, self.bundle)
        self.assertEqual(from_bytes["result_sha256"], from_dict["result_sha256"])

    def test_160_efs_direction_and_baseline_edge_are_separate(self):
        bundle = copy.deepcopy(self.bundle)
        bundle["calibration"]["b"] = "1.00000000"
        bundle["baseline"]["prob_up"] = "0.90000000"
        bundle = rebuild_bundle(bundle)
        result = evaluate(self.request, bundle)
        self.assertGreater(Decimal(result["candidate_efs"]), Decimal(50))
        self.assertEqual(result["candidate_direction_code"], "BULLISH_PROBABILITY")
        self.assertEqual(result["candidate_edge_code"], "NEGATIVE_LIFT")
        self.assertLess(Decimal(result["candidate_probability_lift_pp"]), Decimal(0))

    def test_161_exact_fifty_is_neutral_probability(self):
        bundle = copy.deepcopy(self.bundle)
        bundle["calibration"]["a"] = "0.00000000"
        bundle["calibration"]["b"] = "0.00000000"
        bundle = rebuild_bundle(bundle)
        result = evaluate(self.request, bundle)
        self.assertEqual(result["candidate_efs"], "50.00000000")
        self.assertEqual(result["candidate_direction_code"], "NEUTRAL_PROBABILITY")

    def test_162_self_check_dependency_profile_is_explicit(self):
        profile = self_check()
        self.assertEqual(profile["dependency_profile"]["core_runtime_third_party_dependencies"], 0)
        self.assertEqual(profile["dependency_profile"]["release_authorized_path_third_party_dependencies"], 0)
        self.assertEqual(profile["release_capability_ceiling"], "SHADOW_ONLY")
        self.assertEqual(profile["release_authorized_usage_modes"], ["RESEARCH", "SHADOW"])

    def test_163_self_check_still_zero_agent_and_token(self):
        profile = self_check()["runtime_profile"]
        self.assertEqual(profile["agent_dependency"], 0)
        self.assertEqual(profile["llm_dependency"], 0)
        self.assertEqual(profile["llm_tokens_per_evaluation"], 0)
        self.assertEqual(profile["network_dependency"], 0)


if __name__ == "__main__":
    unittest.main()

class LifecycleTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.root = ROOT
        cls.request = load("request.json")
        cls.bundle = load("bundle.json")

    def test_164_health_runtime_only_is_deterministic(self):
        from equity_foresight_signal.lifecycle import health_snapshot
        first = health_snapshot(as_of="2026-07-24T21:00:00Z")
        second = health_snapshot(as_of="2026-07-24T21:00:00Z")
        self.assertEqual(first, second)
        self.assertEqual(first["status"], "HEALTHY_RUNTIME_ONLY")
        self.assertEqual(first["agent_invocations_total"], 0)
        self.assertEqual(first["llm_requests_total"], 0)

    def test_165_health_valid_bundle(self):
        from equity_foresight_signal.lifecycle import health_snapshot
        result = health_snapshot(self.bundle, as_of="2026-07-24T21:00:00Z")
        self.assertEqual(result["status"], "HEALTHY")
        self.assertEqual(result["bundle_state"], "VALID")

    def test_166_health_expired_bundle(self):
        from equity_foresight_signal.lifecycle import health_snapshot
        result = health_snapshot(self.bundle, as_of="2027-01-02T00:00:00Z")
        self.assertEqual(result["status"], "DEGRADED")
        self.assertEqual(result["bundle_state"], "EXPIRED")

    def test_167_health_invalid_bundle_fails_closed(self):
        from equity_foresight_signal.lifecycle import health_snapshot
        broken = copy.deepcopy(self.bundle)
        broken["payload_sha256"] = "0" * 64
        result = health_snapshot(broken, as_of="2026-07-24T21:00:00Z")
        self.assertEqual(result["status"], "UNHEALTHY")
        self.assertEqual(result["bundle_state"], "INVALID")

    def test_168_identical_candidate_is_compatible_but_not_auto_promoted(self):
        from equity_foresight_signal.lifecycle import compare_candidate_to_lkg
        report = compare_candidate_to_lkg(self.bundle, self.bundle)
        self.assertTrue(report["compatible_for_in_place_refresh"])
        self.assertFalse(report["automatic_promotion_permitted"])
        self.assertIn("CANDIDATE_IDENTICAL_TO_LKG", report["warnings"])

    def test_169_scope_change_rejected_for_in_place_refresh(self):
        from equity_foresight_signal.lifecycle import compare_candidate_to_lkg
        candidate = copy.deepcopy(self.bundle)
        candidate["scope"]["instrument_id"] = "FIGI:DIFFERENT"
        candidate = rebuild_bundle(candidate)
        report = compare_candidate_to_lkg(candidate, self.bundle)
        self.assertFalse(report["compatible_for_in_place_refresh"])
        self.assertIn("INCOMPATIBLE_SCOPE", report["blocking_reasons"])

    def test_170_cost_change_rejected_for_in_place_refresh(self):
        from equity_foresight_signal.lifecycle import compare_candidate_to_lkg
        candidate = copy.deepcopy(self.bundle)
        candidate["cost_contract"]["spread_slippage_bps"] = "20"
        # Embedded bindings are rebuilt consistently; compatibility still rejects the migration.
        candidate = rebuild_bundle(candidate)
        report = compare_candidate_to_lkg(candidate, self.bundle)
        self.assertFalse(report["compatible_for_in_place_refresh"])
        self.assertIn("INCOMPATIBLE_COST_CONTRACT", report["blocking_reasons"])

    def test_171_lifecycle_has_zero_agent_and_token_counters(self):
        from equity_foresight_signal.lifecycle import compare_candidate_to_lkg, health_snapshot
        for result in (health_snapshot(self.bundle, as_of="2026-07-24T21:00:00Z"), compare_candidate_to_lkg(self.bundle, self.bundle)):
            self.assertEqual(result["agent_invocations_total"], 0)
            self.assertEqual(result["llm_requests_total"], 0)
            self.assertEqual(result["llm_input_tokens_total"], 0)
            self.assertEqual(result["llm_output_tokens_total"], 0)
            self.assertEqual(result["network_requests_total"], 0)

class CLIEntryPointTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.root = ROOT

    def _run(self, *args: str):
        return subprocess.run(
            [sys.executable, *args],
            cwd=ROOT,
            text=True,
            capture_output=True,
            timeout=15,
            check=False,
            env={**os.environ, "PYTHONPATH": str(ROOT)},
        )

    def test_172_direct_script_self_check(self):
        completed = self._run(str(ROOT / "equity_foresight_signal" / "cli.py"), "self-check")
        self.assertEqual(completed.returncode, 0, completed.stderr)
        self.assertEqual(json.loads(completed.stdout)["runtime_profile"]["agent_dependency"], 0)

    def test_173_package_main_self_check(self):
        completed = self._run("-m", "equity_foresight_signal", "self-check")
        self.assertEqual(completed.returncode, 0, completed.stderr)
        self.assertEqual(json.loads(completed.stdout)["runtime_profile"]["llm_dependency"], 0)

    def test_174_module_cli_self_check(self):
        completed = self._run("-m", "equity_foresight_signal.cli", "self-check")
        self.assertEqual(completed.returncode, 0, completed.stderr)

    def test_175_cli_evaluate_golden_path(self):
        completed = self._run(
            "-m", "equity_foresight_signal", "evaluate",
            str(ROOT / "fixtures" / "request.json"),
            str(ROOT / "fixtures" / "bundle.json"),
        )
        self.assertEqual(completed.returncode, 0, completed.stderr)
        self.assertEqual(json.loads(completed.stdout)["status"], "FORECAST")

    def test_176_cli_missing_file_is_structured_error(self):
        completed = self._run("-m", "equity_foresight_signal", "validate-bundle", "does-not-exist.json")
        self.assertEqual(completed.returncode, 2)
        payload = json.loads(completed.stdout)
        self.assertEqual(payload["status"], "ERROR")
        self.assertEqual(payload["reason_code"], "INPUT_IO_ERROR")
        self.assertNotIn("Traceback", completed.stderr)

    def test_177_cli_rejects_symlink_input(self):
        import tempfile
        with tempfile.TemporaryDirectory() as tmp:
            link = Path(tmp) / "bundle-link.json"
            try:
                link.symlink_to(ROOT / "fixtures" / "bundle.json")
            except OSError:
                self.skipTest("symlinks unavailable")
            completed = self._run("-m", "equity_foresight_signal", "validate-bundle", str(link))
            self.assertEqual(completed.returncode, 2)
            self.assertEqual(json.loads(completed.stdout)["reason_code"], "INPUT_IO_ERROR")

class PreparedBundleTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.bundle = load("bundle.json")
        cls.request = load("request.json")

    def test_178_prepared_matches_regular_evaluation(self):
        from equity_foresight_signal import evaluate_prepared, prepare_bundle
        prepared = prepare_bundle(self.bundle)
        self.assertEqual(evaluate_prepared(self.request, prepared), evaluate(self.request, self.bundle))

    def test_179_prepared_isolated_from_original_mutation(self):
        from equity_foresight_signal import evaluate_prepared, prepare_bundle
        source = copy.deepcopy(self.bundle)
        prepared = prepare_bundle(source)
        expected = evaluate_prepared(self.request, prepared)
        source["bundle_id"] = "tampered_after_prepare"
        source["experts"]["price"]["weights"]["mom_20"] = "999"
        self.assertEqual(evaluate_prepared(self.request, prepared), expected)

    def test_180_prepared_cannot_be_constructed_directly(self):
        from equity_foresight_signal import PreparedBundle
        with self.assertRaises(TypeError):
            PreparedBundle(copy.deepcopy(self.bundle), object())

    def test_181_prepared_invalid_bundle_rejected(self):
        from equity_foresight_signal import prepare_bundle
        broken = copy.deepcopy(self.bundle)
        broken["payload_sha256"] = "0" * 64
        with self.assertRaises(EFSError):
            prepare_bundle(broken)

    def test_182_prepared_hot_path_does_not_revalidate_bundle(self):
        import equity_foresight_signal.engine as engine
        prepared = engine.prepare_bundle(self.bundle)
        with mock.patch.object(engine, "validate_bundle", side_effect=AssertionError("must not run")):
            result = engine.evaluate_prepared(self.request, prepared)
        self.assertEqual(result["status"], "FORECAST")

    def test_183_prepared_batch_matches_regular_batch(self):
        from equity_foresight_signal import batch_evaluate_prepared, prepare_bundle
        requests = [copy.deepcopy(self.request) for _ in range(3)]
        for index, item in enumerate(requests):
            item["request_id"] = f"prepared_batch_{index}"
        prepared = prepare_bundle(self.bundle)
        self.assertEqual(batch_evaluate_prepared(requests, prepared), batch_evaluate(requests, self.bundle))

    def test_184_wrong_prepared_type_fails_closed(self):
        from equity_foresight_signal import evaluate_prepared
        result = evaluate_prepared(self.request, object())
        self.assertEqual(result["status"], "ABSTAIN")
        self.assertEqual(result["reason_code"], "CONTRACT_INVALID")

class ForecastSuiteTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.bundle20 = load("bundle.json")
        cls.request20 = load("request.json")

    def _for_horizon(self, horizon: int):
        bundle = copy.deepcopy(self.bundle20)
        bundle["bundle_id"] = f"fixture_spy_{horizon}d_suite"
        bundle["horizons"] = [horizon]
        label_id = f"net_return_next_open_{horizon}d_gt_zero_v1"
        bundle["label_contract"]["id"] = label_id
        bundle["label_contract"]["exit_price"] = f"open_t_plus_{horizon + 1}"
        for key in ("baseline", "calibration", "magnitude_head", "timing_head", "economic_edge_head", "reliability_head"):
            bundle[key]["horizon"] = horizon
            bundle[key]["label_contract_id"] = label_id
        buckets = []
        start = 1
        bucket_count = min(4, horizon)
        for index in range(bucket_count):
            end = horizon if index == bucket_count - 1 else max(start, round((index + 1) * horizon / bucket_count))
            buckets.append({"start_day": start, "end_day": end, "up_logit": "0", "down_logit": "0"})
            start = end + 1
        bundle["timing_head"]["buckets"] = buckets
        bundle = rebuild_bundle(bundle)
        request = copy.deepcopy(self.request20)
        request["request_id"] = f"suite_request_{horizon}d"
        request["horizon"] = horizon
        request["label_contract_id"] = label_id
        return bundle, request

    def test_185_prepare_and_evaluate_5_20_60_suite(self):
        from equity_foresight_signal import evaluate_suite, prepare_suite
        pairs = [self._for_horizon(horizon) for horizon in (5, 20, 60)]
        suite = prepare_suite([item[0] for item in pairs], required_horizons=[5, 20, 60])
        result = evaluate_suite({h: pair[1] for h, pair in zip((5, 20, 60), pairs)}, suite)
        self.assertEqual(result["status"], "ALL_FORECAST")
        self.assertEqual([item["horizon"] for item in result["results"]], [5, 20, 60])
        self.assertEqual(result["cross_horizon_semantics"], "NO_COMPOSITE_SCORE_NO_AUTOMATIC_TRADE_DECISION")

    def test_186_duplicate_horizon_rejected(self):
        from equity_foresight_signal import prepare_suite
        with self.assertRaises(EFSError):
            prepare_suite([self.bundle20, self.bundle20])

    def test_187_scope_mismatch_rejected(self):
        from equity_foresight_signal import prepare_suite
        bundle5, _ = self._for_horizon(5)
        bundle5["scope"]["instrument_id"] = "FIGI:DIFFERENT"
        bundle5 = rebuild_bundle(bundle5)
        with self.assertRaises(EFSError):
            prepare_suite([bundle5, self.bundle20])

    def test_188_incomplete_suite_rejected_by_default(self):
        from equity_foresight_signal import evaluate_suite, prepare_suite
        bundle5, request5 = self._for_horizon(5)
        suite = prepare_suite([bundle5, self.bundle20])
        with self.assertRaises(EFSError):
            evaluate_suite({5: request5}, suite)

    def test_189_partial_suite_is_explicit_when_allowed(self):
        from equity_foresight_signal import evaluate_suite, prepare_suite
        bundle5, request5 = self._for_horizon(5)
        suite = prepare_suite([bundle5, self.bundle20])
        result = evaluate_suite({5: request5}, suite, require_complete=False)
        self.assertEqual(result["status"], "ALL_FORECAST")
        self.assertEqual(result["horizons"], [5, 20])
        self.assertEqual(len(result["results"]), 1)

    def test_190_suite_deterministic(self):
        from equity_foresight_signal import evaluate_suite, prepare_suite
        pairs = [self._for_horizon(horizon) for horizon in (5, 20, 60)]
        suite = prepare_suite([item[0] for item in pairs])
        requests = {h: pair[1] for h, pair in zip((5, 20, 60), pairs)}
        first = evaluate_suite(requests, suite)
        for _ in range(100):
            self.assertEqual(evaluate_suite(requests, suite), first)

    def test_191_suite_zero_agent_and_token(self):
        from equity_foresight_signal import evaluate_suite, prepare_suite
        suite = prepare_suite([self.bundle20])
        result = evaluate_suite({20: self.request20}, suite)
        self.assertEqual(result["agent_invocations_total"], 0)
        self.assertEqual(result["llm_requests_total"], 0)
        self.assertEqual(result["network_requests_total"], 0)

    def test_191a_suite_public_shapes_fail_as_controlled_contract_errors(self):
        from equity_foresight_signal import evaluate_suite, prepare_suite
        suite = prepare_suite([self.bundle20])
        for malformed in (None, 1, True, object()):
            with self.subTest(api="prepare_suite", malformed=type(malformed).__name__):
                with self.assertRaises(EFSError):
                    prepare_suite(malformed)
            with self.subTest(api="evaluate_suite.requests", malformed=type(malformed).__name__):
                with self.assertRaises(EFSError):
                    evaluate_suite(malformed, suite)
        for malformed in (1, True, object()):
            with self.subTest(api="evaluate_suite.trust", malformed=type(malformed).__name__):
                with self.assertRaises(EFSError):
                    evaluate_suite({20: self.request20}, suite, malformed)
        with self.assertRaises(EFSError):
            prepare_suite([self.bundle20], required_horizons=["x"])

    def test_191b_suite_iterables_are_bounded_before_bundle_validation(self):
        import equity_foresight_signal.suite as suite_module
        consumed = {"count": 0}

        def endless():
            while True:
                consumed["count"] += 1
                yield self.bundle20

        with mock.patch.object(suite_module, "MAX_SUITE_HORIZONS", 3):
            with self.assertRaisesRegex(EFSError, "RESOURCE_LIMIT"):
                suite_module.prepare_suite(endless())
        self.assertEqual(consumed["count"], 4)

class OOSValidationTests(unittest.TestCase):
    def _policy(self, role="OOS", minimum_records=20):
        policy = {
            "schema": "efs.validation_policy.v1",
            "policy_id": "fixture_oos_policy_20d_v1",
            "evaluation_role": role,
            "evaluation_as_of": "2026-07-25T00:00:00Z",
            "horizon": 20,
            "hurdle": "0",
            "calibration_bins": 10,
            "minimum_records": minimum_records,
            "minimum_clusters": 2,
            "minimum_brier_skill": "0.05",
            "minimum_auc": "0.55",
            "maximum_ece": "0.15",
            "minimum_interval_coverage": "0.70",
            "maximum_interval_coverage": "1.00",
            "maximum_timing_brier": "0.20",
            "cost_stress_multiplier": "2",
            "minimum_mean_stressed_return": "0.001",
            "maximum_monotonicity_violations": 2,
            "subject_model_set_sha256": load("bundle.json")["model_set_sha256"],
            "trial_manifest_sha256": sha256_hex({"trial_manifest": "fixture"}),
            "dataset_snapshot_sha256": sha256_hex({"dataset_snapshot": "fixture"}),
        }
        policy["policy_sha256"] = sha256_hex(policy)
        return policy

    def _records(self, *, good=True, count=40):
        from datetime import datetime, timedelta, timezone
        records = []
        start = datetime(2022, 1, 1, tzinfo=timezone.utc)
        for index in range(count):
            positive = index % 2 == 0
            probability = ("0.90" if positive else "0.10") if good else ("0.10" if positive else "0.90")
            gross = Decimal("0.03") if positive else Decimal("-0.015")
            actual_net = gross - Decimal("0.001")
            event = "UP" if actual_net > 0 else "DOWN"
            forecast = start + timedelta(days=index * 25)
            matured = forecast + timedelta(days=21)
            record = {
                "schema": "efs.oos_forecast_record.v1",
                "record_id": f"oos_{index:04d}",
                "forecast_as_of": forecast.isoformat().replace("+00:00", "Z"),
                "label_matured_at": matured.isoformat().replace("+00:00", "Z"),
                "instrument_id": f"FIGI:FIXTURE{index % 10:02d}",
                "horizon": 20,
                "cluster_id": f"year_{forecast.year}",
                "prob_up": probability,
                "baseline_prob": "0.50",
                "gross_return": str(gross),
                "cost_return": "0.001",
                "p10": str(actual_net - Decimal("0.02")),
                "p50": str(actual_net),
                "p90": str(actual_net + Decimal("0.02")),
                "timing_up": "0.90" if event == "UP" else "0.05",
                "timing_down": "0.90" if event == "DOWN" else "0.05",
                "timing_timeout": "0.05",
                "realized_event": event,
            }
            record["source_record_sha256"] = sha256_hex(record)
            records.append(record)
        return records

    def test_192_good_oos_evidence_passes_without_auto_promotion(self):
        from equity_foresight_signal import evaluate_oos_records
        report = evaluate_oos_records(self._records(), self._policy())
        self.assertEqual(report["overall_status"], "PASS")
        self.assertFalse(report["automatic_promotion_permitted"])
        self.assertGreater(Decimal(report["direction"]["brier_skill"]), 0)

    def test_193_bad_direction_evidence_fails(self):
        from equity_foresight_signal import evaluate_oos_records
        report = evaluate_oos_records(self._records(good=False), self._policy())
        self.assertEqual(report["direction"]["status"], "FAIL")
        self.assertEqual(report["overall_status"], "FAIL")

    def test_194_insufficient_support_is_not_pass(self):
        from equity_foresight_signal import evaluate_oos_records
        report = evaluate_oos_records(self._records(count=10), self._policy(minimum_records=20))
        self.assertEqual(report["direction"]["status"], "INSUFFICIENT_SUPPORT")
        self.assertEqual(report["overall_status"], "FAIL")

    def test_195_unmatured_label_rejected(self):
        from equity_foresight_signal import evaluate_oos_records
        records = self._records()
        records[-1]["label_matured_at"] = "2027-01-01T00:00:00Z"
        records[-1]["source_record_sha256"] = sha256_hex({k: v for k, v in records[-1].items() if k != "source_record_sha256"})
        with self.assertRaises(EFSError):
            evaluate_oos_records(records, self._policy())

    def test_196_record_tamper_rejected(self):
        from equity_foresight_signal import evaluate_oos_records
        records = self._records()
        records[0]["prob_up"] = "0.51"
        with self.assertRaises(EFSError):
            evaluate_oos_records(records, self._policy())

    def test_197_policy_tamper_rejected(self):
        from equity_foresight_signal import evaluate_oos_records
        policy = self._policy()
        policy["minimum_auc"] = "0.99"
        with self.assertRaises(EFSError):
            evaluate_oos_records(self._records(), policy)

    def test_198_validation_is_order_independent_and_deterministic(self):
        from equity_foresight_signal import evaluate_oos_records
        records = self._records()
        first = evaluate_oos_records(records, self._policy())
        second = evaluate_oos_records(list(reversed(records)), self._policy())
        self.assertEqual(first, second)

    def test_199_evidence_zero_agent_and_token(self):
        from equity_foresight_signal import evaluate_oos_records
        result = evaluate_oos_records(self._records(), self._policy())
        self.assertEqual(result["agent_invocations_total"], 0)
        self.assertEqual(result["llm_requests_total"], 0)
        self.assertEqual(result["network_requests_total"], 0)

class ResearchGovernanceTests(unittest.TestCase):
    def _config(self, minimum_train=20, test_block=5, embargo=2):
        config = {
            "schema": "efs.walk_forward_config.v1",
            "config_id": "fixture_walk_forward_20d_v1",
            "horizon": 20,
            "minimum_train_records": minimum_train,
            "test_block_records": test_block,
            "embargo_calendar_days": embargo,
            "maximum_folds": 10,
        }
        config["config_sha256"] = sha256_hex(config)
        return config

    def _wf_records(self, count=80):
        from datetime import datetime, timedelta, timezone
        records = []
        start = datetime(2020, 1, 1, tzinfo=timezone.utc)
        for index in range(count):
            forecast = start + timedelta(days=index * 3)
            matured = forecast + timedelta(days=21)
            record = {
                "record_id": f"wf_{index:04d}",
                "forecast_as_of": forecast.isoformat().replace("+00:00", "Z"),
                "label_matured_at": matured.isoformat().replace("+00:00", "Z"),
                "instrument_id": f"FIGI:WF{index % 8:02d}",
            }
            record["record_sha256"] = sha256_hex(record)
            records.append(record)
        return records

    def _trial(self, trial_id, created_at, parent=None):
        trial = {
            "schema": "efs.trial_registration.v1",
            "trial_id": trial_id,
            "hypothesis_id": f"hypothesis_{trial_id}",
            "created_at": created_at,
            "feature_set_sha256": sha256_hex({"feature": trial_id}),
            "model_spec_sha256": sha256_hex({"model": trial_id}),
            "walk_forward_plan_sha256": sha256_hex({"plan": trial_id}),
            "validation_policy_sha256": sha256_hex({"policy": trial_id}),
            "dataset_snapshot_sha256": sha256_hex({"dataset": "same"}),
            "parent_trial_id": parent,
        }
        trial["registration_sha256"] = sha256_hex(trial)
        return trial

    def test_200_purged_walk_forward_has_no_label_leakage(self):
        from equity_foresight_signal import build_purged_walk_forward_plan
        records = self._wf_records()
        by_id = {item["record_id"]: item for item in records}
        plan = build_purged_walk_forward_plan(records, self._config())
        self.assertGreater(plan["fold_count"], 0)
        for fold in plan["folds"]:
            test_start = fold["test_first_forecast_as_of"]
            self.assertTrue(all(by_id[item]["label_matured_at"] < test_start for item in fold["train_record_ids"]))

    def test_201_walk_forward_is_order_independent(self):
        from equity_foresight_signal import build_purged_walk_forward_plan
        records = self._wf_records()
        self.assertEqual(
            build_purged_walk_forward_plan(records, self._config()),
            build_purged_walk_forward_plan(list(reversed(records)), self._config()),
        )

    def test_202_walk_forward_config_tamper_rejected(self):
        from equity_foresight_signal import build_purged_walk_forward_plan
        config = self._config()
        config["embargo_calendar_days"] = 0
        with self.assertRaises(EFSError):
            build_purged_walk_forward_plan(self._wf_records(), config)

    def test_203_walk_forward_insufficient_support(self):
        from equity_foresight_signal import build_purged_walk_forward_plan
        with self.assertRaises(EFSError):
            build_purged_walk_forward_plan(self._wf_records(10), self._config())

    def test_204_trial_manifest_counts_every_trial(self):
        from equity_foresight_signal import build_trial_manifest
        first = self._trial("trial_001", "2026-01-01T00:00:00Z")
        second = self._trial("trial_002", "2026-01-02T00:00:00Z", parent="trial_001")
        manifest = build_trial_manifest([second, first])
        self.assertEqual(manifest["trial_count"], 2)
        self.assertFalse(manifest["automatic_candidate_selection_permitted"])
        self.assertEqual([item["trial_id"] for item in manifest["trials"]], ["trial_001", "trial_002"])

    def test_205_unknown_parent_rejected(self):
        from equity_foresight_signal import build_trial_manifest
        with self.assertRaises(EFSError):
            build_trial_manifest([self._trial("trial_002", "2026-01-02T00:00:00Z", parent="missing")])

    def test_206_duplicate_trial_rejected(self):
        from equity_foresight_signal import build_trial_manifest
        trial = self._trial("trial_001", "2026-01-01T00:00:00Z")
        with self.assertRaises(EFSError):
            build_trial_manifest([trial, trial])

    def test_207_research_governance_zero_agent_token(self):
        from equity_foresight_signal import build_purged_walk_forward_plan
        plan = build_purged_walk_forward_plan(self._wf_records(), self._config())
        self.assertEqual(plan["agent_invocations_total"], 0)
        self.assertEqual(plan["llm_requests_total"], 0)
        self.assertEqual(plan["network_requests_total"], 0)

class PromotionLifecycleTests(OOSValidationTests):
    def _report_for(self, bundle, role, dataset_tag):
        from equity_foresight_signal import evaluate_oos_records
        policy = self._policy(role=role)
        policy["subject_model_set_sha256"] = bundle["model_set_sha256"]
        policy["dataset_snapshot_sha256"] = sha256_hex({"dataset": dataset_tag})
        policy["policy_id"] = f"fixture_{role.lower()}_policy"
        policy.pop("policy_sha256", None)
        policy["policy_sha256"] = sha256_hex(policy)
        return evaluate_oos_records(self._records(), policy)

    def _new_candidate(self, status):
        candidate = promote(load("bundle.json"), status)
        candidate["bundle_id"] = f"candidate_{status.lower()}"
        candidate["created_at"] = "2026-02-01T00:00:00Z"
        candidate["expires_at"] = "2027-02-01T00:00:00Z"
        candidate["calibration"]["expires_at"] = "2027-02-01T00:00:00Z"
        return rebuild_bundle(candidate)

    def test_208_shadow_candidate_can_be_bound_and_assessed(self):
        from equity_foresight_signal import assess_candidate_promotion, bind_validation_evidence
        lkg = load("bundle.json")
        candidate = self._new_candidate("OOS_VALIDATED")
        oos = self._report_for(candidate, "OOS", "oos")
        bound = bind_validation_evidence(candidate, oos)
        decision = assess_candidate_promotion(bound, lkg, oos, intended_mode="SHADOW")
        self.assertTrue(decision["eligible_for_separate_host_approval"])
        self.assertFalse(decision["automatic_promotion_permitted"])

    def test_209_failed_oos_cannot_be_bound(self):
        from equity_foresight_signal import bind_validation_evidence, evaluate_oos_records
        candidate = self._new_candidate("OOS_VALIDATED")
        policy = self._policy()
        policy["subject_model_set_sha256"] = candidate["model_set_sha256"]
        policy.pop("policy_sha256")
        policy["policy_sha256"] = sha256_hex(policy)
        failed = evaluate_oos_records(self._records(good=False), policy)
        with self.assertRaises(EFSError):
            bind_validation_evidence(candidate, failed)

    def test_210_decision_support_requires_distinct_holdout(self):
        from equity_foresight_signal import bind_validation_evidence
        candidate = self._new_candidate("OUTCOME_PROVEN")
        oos = self._report_for(candidate, "OOS", "same")
        holdout = self._report_for(candidate, "UNTOUCHED_HOLDOUT", "same")
        with self.assertRaises(EFSError):
            bind_validation_evidence(candidate, oos, holdout)

    def test_211_decision_support_eligible_with_bound_holdout(self):
        from equity_foresight_signal import assess_candidate_promotion, bind_validation_evidence
        lkg = load("bundle.json")
        candidate = self._new_candidate("OUTCOME_PROVEN")
        oos = self._report_for(candidate, "OOS", "oos")
        holdout = self._report_for(candidate, "UNTOUCHED_HOLDOUT", "holdout")
        bound = bind_validation_evidence(candidate, oos, holdout)
        decision = assess_candidate_promotion(
            bound, lkg, oos, intended_mode="DECISION_SUPPORT",
            untouched_holdout_report=holdout,
        )
        self.assertTrue(decision["eligible_for_separate_host_approval"])
        self.assertEqual(decision["decision"], "ELIGIBLE_FOR_SEPARATE_HOST_APPROVAL")

    def test_212_report_subject_mismatch_keeps_lkg(self):
        from equity_foresight_signal import assess_candidate_promotion, bind_validation_evidence
        lkg = load("bundle.json")
        candidate = self._new_candidate("OOS_VALIDATED")
        oos = self._report_for(candidate, "OOS", "oos")
        bound = bind_validation_evidence(candidate, oos)
        other = copy.deepcopy(oos)
        other["subject_model_set_sha256"] = "0" * 64
        other.pop("report_sha256")
        other["report_sha256"] = sha256_hex(other)
        decision = assess_candidate_promotion(bound, lkg, other, intended_mode="SHADOW")
        self.assertFalse(decision["eligible_for_separate_host_approval"])
        self.assertIn("OOS_SUBJECT_MISMATCH", decision["blocking_reasons"])

    def test_213_identical_candidate_is_no_change(self):
        from equity_foresight_signal import assess_candidate_promotion
        bundle = promote(load("bundle.json"), "OOS_VALIDATED")
        oos = self._report_for(bundle, "OOS", "oos")
        decision = assess_candidate_promotion(bundle, bundle, oos, intended_mode="SHADOW")
        self.assertFalse(decision["eligible_for_separate_host_approval"])
        self.assertIn("NO_CHANGE_KEEP_LKG", decision["blocking_reasons"])

    def test_214_promotion_lifecycle_zero_agent_and_token(self):
        from equity_foresight_signal import assess_candidate_promotion, bind_validation_evidence
        lkg = load("bundle.json")
        candidate = self._new_candidate("OOS_VALIDATED")
        oos = self._report_for(candidate, "OOS", "oos")
        bound = bind_validation_evidence(candidate, oos)
        decision = assess_candidate_promotion(bound, lkg, oos, intended_mode="SHADOW")
        self.assertEqual(decision["agent_invocations_total"], 0)
        self.assertEqual(decision["llm_requests_total"], 0)
        self.assertEqual(decision["network_requests_total"], 0)

    def test_214a_validation_report_nested_shapes_are_verified_before_binding(self):
        from equity_foresight_signal import bind_validation_evidence
        candidate = self._new_candidate("OUTCOME_PROVEN")
        oos = self._report_for(candidate, "OOS", "oos")
        holdout = self._report_for(candidate, "UNTOUCHED_HOLDOUT", "holdout")
        for malformed in (None, 1, [], {}):
            broken = copy.deepcopy(holdout)
            broken["economic_edge"] = malformed
            broken.pop("report_sha256")
            broken["report_sha256"] = sha256_hex(broken)
            with self.subTest(malformed=type(malformed).__name__):
                with self.assertRaises(EFSError):
                    bind_validation_evidence(candidate, oos, broken)

    def test_214b_status_adapter_accepts_only_a_fully_valid_promotion_decision(self):
        from equity_foresight_signal import assess_candidate_promotion, bind_validation_evidence, build_host_status_payload
        lkg = load("bundle.json")
        candidate = self._new_candidate("OUTCOME_PROVEN")
        oos = self._report_for(candidate, "OOS", "oos")
        holdout = self._report_for(candidate, "UNTOUCHED_HOLDOUT", "holdout")
        bound = bind_validation_evidence(candidate, oos, holdout)
        decision = assess_candidate_promotion(
            bound,
            lkg,
            oos,
            intended_mode="DECISION_SUPPORT",
            untouched_holdout_report=holdout,
        )
        status = build_host_status_payload(
            as_of="2026-07-25T00:00:00Z",
            bundle=bound,
            outcome_report=holdout,
            promotion_decision=decision,
        )
        self.assertEqual(status["capability_state"], "ELIGIBLE_FOR_HOST_CONTROLLED_ACTIVATION")
        forged = copy.deepcopy(decision)
        forged["eligible_for_separate_host_approval"] = False
        forged.pop("decision_sha256")
        forged["decision_sha256"] = sha256_hex(forged)
        with self.assertRaises(EFSError):
            build_host_status_payload(
                as_of="2026-07-25T00:00:00Z",
                bundle=bound,
                outcome_report=holdout,
                promotion_decision=forged,
            )

class BoundedIterableTests(OOSValidationTests, ResearchGovernanceTests):
    def test_215_oos_infinite_iterable_is_bounded_before_validation(self):
        import equity_foresight_signal.evidence as evidence
        consumed = {"count": 0}
        def endless():
            while True:
                consumed["count"] += 1
                yield {}
        with mock.patch.object(evidence, "MAX_OOS_RECORDS", 5):
            with self.assertRaisesRegex(EFSError, "RESOURCE_LIMIT"):
                evidence.evaluate_oos_records(endless(), self._policy())
        self.assertEqual(consumed["count"], 6)

    def test_216_walk_forward_infinite_iterable_is_bounded(self):
        import equity_foresight_signal.research as research
        consumed = {"count": 0}
        def endless():
            while True:
                consumed["count"] += 1
                yield {}
        with mock.patch.object(research, "MAX_WALK_FORWARD_RECORDS", 5):
            with self.assertRaisesRegex(EFSError, "RESOURCE_LIMIT"):
                research.build_purged_walk_forward_plan(endless(), self._config())
        self.assertEqual(consumed["count"], 6)

    def test_217_trial_manifest_infinite_iterable_is_bounded(self):
        import equity_foresight_signal.research as research
        consumed = {"count": 0}
        def endless():
            while True:
                consumed["count"] += 1
                yield {}
        with mock.patch.object(research, "MAX_TRIALS", 5):
            with self.assertRaisesRegex(EFSError, "RESOURCE_LIMIT"):
                research.build_trial_manifest(endless())
        self.assertEqual(consumed["count"], 6)


class ContractShapeHardeningTests(unittest.TestCase):
    def setUp(self) -> None:
        self.bundle = load("bundle.json")

    def test_218_nested_unhashable_statuses_fail_as_controlled_contract_errors(self):
        mutations = (
            ("experts", "price", "status"),
            ("admissible_expert_sets", 0, "status"),
            ("baseline", "status"),
            ("calibration", "status"),
            ("magnitude_head", "status"),
            ("timing_head", "status"),
            ("economic_edge_head", "status"),
            ("reliability_head", "status"),
        )
        for path in mutations:
            with self.subTest(path=path):
                broken = copy.deepcopy(self.bundle)
                target = broken
                for key in path[:-1]:
                    target = target[key]
                target[path[-1]] = {"invalid": True}
                with self.assertRaisesRegex(EFSError, "CONTRACT_INVALID"):
                    validate_bundle(broken)

    def test_219_unhashable_model_type_and_temporal_semantic_are_controlled(self):
        broken_model = copy.deepcopy(self.bundle)
        broken_model["experts"]["price"]["model_type"] = []
        with self.assertRaisesRegex(EFSError, "CONTRACT_INVALID"):
            validate_bundle(broken_model)

        broken_semantics = copy.deepcopy(self.bundle)
        broken_semantics["feature_contracts"]["mom_20"]["allowed_temporal_semantics"][0] = {}
        with self.assertRaisesRegex(EFSError, "CONTRACT_INVALID"):
            validate_bundle(broken_semantics)
