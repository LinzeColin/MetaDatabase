from __future__ import annotations

import copy
import json
import unittest
from pathlib import Path

from equity_foresight_signal.canonical import canonical_json_bytes, sha256_hex
from equity_foresight_signal.dataset import PIT_DATASET_SCHEMA, validate_pit_dataset
from equity_foresight_signal.errors import EFSError

ROOT = Path(__file__).resolve().parents[1]


def load_dataset() -> dict:
    return json.loads((ROOT / "fixtures" / "pit_dataset.json").read_text(encoding="utf-8"))


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


class PITDatasetTests(unittest.TestCase):
    def setUp(self) -> None:
        self.dataset = load_dataset()

    def test_201_valid_fixture(self):
        receipt = validate_pit_dataset(self.dataset)
        self.assertEqual(receipt["status"], "PASS")
        self.assertEqual(receipt["row_count"], 12)
        self.assertEqual(receipt["split_counts"], {"TRAIN": 4, "CALIBRATION": 4, "HOLDOUT": 4})
        self.assertEqual(receipt["agent_invocations_total"], 0)
        self.assertEqual(receipt["llm_requests_total"], 0)

    def test_202_bytes_and_dict_are_equivalent(self):
        self.assertEqual(validate_pit_dataset(self.dataset), validate_pit_dataset(canonical_json_bytes(self.dataset)))

    def test_203_dataset_hash_tamper_rejected(self):
        broken = copy.deepcopy(self.dataset)
        broken["payload_sha256"] = "0" * 64
        with self.assertRaisesRegex(EFSError, "HASH_MISMATCH"):
            validate_pit_dataset(broken)

    def test_204_row_hash_tamper_rejected(self):
        broken = copy.deepcopy(self.dataset)
        broken["rows"][0]["features"]["mom_20"] = "0.50"
        broken = rebuild_dataset(broken)
        with self.assertRaisesRegex(EFSError, "HASH_MISMATCH"):
            validate_pit_dataset(broken)

    def test_205_unmatured_label_rejected(self):
        broken = copy.deepcopy(self.dataset)
        broken["created_at"] = "2025-05-20T00:00:00Z"
        broken = rebuild_dataset(broken)
        with self.assertRaisesRegex(EFSError, "LOOKAHEAD_RISK"):
            validate_pit_dataset(broken)

    def test_206_label_before_signal_rejected(self):
        broken = copy.deepcopy(self.dataset)
        broken["rows"][0]["label_matured_at"] = broken["rows"][0]["signal_as_of"]
        broken["rows"][0] = rebuild_row(broken["rows"][0])
        broken = rebuild_dataset(broken)
        with self.assertRaisesRegex(EFSError, "LOOKAHEAD_RISK"):
            validate_pit_dataset(broken)

    def test_207_split_overlap_rejected(self):
        broken = copy.deepcopy(self.dataset)
        broken["rows"][4]["signal_as_of"] = "2025-01-03T21:00:00Z"
        broken["rows"][4] = rebuild_row(broken["rows"][4])
        broken["rows"] = sorted(broken["rows"], key=lambda r: (r["signal_as_of"], r["instrument_id"], r["row_id"]))
        broken = rebuild_dataset(broken)
        with self.assertRaisesRegex(EFSError, "LOOKAHEAD_RISK"):
            validate_pit_dataset(broken)

    def test_208_label_mismatch_rejected(self):
        broken = copy.deepcopy(self.dataset)
        broken["rows"][0]["label"] = 1
        broken["rows"][0] = rebuild_row(broken["rows"][0])
        broken = rebuild_dataset(broken)
        with self.assertRaisesRegex(EFSError, "LABEL_MISMATCH"):
            validate_pit_dataset(broken)

    def test_209_cost_stress_order_rejected(self):
        broken = copy.deepcopy(self.dataset)
        broken["rows"][0]["net_return_3x"] = "0.10"
        broken["rows"][0] = rebuild_row(broken["rows"][0])
        broken = rebuild_dataset(broken)
        with self.assertRaisesRegex(EFSError, "CONTRACT_INVALID"):
            validate_pit_dataset(broken)

    def test_210_feature_set_must_match_exactly(self):
        broken = copy.deepcopy(self.dataset)
        broken["rows"][0]["features"].pop("vix_level")
        broken["rows"][0] = rebuild_row(broken["rows"][0])
        broken = rebuild_dataset(broken)
        with self.assertRaisesRegex(EFSError, "CONTRACT_INVALID"):
            validate_pit_dataset(broken)

    def test_211_rows_must_be_canonical(self):
        broken = copy.deepcopy(self.dataset)
        broken["rows"][0], broken["rows"][1] = broken["rows"][1], broken["rows"][0]
        broken = rebuild_dataset(broken)
        with self.assertRaisesRegex(EFSError, "canonically sorted"):
            validate_pit_dataset(broken)

    def test_212_scope_mismatch_rejected(self):
        broken = copy.deepcopy(self.dataset)
        broken["rows"][0]["instrument_id"] = "FIGI:OTHER"
        broken["rows"][0] = rebuild_row(broken["rows"][0])
        broken = rebuild_dataset(broken)
        with self.assertRaisesRegex(EFSError, "SCOPE_MISMATCH"):
            validate_pit_dataset(broken)

    def test_213_universe_scope_hash_is_bound(self):
        universe = copy.deepcopy(self.dataset)
        members = ["FIGI:BBG000BDTBL9", "FIGI:OTHER"]
        universe["scope"] = {"type": "universe_snapshot_v1", "members": members, "snapshot_sha256": sha256_hex(members)}
        universe = rebuild_dataset(universe)
        self.assertEqual(validate_pit_dataset(universe)["status"], "PASS")
        universe["scope"]["snapshot_sha256"] = "0" * 64
        universe = rebuild_dataset(universe)
        with self.assertRaisesRegex(EFSError, "HASH_MISMATCH"):
            validate_pit_dataset(universe)

    def test_214_unknown_top_level_key_rejected(self):
        broken = copy.deepcopy(self.dataset)
        broken["agent_fallback"] = True
        broken = rebuild_dataset(broken)
        with self.assertRaisesRegex(EFSError, "unknown keys"):
            validate_pit_dataset(broken)

    def test_215_schema_is_explicit(self):
        self.assertEqual(self.dataset["schema"], PIT_DATASET_SCHEMA)


if __name__ == "__main__":
    unittest.main()
