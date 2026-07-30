from __future__ import annotations

import copy
import json
import socket
import unittest
from pathlib import Path
from unittest import mock

from equity_foresight_signal import train_direction_pipeline, validate_pit_dataset, validate_training_config
from equity_foresight_signal.canonical import canonical_json_bytes, sha256_hex
from equity_foresight_signal.errors import EFSError

ROOT = Path(__file__).resolve().parents[1]


def load(name: str) -> dict:
    return json.loads((ROOT / "fixtures" / name).read_text(encoding="utf-8"))


def rebuild_row(row: dict) -> dict:
    value = copy.deepcopy(row)
    value.pop("row_payload_sha256", None)
    value["row_payload_sha256"] = sha256_hex(value)
    return value


def rebuild_dataset(dataset: dict) -> dict:
    value = copy.deepcopy(dataset)
    value.pop("payload_sha256", None)
    value["payload_sha256"] = sha256_hex(value)
    return value


def rebuild_config(config: dict) -> dict:
    value = copy.deepcopy(config)
    value.pop("config_sha256", None)
    value["config_sha256"] = sha256_hex(value)
    return value


class DeterministicTrainingTests(unittest.TestCase):
    def setUp(self) -> None:
        self.dataset = load("pit_dataset.json")
        self.config = load("training_config.json")

    def test_301_config_validates(self):
        self.assertEqual(validate_training_config(self.config)["config_id"], "fixture_linear_direction_v1")

    def test_302_training_is_deterministic(self):
        first = train_direction_pipeline(self.dataset, self.config)
        second = train_direction_pipeline(self.dataset, self.config)
        self.assertEqual(first, second)
        self.assertRegex(first["run_sha256"], r"^[0-9a-f]{64}$")

    def test_303_bytes_and_dict_are_equivalent(self):
        self.assertEqual(
            train_direction_pipeline(self.dataset, self.config),
            train_direction_pipeline(canonical_json_bytes(self.dataset), canonical_json_bytes(self.config)),
        )

    def test_304_holdout_mutation_does_not_change_fit_artifacts(self):
        original = train_direction_pipeline(self.dataset, self.config)
        mutated = copy.deepcopy(self.dataset)
        row = mutated["rows"][-1]
        row["net_return_1x"] = "-0.20"
        row["net_return_2x"] = "-0.21"
        row["net_return_3x"] = "-0.22"
        row["label"] = 0
        mutated["rows"][-1] = rebuild_row(row)
        mutated = rebuild_dataset(mutated)
        changed = train_direction_pipeline(mutated, self.config)
        self.assertEqual(original["direction_artifact"], changed["direction_artifact"])
        self.assertEqual(original["calibration_artifact"], changed["calibration_artifact"])
        self.assertNotEqual(original["holdout_records_sha256"], changed["holdout_records_sha256"])

    def test_305_calibration_mutation_does_not_change_direction_fit(self):
        original = train_direction_pipeline(self.dataset, self.config)
        mutated = copy.deepcopy(self.dataset)
        row = mutated["rows"][4]
        row["features"]["mom_20"] = "0.20"
        mutated["rows"][4] = rebuild_row(row)
        mutated = rebuild_dataset(mutated)
        changed = train_direction_pipeline(mutated, self.config)
        self.assertEqual(original["direction_artifact"], changed["direction_artifact"])
        self.assertNotEqual(original["calibration_artifact"], changed["calibration_artifact"])

    def test_306_train_mutation_changes_direction_artifact(self):
        original = train_direction_pipeline(self.dataset, self.config)
        mutated = copy.deepcopy(self.dataset)
        row = mutated["rows"][0]
        row["features"]["mom_20"] = "0.30"
        mutated["rows"][0] = rebuild_row(row)
        mutated = rebuild_dataset(mutated)
        changed = train_direction_pipeline(mutated, self.config)
        self.assertNotEqual(original["direction_artifact"], changed["direction_artifact"])

    def test_307_config_tamper_rejected(self):
        broken = copy.deepcopy(self.config)
        broken["iterations"] = 1
        with self.assertRaisesRegex(EFSError, "HASH_MISMATCH"):
            validate_training_config(broken)

    def test_308_feature_set_mismatch_rejected(self):
        broken = copy.deepcopy(self.config)
        broken["feature_names"] = ["mom_20"]
        broken = rebuild_config(broken)
        with self.assertRaisesRegex(EFSError, "feature set"):
            train_direction_pipeline(self.dataset, broken)

    def test_309_invalid_dataset_rejected(self):
        broken = copy.deepcopy(self.dataset)
        broken["payload_sha256"] = "0" * 64
        with self.assertRaises(EFSError):
            train_direction_pipeline(broken, self.config)

    def test_310_zero_agent_token_network_and_randomness(self):
        result = train_direction_pipeline(self.dataset, self.config)
        self.assertEqual(result["agent_invocations_total"], 0)
        self.assertEqual(result["llm_requests_total"], 0)
        self.assertEqual(result["llm_input_tokens_total"], 0)
        self.assertEqual(result["llm_output_tokens_total"], 0)
        self.assertEqual(result["network_requests_total"], 0)
        self.assertEqual(result["random_seed_dependency"], 0)

    def test_311_network_blocked_still_trains(self):
        with mock.patch.object(socket, "socket", side_effect=AssertionError("network forbidden")):
            result = train_direction_pipeline(self.dataset, self.config)
        self.assertEqual(result["status"], "ENGINEERING_TRAINING_COMPLETE")

    def test_312_no_automatic_promotion_or_outcome_claim(self):
        result = train_direction_pipeline(self.dataset, self.config)
        self.assertFalse(result["automatic_promotion_permitted"])
        self.assertEqual(result["outcome_claim"], "NOT_PROVEN")

    def test_313_holdout_records_are_integrity_bound(self):
        result = train_direction_pipeline(self.dataset, self.config)
        self.assertEqual(result["holdout_records_sha256"], sha256_hex(result["holdout_records"]))
        for record in result["holdout_records"]:
            payload = dict(record)
            claimed = payload.pop("source_record_sha256")
            self.assertEqual(claimed, sha256_hex(payload))

    def test_314_raw_model_artifact_has_exact_feature_map(self):
        artifact = train_direction_pipeline(self.dataset, self.config)["direction_artifact"]
        self.assertEqual(set(artifact["weights"]), set(self.config["feature_names"]))
        self.assertEqual(artifact["model_type"], "linear_logit_v1")

    def test_315_training_iteration_limit_is_bounded(self):
        broken = copy.deepcopy(self.config)
        broken["iterations"] = 10001
        broken = rebuild_config(broken)
        with self.assertRaisesRegex(EFSError, "iterations"):
            validate_training_config(broken)

    def test_316_non_string_feature_names_fail_as_controlled_contract_errors(self):
        for invalid in (-1, False, None, {}, []):
            with self.subTest(invalid=repr(invalid)):
                broken = copy.deepcopy(self.config)
                broken["feature_names"][0] = invalid
                broken = rebuild_config(broken)
                with self.assertRaisesRegex(EFSError, "CONTRACT_INVALID"):
                    validate_training_config(broken)

    def test_317_unhashable_dataset_scope_type_is_controlled(self):
        broken = copy.deepcopy(self.dataset)
        broken["scope"]["type"] = []
        broken = rebuild_dataset(broken)
        with self.assertRaisesRegex(EFSError, "CONTRACT_INVALID"):
            validate_pit_dataset(broken)

    def test_318_unhashable_dataset_split_is_controlled(self):
        broken = copy.deepcopy(self.dataset)
        broken["rows"][0]["split"] = []
        broken["rows"][0] = rebuild_row(broken["rows"][0])
        broken = rebuild_dataset(broken)
        with self.assertRaisesRegex(EFSError, "CONTRACT_INVALID"):
            validate_pit_dataset(broken)


if __name__ == "__main__":
    unittest.main()
