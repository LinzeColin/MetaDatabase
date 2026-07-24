#!/usr/bin/env python3
"""Fail-closed tests for the frozen independent forward-test evidence."""

from __future__ import annotations

import base64
import copy
import importlib.util
import hashlib
import json
import re
import shutil
import tempfile
import unittest
from pathlib import Path
from types import ModuleType
from typing import Any


SKILL_ROOT = Path(__file__).resolve().parents[1]
VALIDATOR_PATH = SKILL_ROOT / "scripts" / "validate_forward_test.py"


def load_validator() -> ModuleType:
    spec = importlib.util.spec_from_file_location("validate_forward_test", VALIDATOR_PATH)
    if spec is None or spec.loader is None:
        raise RuntimeError("cannot load forward-test validator")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


VALIDATOR = load_validator()


class ForwardTestTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory(prefix="bss-forward-test-")
        self.root = Path(self.temporary.name) / "bottleneck-serenity-skill"
        shutil.copytree(SKILL_ROOT, self.root)
        self.forward = self.root / "evals" / "forward_test"

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def load_json(self, name: str) -> dict[str, Any]:
        return json.loads((self.forward / name).read_text(encoding="utf-8"))

    def write_json(self, name: str, value: dict[str, Any]) -> None:
        (self.forward / name).write_text(
            json.dumps(value, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )

    def rebind_result_artifact(self, field: str, name: str) -> None:
        result = self.load_json("result.json")
        result["artifact_bindings"][field] = hashlib.sha256(
            (self.forward / name).read_bytes()
        ).hexdigest()
        self.write_json("result.json", result)

    def validate(self) -> dict[str, int | str]:
        return VALIDATOR.validate_all(self.root)

    def test_frozen_forward_test_passes(self) -> None:
        summary = self.validate()
        self.assertEqual(summary["status"], "PASS")
        self.assertEqual(summary["context_file_count"], 30)
        self.assertEqual(summary["executor_trial_count"], 19)
        self.assertEqual(summary["judge_count"], 2)
        self.assertEqual(summary["maximum_score"], 24)
        self.assertGreaterEqual(summary["total_score"], 20)
        self.assertEqual(summary["provider_provenance"], "LIVE_WITNESS_READY")
        self.assertEqual(summary["provider_generation_protocol"], "PASS")
        self.assertEqual(
            summary["provider_live_review_task"],
            "BSS-S3-P3-T017",
        )
        self.assertEqual(summary["provider_attestation_attempt_count"], 3)
        self.assertEqual(summary["provider_interval_seconds"], 205)

    def test_answer_key_leakage_fails_closed(self) -> None:
        value = self.load_json("preregistration.json")
        value["context_contract"]["answer_key_provided"] = True
        self.write_json("preregistration.json", value)
        with self.assertRaisesRegex(VALIDATOR.ForwardTestError, "answer_key_provided"):
            self.validate()

    def test_baseline_artifact_mutation_fails_closed(self) -> None:
        path = self.forward / "baseline_raw_output.md"
        path.write_text(
            path.read_text(encoding="utf-8") + "mutated\n",
            encoding="utf-8",
        )
        with self.assertRaisesRegex(
            VALIDATOR.ForwardTestError, "immutable baseline artifact drift"
        ):
            self.validate()

    def test_remediation_lineage_mutation_fails_closed(self) -> None:
        value = self.load_json("remediation.json")
        value["unseen_rerun"]["prior_diagnoses_in_executor_context"] = True
        self.write_json("remediation.json", value)
        with self.assertRaisesRegex(
            VALIDATOR.ForwardTestError, "unseen-rerun binding drift"
        ):
            self.validate()

    def test_trial_02_artifact_mutation_fails_closed(self) -> None:
        path = self.forward / "trial_02_raw_output.md"
        path.write_text(
            path.read_text(encoding="utf-8") + "mutated\n",
            encoding="utf-8",
        )
        with self.assertRaisesRegex(
            VALIDATOR.ForwardTestError, "immutable trial-02 artifact drift"
        ):
            self.validate()

    def test_context_target_hash_mutation_fails_closed(self) -> None:
        value = self.load_json("context_manifest.json")
        value["files"][0]["sha256"] = "0" * 64
        self.write_json("context_manifest.json", value)
        with self.assertRaisesRegex(VALIDATOR.ForwardTestError, "context target drift"):
            self.validate()

    def test_raw_output_mutation_fails_closed(self) -> None:
        path = self.forward / "raw_output.md"
        path.write_text(
            path.read_text(encoding="utf-8") + "mutated\n",
            encoding="utf-8",
        )
        with self.assertRaisesRegex(VALIDATOR.ForwardTestError, "trace artifact binding drift"):
            self.validate()

    def test_parent_repository_read_fails_closed(self) -> None:
        value = self.load_json("trace.json")
        value["observations"]["parent_or_sibling_repository_reads"] = ["parent/file"]
        self.write_json("trace.json", value)
        with self.assertRaisesRegex(VALIDATOR.ForwardTestError, "boundary violation"):
            self.validate()

    def test_trace_section_hash_mutation_fails_closed(self) -> None:
        value = self.load_json("trace.json")
        value["observations"]["raw_execution_trace_sha256"] = "0" * 64
        self.write_json("trace.json", value)
        with self.assertRaisesRegex(VALIDATOR.ForwardTestError, "does not bind"):
            self.validate()

    def test_non_verbatim_judge_quote_fails_closed(self) -> None:
        value = self.load_json("judge_a.json")
        value["scores"][0]["evidence_quote"] = "not in the preserved raw output"
        self.write_json("judge_a.json", value)
        self.rebind_result_artifact("judge_a_sha256", "judge_a.json")
        with self.assertRaisesRegex(VALIDATOR.ForwardTestError, "not verbatim"):
            self.validate()

    def test_judge_score_arithmetic_mutation_fails_closed(self) -> None:
        value = self.load_json("judge_a.json")
        value["scores"][0]["score"] = 1
        self.write_json("judge_a.json", value)
        self.rebind_result_artifact("judge_a_sha256", "judge_a.json")
        with self.assertRaisesRegex(VALIDATOR.ForwardTestError, "total score arithmetic"):
            self.validate()

    def test_multiple_executor_trials_fail_closed(self) -> None:
        value = self.load_json("result.json")
        value["methodology"]["executor_trial_count"] = 4
        self.write_json("result.json", value)
        with self.assertRaisesRegex(VALIDATOR.ForwardTestError, "methodology drift"):
            self.validate()

    def test_result_artifact_binding_mutation_fails_closed(self) -> None:
        value = self.load_json("result.json")
        value["artifact_bindings"]["judge_a_sha256"] = "0" * 64
        self.write_json("result.json", value)
        with self.assertRaisesRegex(VALIDATOR.ForwardTestError, "artifact binding drift"):
            self.validate()

    def test_result_verdict_mutation_fails_closed(self) -> None:
        value = self.load_json("result.json")
        value["verdict"] = "FAIL"
        self.write_json("result.json", value)
        with self.assertRaisesRegex(VALIDATOR.ForwardTestError, "verdict arithmetic"):
            self.validate()

    def test_current_preexecution_seal_mutation_fails_closed(self) -> None:
        value = self.load_json("preexecution_seal_v18.json")
        value["artifact_bindings"]["remediation_v18_task_message_sha256"] = "0" * 64
        self.write_json("preexecution_seal_v18.json", value)
        with self.assertRaisesRegex(
            VALIDATOR.ForwardTestError, "v18 frozen artifact drift"
        ):
            self.validate()

    def test_current_context_manifest_mutation_fails_closed(self) -> None:
        value = self.load_json("remediation_v18_context_manifest.json")
        value["files"][0]["sha256"] = "0" * 64
        self.write_json("remediation_v18_context_manifest.json", value)
        with self.assertRaisesRegex(
            VALIDATOR.ForwardTestError, "v18 frozen artifact drift"
        ):
            self.validate()

    def test_current_post_execution_remediation_mutation_fails_closed(self) -> None:
        value = self.load_json("remediation_v18_post_execution_remediation.json")
        value["changes"][0]["current"]["sha256"] = "0" * 64
        self.write_json("remediation_v18_post_execution_remediation.json", value)
        with self.assertRaisesRegex(
            VALIDATOR.ForwardTestError, "post-execution remediation drift"
        ):
            self.validate()

    def test_current_t014_remediation_mutation_fails_closed(self) -> None:
        name = "remediation_v18_post_execution_remediation_t014.json"
        value = self.load_json(name)
        value["changes"][0]["current"]["sha256"] = "0" * 64
        self.write_json(name, value)
        with self.assertRaisesRegex(
            VALIDATOR.ForwardTestError, "T014 post-execution remediation drift"
        ):
            self.validate()

    def test_current_presentation_helper_unbound_drift_fails_closed(self) -> None:
        path = self.root / "scripts" / "presentation_contract.py"
        path.write_text(
            path.read_text(encoding="utf-8") + "\n# unbound mutation\n",
            encoding="utf-8",
        )
        with self.assertRaisesRegex(
            VALIDATOR.ForwardTestError, "post-execution current target drift"
        ):
            self.validate()

    def test_provider_generation_task_mutation_fails_closed(self) -> None:
        path = self.forward / "provider_generation_v23_task.txt"
        path.write_text(
            path.read_text(encoding="utf-8") + "mutation\n",
            encoding="utf-8",
        )
        with self.assertRaisesRegex(
            VALIDATOR.ForwardTestError,
            "provider generation artifact drift",
        ):
            self.validate()

    def test_v22_cannot_be_repromoted_as_generation_proof(self) -> None:
        value = self.load_json(
            "provider_attestation_v22_review_disposition.json"
        )
        value["admissible_as_provider_generation_proof"] = True
        self.write_json(
            "provider_attestation_v22_review_disposition.json",
            value,
        )
        with self.assertRaisesRegex(
            VALIDATOR.ForwardTestError,
            "provider generation artifact drift|review disposition drift",
        ):
            self.validate()

    def test_current_raw_storage_mutation_fails_closed(self) -> None:
        path = self.forward / "remediation_v18_raw.json"
        path.write_text(
            path.read_text(encoding="utf-8").rstrip("\n") + " \n",
            encoding="utf-8",
        )
        with self.assertRaisesRegex(
            VALIDATOR.ForwardTestError, "v18 frozen artifact drift"
        ):
            self.validate()

    def test_current_exact_stdin_mutation_fails_closed(self) -> None:
        raw_path = self.forward / "remediation_v18_raw.json"
        raw = json.loads(raw_path.read_text(encoding="utf-8"))
        raw["evidence_json"] += " "
        with self.assertRaisesRegex(
            VALIDATOR.ForwardTestError, "exact-returned-field trace mismatch: evidence"
        ):
            VALIDATOR._current_forward_replay_fields(self.root, raw)

    def test_current_brand_before_security_map_fails_closed(self) -> None:
        raw_path = self.forward / "remediation_v18_raw.json"
        raw = json.loads(raw_path.read_text(encoding="utf-8"))
        raw["memo_markdown"] = raw["memo_markdown"].replace(
            "## Funded demand",
            "MSCI ACWI\n\n## Funded demand",
            1,
        )
        with self.assertRaisesRegex(
            VALIDATOR.ForwardTestError, "before Security map"
        ):
            VALIDATOR.validate_current_presentation(raw)

    def test_current_unknown_issuer_shapes_fail_closed(self) -> None:
        raw = self.load_json("remediation_v18_raw.json")
        original = raw["memo_markdown"]
        presentation_oracles = json.loads(
            (self.root / "evals/presentation_oracles.json").read_text(
                encoding="utf-8"
            )
        )
        issuer_shapes = (
            "ABB",
            "Acme",
            "Acme Holdings",
            "Acme supplies equipment",
            "Blue Origin",
            "$ZZZ",
            "1234.T",
            "Example Exchange",
            "Acme plc",
            "nvidia",
            "acme supplies equipment",
            "www.acme.com/research",
            "ftp://acme.com/file",
            "acme.com/research",
            "research@acme.com",
            "The constrained node is controlled by Acme under current rules",
            "A single source, nvidia, controls qualification under current rules",
            "Acme's qualified line controls supply under current rules",
            "The issuer is nvidia",
            "The selected security is nvidia",
            "Our benchmark is acme global",
            "A candidate supplier is nvidia",
            "One listed issuer, acme, may capture the rent",
            "Demand from nvidia remains funded",
            "The system depends on acme for supply",
            "The critical supplier is `nvidia`",
            "A supplier called acme builds equipment",
            "nvidia is the supplier",
            "The manufacturer is nvidia",
            "nvidia may supply qualified equipment",
            "Procurement relies on nvidia",
            "The bottleneck owner named nvidia controls supply",
            "We shortlisted nvidia for the role",
            "Capacity at nvidia remains constrained",
            "The primary vendor, nvidia, has spare slots",
            "nvidia remains the only qualified source",
            "The winner was nvidia",
            "Source: nvidia annual report",
            "Demand is routed through nvidia",
            "Critical capacity belongs to nvidia",
            "Funding is supplied by acme",
            "This leaves nvidia as the only listed exposure",
            *presentation_oracles["negative_issuer_slots"],
        )
        for issuer_shape in issuer_shapes:
            with self.subTest(issuer_shape=issuer_shape):
                raw["memo_markdown"] = original.replace(
                    "## Funded demand",
                    f"{issuer_shape}\n\n## Funded demand",
                    1,
                )
                with self.assertRaisesRegex(
                    VALIDATOR.ForwardTestError, "before Security map"
                ):
                    VALIDATOR.validate_current_presentation(raw)
        raw["memo_markdown"] = original

    def test_current_role_neutral_generic_prose_remains_valid(self) -> None:
        raw = self.load_json("remediation_v18_raw.json")
        presentation_oracles = json.loads(
            (self.root / "evals/presentation_oracles.json").read_text(
                encoding="utf-8"
            )
        )
        reviewed_positive_prose = " ".join(
            presentation_oracles["positive_role_neutral_statements"]
        )
        raw["memo_markdown"] = raw["memo_markdown"].replace(
            "## Funded demand",
            (
                "AI is a generic demand driver, not an issuer identity.\n\n"
                "A qualified equipment manufacturer may expand capacity without "
                "creating durable shareholder rent.\n\n"
                "Demand is funded through committed procurement.\n\n"
                "Capacity may expand before monetization.\n\n"
                "Suppliers can add generic production lines.\n\n"
                "Owner controls the constrained node.\n\n"
                "Unlocker supplies missing capacity.\n\n"
                "Substitute provides an alternative architecture.\n\n"
                "Tollbooth operates the qualification gate.\n\n"
                "Absorber owns compatible spare slots.\n\n"
                "Public proxy offers liquid exposure.\n\n"
                "Manufacturer may supply qualified equipment.\n\n"
                "Vendor provides generic capacity.\n\n"
                "Fragile. Uncertain. Qualified. Constrained. Funded. "
                "Substitutable.\n\n"
                "The mandatory roles are Factory Testing and Specialized Logistics."
                f"\n\n{reviewed_positive_prose}"
                "\n\n## Funded demand"
            ),
            1,
        )
        VALIDATOR.validate_current_presentation(raw)

    def test_current_rejections_preserve_full_entity_witness(self) -> None:
        presentation_oracles = json.loads(
            (self.root / "evals/presentation_oracles.json").read_text(
                encoding="utf-8"
            )
        )
        helper_path = self.root / "scripts/presentation_contract.py"
        spec = importlib.util.spec_from_file_location(
            "_bss_forward_entity_witness_contract",
            helper_path,
        )
        self.assertIsNotNone(spec)
        self.assertIsNotNone(spec.loader if spec else None)
        helper = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(helper)

        def normalized(value: str) -> str:
            return " ".join(re.findall(r"[^\W_]+", value.casefold()))

        for witness in presentation_oracles["negative_entity_witnesses"]:
            with self.subTest(statement=witness["statement"]):
                violations = helper.find_role_neutral_violations(
                    f"{witness['statement']}\n\n## Security map",
                    "## Security map",
                )
                expected = normalized(witness["entity"])
                self.assertTrue(
                    any(expected in normalized(value) for value in violations),
                    msg=(
                        f"full entity witness missing: {witness['entity']!r}; "
                        f"violations={violations!r}"
                    ),
                )

    def test_current_formal_template_is_role_neutral(self) -> None:
        template = (
            self.root / "templates/investment_memo.md"
        ).read_text(encoding="utf-8")
        helper_path = self.root / "scripts/presentation_contract.py"
        spec = importlib.util.spec_from_file_location(
            "_bss_test_presentation_contract",
            helper_path,
        )
        self.assertIsNotNone(spec)
        self.assertIsNotNone(spec.loader if spec else None)
        helper = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(helper)
        self.assertEqual(
            helper.find_role_neutral_violations(
                template,
                "## Security map",
            ),
            [],
        )

    def test_current_judge_verdict_mutation_fails_closed(self) -> None:
        value = self.load_json("remediation_v18_judge_a.json")
        value["verdict"] = "FAIL"
        self.write_json("remediation_v18_judge_a.json", value)
        with self.assertRaisesRegex(
            VALIDATOR.ForwardTestError, "v18 frozen artifact drift"
        ):
            self.validate()

    def test_current_executor_schema_mutation_fails_closed(self) -> None:
        value = self.load_json("executor_output_v18.schema.json")
        del value["definitions"]["replay"]["properties"]["stdout_sha256"]
        with self.assertRaisesRegex(
            VALIDATOR.ForwardTestError, "closed replay envelope"
        ):
            VALIDATOR.validate_current_forward_schema_contract(value)

    def test_v14_failed_verdict_cannot_be_promoted(self) -> None:
        value = self.load_json("remediation_v14_result.json")
        value["outcome"] = "PASS"
        self.write_json("remediation_v14_result.json", value)
        with self.assertRaisesRegex(
            VALIDATOR.ForwardTestError, "v14 immutable failure result drift"
        ):
            self.validate()

    def test_v15_preflight_failure_cannot_be_promoted(self) -> None:
        value = self.load_json("remediation_v15_result.json")
        value["outcome"] = "PASS"
        self.write_json("remediation_v15_result.json", value)
        with self.assertRaisesRegex(
            VALIDATOR.ForwardTestError, "v15 immutable failure result drift"
        ):
            self.validate()

    def test_v16_preflight_failure_cannot_be_promoted(self) -> None:
        value = self.load_json("remediation_v16_result.json")
        value["outcome"] = "PASS"
        self.write_json("remediation_v16_result.json", value)
        with self.assertRaisesRegex(
            VALIDATOR.ForwardTestError, "v16 immutable failure result drift"
        ):
            self.validate()

    def test_v17_exact_trace_failure_cannot_be_promoted(self) -> None:
        value = self.load_json("remediation_v17_result.json")
        value["outcome"] = "PASS"
        self.write_json("remediation_v17_result.json", value)
        with self.assertRaisesRegex(
            VALIDATOR.ForwardTestError, "v17 immutable failure result drift"
        ):
            self.validate()

    def test_current_lineage_mutation_fails_closed(self) -> None:
        value = self.load_json("remediation_v18_result.json")
        value["prior_attempt_lineage"][16]["ordinal"] = 99
        self.write_json("remediation_v18_result.json", value)
        with self.assertRaisesRegex(
            VALIDATOR.ForwardTestError, "v18 frozen artifact drift"
        ):
            self.validate()

    def test_v19_control_packet_mutation_fails_closed(self) -> None:
        value = self.load_json("control_packet_v19.json")
        value["projection_tree_sha256"] = "0" * 64
        self.write_json("control_packet_v19.json", value)
        with self.assertRaisesRegex(
            VALIDATOR.ForwardTestError, "v19 frozen artifact drift"
        ):
            self.validate()

    def test_v19_timestamp_response_mutation_fails_cryptographically(self) -> None:
        value = self.load_json("preexecution_timestamp_v19.json")
        response = bytearray(base64.b64decode(value["response"]["payload_base64"]))
        response[-1] ^= 1
        value["response"]["payload_base64"] = base64.b64encode(response).decode(
            "ascii"
        )
        value["response"]["sha256"] = hashlib.sha256(response).hexdigest()
        with self.assertRaisesRegex(
            VALIDATOR.ForwardTestError, "RFC3161 verification failed"
        ):
            VALIDATOR.validate_v19_timestamp_contract(self.forward, value)

    def test_v19_external_timestamp_must_precede_executor(self) -> None:
        preregistration = self.load_json("remediation_v19_preregistration.json")
        timestamp = self.load_json("preexecution_timestamp_v19.json")
        execution = self.load_json("remediation_v19_execution.json")
        execution["started_at_utc"] = timestamp["response"]["gen_time_utc"]
        execution["independent_preexecution_ordering"][
            "minimum_observed_lead_seconds"
        ] = 0
        with self.assertRaisesRegex(
            VALIDATOR.ForwardTestError,
            "independent preexecution ordering drift",
        ):
            VALIDATOR.validate_v19_execution_ordering(
                preregistration,
                timestamp,
                execution,
            )

    def test_v19_generic_session_object_and_uuid_v4_fail_closed(self) -> None:
        for payload in (
            {"session": {"engine": "synthetic"}},
            {"receipt": "123e4567-e89b-42d3-a456-426614174000"},
        ):
            with self.subTest(payload=payload):
                with self.assertRaisesRegex(
                    VALIDATOR.ForwardTestError,
                    "forbidden execution session metadata",
                ):
                    VALIDATOR._current_forward_reject_session_metadata(
                        payload,
                        "synthetic",
                    )

    def test_v19_judge_verdict_mutation_fails_closed(self) -> None:
        value = self.load_json("remediation_v19_judge_b.json")
        value["verdict"] = "FAIL"
        self.write_json("remediation_v19_judge_b.json", value)
        with self.assertRaisesRegex(
            VALIDATOR.ForwardTestError, "v19 frozen artifact drift"
        ):
            self.validate()

    def test_provider_post_timestamp_mutation_fails_cryptographically(
        self,
    ) -> None:
        name = "provider_attestation_v22_post_timestamp.json"
        value = self.load_json(name)
        response = bytearray(
            base64.b64decode(value["response"]["der_base64"])
        )
        response[-1] ^= 1
        value["response"]["der_base64"] = base64.b64encode(response).decode(
            "ascii"
        )
        value["response"]["sha256"] = hashlib.sha256(response).hexdigest()
        self.write_json(name, value)
        with self.assertRaisesRegex(
            VALIDATOR.ForwardTestError,
            "RFC3161 verification failed",
        ):
            VALIDATOR._validate_provider_rfc3161_timestamp(
                self.forward,
                name,
                "provider_attestation_v22_post_packet.json",
                "BSS-S3-P3-T010-provider-attestation-v22",
                "postexecution",
            )

    def test_provider_whole_timeline_shift_mutant_is_killed_after_rebind(
        self,
    ) -> None:
        host_name = "provider_attestation_v22_host_receipt.json"
        post_name = "provider_attestation_v22_post_packet.json"
        timestamp_name = "provider_attestation_v22_post_timestamp.json"
        result_name = "provider_attestation_v22_result.json"
        host = self.load_json(host_name)
        host["execution"]["started_at_utc"] = "2026-07-24T18:38:46Z"
        host["execution"]["finished_at_utc"] = "2026-07-24T18:39:32Z"
        self.write_json(host_name, host)
        host_sha = hashlib.sha256(
            (self.forward / host_name).read_bytes()
        ).hexdigest()
        post = self.load_json(post_name)
        post["execution"]["host_receipt_sha256"] = host_sha
        self.write_json(post_name, post)
        post_sha = hashlib.sha256(
            (self.forward / post_name).read_bytes()
        ).hexdigest()
        timestamp = self.load_json(timestamp_name)
        timestamp["packet"]["sha256"] = post_sha
        timestamp["packet"]["byte_count"] = (
            self.forward / post_name
        ).stat().st_size
        timestamp["request"]["message_imprint_sha256"] = post_sha
        self.write_json(timestamp_name, timestamp)
        timestamp_sha = hashlib.sha256(
            (self.forward / timestamp_name).read_bytes()
        ).hexdigest()
        result = self.load_json(result_name)
        result["artifact_bindings"][host_name] = host_sha
        result["artifact_bindings"][post_name] = post_sha
        result["artifact_bindings"][timestamp_name] = timestamp_sha
        self.write_json(result_name, result)
        result_sha = hashlib.sha256(
            (self.forward / result_name).read_bytes()
        ).hexdigest()
        original = dict(VALIDATOR.PROVIDER_ATTESTATION_ARTIFACT_SHA256)
        try:
            VALIDATOR.PROVIDER_ATTESTATION_ARTIFACT_SHA256.update(
                {
                    host_name: host_sha,
                    post_name: post_sha,
                    timestamp_name: timestamp_sha,
                    result_name: result_sha,
                }
            )
            with self.assertRaisesRegex(
                VALIDATOR.ForwardTestError,
                "query imprint drift",
            ):
                self.validate()
        finally:
            VALIDATOR.PROVIDER_ATTESTATION_ARTIFACT_SHA256.clear()
            VALIDATOR.PROVIDER_ATTESTATION_ARTIFACT_SHA256.update(original)

    def test_provider_false_pass_lineage_cannot_be_promoted(self) -> None:
        failure_name = "provider_attestation_v21_failure.json"
        result_name = "provider_attestation_v22_result.json"
        failure = self.load_json(failure_name)
        failure["outcome"] = "PASS"
        failure["substantive_provider_attestation"] = True
        self.write_json(failure_name, failure)
        failure_sha = hashlib.sha256(
            (self.forward / failure_name).read_bytes()
        ).hexdigest()
        result = self.load_json(result_name)
        result["artifact_bindings"][failure_name] = failure_sha
        self.write_json(result_name, result)
        result_sha = hashlib.sha256(
            (self.forward / result_name).read_bytes()
        ).hexdigest()
        original = dict(VALIDATOR.PROVIDER_ATTESTATION_ARTIFACT_SHA256)
        try:
            VALIDATOR.PROVIDER_ATTESTATION_ARTIFACT_SHA256.update(
                {
                    failure_name: failure_sha,
                    result_name: result_sha,
                }
            )
            with self.assertRaisesRegex(
                VALIDATOR.ForwardTestError,
                "v21 failed-lineage drift",
            ):
                self.validate()
        finally:
            VALIDATOR.PROVIDER_ATTESTATION_ARTIFACT_SHA256.clear()
            VALIDATOR.PROVIDER_ATTESTATION_ARTIFACT_SHA256.update(original)

    def test_current_preregistration_semantic_controls_fail_closed(self) -> None:
        original = self.load_json("remediation_v18_preregistration.json")
        mutations = (
            ("missing manifest", lambda value: value["context_contract"].update(
                {"manifest_path": "evals/forward_test/missing.json"}
            )),
            ("user config", lambda value: value["execution_contract"].update(
                {"user_config_loaded": True}
            )),
            ("project rules", lambda value: value["execution_contract"].update(
                {"project_rules_loaded": True}
            )),
        )
        for label, mutate in mutations:
            with self.subTest(label=label):
                value = copy.deepcopy(original)
                mutate(value)
                with self.assertRaisesRegex(
                    VALIDATOR.ForwardTestError,
                    "preregistration identity/contract drift",
                ):
                    VALIDATOR.validate_current_forward_preregistration_contract(value)

    def test_current_preregistration_context_semantics_fail_closed(self) -> None:
        original = self.load_json("remediation_v18_preregistration.json")
        VALIDATOR.validate_current_forward_preregistration_contract(original)
        for field, replacement in (
            ("allowed_context", "expected answer and diagnosis"),
            ("excluded_context", "answer keys explicitly allowed"),
        ):
            for index in range(len(original["context_contract"][field])):
                with self.subTest(field=field, index=index):
                    value = copy.deepcopy(original)
                    value["context_contract"][field][index] = (
                        f"{replacement} at slot {index}"
                    )
                    with self.assertRaisesRegex(
                        VALIDATOR.ForwardTestError,
                        "preregistration identity/contract drift",
                    ):
                        VALIDATOR.validate_current_forward_preregistration_contract(
                            value
                        )
            with self.subTest(field=field, mutation="order"):
                value = copy.deepcopy(original)
                value["context_contract"][field].reverse()
                with self.assertRaisesRegex(
                    VALIDATOR.ForwardTestError,
                    "preregistration identity/contract drift",
                ):
                    VALIDATOR.validate_current_forward_preregistration_contract(value)

    def test_current_execution_semantic_controls_fail_closed(self) -> None:
        prereg = self.load_json("remediation_v18_preregistration.json")
        seal = self.load_json("preexecution_seal_v18.json")
        original = self.load_json("remediation_v18_execution.json")
        mutations = (
            ("exit", lambda value: value.update({"exit_code": 99})),
            ("control", lambda value: value["execution_controls"].update(
                {"user_config_loaded": True}
            )),
            ("time", lambda value: value.update(
                {"started_at_utc": "2026-07-23T00:00:00Z"}
            )),
        )
        for label, mutate in mutations:
            with self.subTest(label=label):
                value = copy.deepcopy(original)
                mutate(value)
                with self.assertRaises(VALIDATOR.ForwardTestError):
                    VALIDATOR.validate_current_forward_execution_receipt_contract(
                        prereg,
                        seal,
                        value,
                    )


if __name__ == "__main__":
    unittest.main()
