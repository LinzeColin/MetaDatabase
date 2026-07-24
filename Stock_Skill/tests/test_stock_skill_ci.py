#!/usr/bin/env python3
"""Durable negative oracles for the Stock Skill CI helpers."""

from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile, ZipInfo


REPO_ROOT = Path(__file__).resolve().parents[2]
TEST_RUNNER = REPO_ROOT / "Stock_Skill/scripts/run_unittests.py"
SAFETY_VALIDATOR = REPO_ROOT / "Stock_Skill/scripts/validate_public_safety.py"
BSS_TASK_GRAPH = (
    REPO_ROOT
    / "Stock_Skill/bottleneck-serenity-skill/task-pack/03_STAGE_PHASE_TASKS.md"
)
BSS_ACCEPTANCE = (
    REPO_ROOT
    / "Stock_Skill/bottleneck-serenity-skill/task-pack/"
    "04_ACCEPTANCE_VALIDATION_STOP.md"
)
SYNTHETIC_FINE_GRAINED_PAT = "github_" + "pat_" + ("A" * 82)
SYNTHETIC_STATELESS_APP_TOKEN = (
    "ghs_"
    + "12345_"
    + "eyJhbGciOiJSUzI1NiJ9."
    + ("A" * 80)
    + "."
    + ("B" * 79)
    + "-"
)


class StockSkillCiHelperTests(unittest.TestCase):
    @staticmethod
    def _stage3_review_task_ids(task_graph: str) -> tuple[str, ...]:
        result: list[str] = []
        row = re.compile(
            r"^\| `(?P<task>BSS-S3-P3-T[0-9]{3})` "
            r"\| (?P<phase>[^|]+?) \|"
        )
        for line in task_graph.splitlines():
            match = row.match(line)
            if match and match.group("phase").strip().startswith(
                ("Review", "Re-review")
            ):
                result.append(match.group("task"))
        return tuple(result)

    @staticmethod
    def _stage3_acceptance_verifiers(
        acceptance: str,
    ) -> dict[str, tuple[str, ...]]:
        result: dict[str, tuple[str, ...]] = {}
        for line in acceptance.splitlines():
            if not line.startswith("| `ACC-S3-"):
                continue
            cells = [cell.strip() for cell in line.split("|")]
            acceptance_id = cells[1].strip("`")
            result[acceptance_id] = tuple(
                re.findall(r"BSS-S3-P3-T[0-9]{3}", cells[4])
            )
        return result

    def _run(self, script: Path, root: Path) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [sys.executable, "-B", str(script), "--repo-root", str(root)],
            text=True,
            capture_output=True,
            check=False,
            env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1"},
        )

    @staticmethod
    def _public_fixture(root: Path) -> Path:
        (root / "Stock_Skill").mkdir(parents=True)
        (root / "AGENTS.md").write_text("public rules\n", encoding="utf-8")
        (root / "README.md").write_text("public readme\n", encoding="utf-8")
        stock_readme = root / "Stock_Skill/README.md"
        stock_readme.write_text("public stock skills\n", encoding="utf-8")
        return stock_readme

    def test_unittest_runner_rejects_zero_case_file(self) -> None:
        with tempfile.TemporaryDirectory(prefix="stock-ci-zero-case-") as raw:
            root = Path(raw)
            tests = root / "Stock_Skill/tests"
            tests.mkdir(parents=True)
            (tests / "test_empty.py").write_bytes(b"")
            result = self._run(TEST_RUNNER, root)
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("zero test cases", result.stderr)

    def test_stage3_acceptance_verifiers_equal_derived_review_sequence(
        self,
    ) -> None:
        review_ids = self._stage3_review_task_ids(
            BSS_TASK_GRAPH.read_text(encoding="utf-8")
        )
        self.assertEqual(
            review_ids,
            (
                "BSS-S3-P3-T001",
                "BSS-S3-P3-T003",
                "BSS-S3-P3-T005",
                "BSS-S3-P3-T007",
                "BSS-S3-P3-T009",
                "BSS-S3-P3-T011",
                "BSS-S3-P3-T013",
                "BSS-S3-P3-T015",
                "BSS-S3-P3-T017",
                "BSS-S3-P3-T019",
            ),
        )
        verifiers = self._stage3_acceptance_verifiers(
            BSS_ACCEPTANCE.read_text(encoding="utf-8")
        )
        self.assertEqual(
            tuple(verifiers),
            tuple(f"ACC-S3-{ordinal:03d}" for ordinal in range(1, 11)),
        )
        for acceptance_id, observed in verifiers.items():
            with self.subTest(acceptance_id=acceptance_id):
                self.assertEqual(observed, review_ids)

    def test_stage3_acceptance_verifier_omission_mutant_is_killed(self) -> None:
        source = BSS_ACCEPTANCE.read_text(encoding="utf-8")
        mutated = source.replace(
            "; `BSS-S3-P3-T009`",
            "",
            1,
        )
        self.assertNotEqual(source, mutated)
        review_ids = self._stage3_review_task_ids(
            BSS_TASK_GRAPH.read_text(encoding="utf-8")
        )
        verifiers = self._stage3_acceptance_verifiers(mutated)
        self.assertTrue(
            any(observed != review_ids for observed in verifiers.values())
        )

    def test_unittest_runner_reports_actual_positive_case_count(self) -> None:
        with tempfile.TemporaryDirectory(prefix="stock-ci-positive-case-") as raw:
            root = Path(raw)
            tests = root / "Stock_Skill/tests"
            tests.mkdir(parents=True)
            (tests / "test_one.py").write_text(
                "import unittest\n"
                "class OneTest(unittest.TestCase):\n"
                "    def test_one(self): self.assertTrue(True)\n",
                encoding="utf-8",
            )
            result = self._run(TEST_RUNNER, root)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertIn("PASS: 1 test case(s)", result.stdout)

    def test_unittest_runner_rejects_failing_case(self) -> None:
        with tempfile.TemporaryDirectory(prefix="stock-ci-failing-case-") as raw:
            root = Path(raw)
            tests = root / "Stock_Skill/tests"
            tests.mkdir(parents=True)
            (tests / "test_failure.py").write_text(
                "import unittest\n"
                "class FailureTest(unittest.TestCase):\n"
                "    def test_failure(self): self.fail('synthetic failure')\n",
                encoding="utf-8",
            )
            result = self._run(TEST_RUNNER, root)
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("FAILED", result.stderr)

    def test_public_safety_rejects_fine_grained_pat_in_plain_file(self) -> None:
        with tempfile.TemporaryDirectory(prefix="stock-ci-pat-plain-") as raw:
            root = Path(raw)
            stock_readme = self._public_fixture(root)
            stock_readme.write_text(
                f"synthetic credential: {SYNTHETIC_FINE_GRAINED_PAT}\n",
                encoding="utf-8",
            )
            result = self._run(SAFETY_VALIDATOR, root)
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("forbidden GitHub fine-grained PAT", result.stderr)

    def test_public_safety_rejects_fine_grained_pat_in_zip_payload(self) -> None:
        with tempfile.TemporaryDirectory(prefix="stock-ci-pat-zip-") as raw:
            root = Path(raw)
            self._public_fixture(root)
            archive_path = root / "Stock_Skill/synthetic.zip"
            with ZipFile(archive_path, "w", compression=ZIP_DEFLATED) as archive:
                archive.writestr("payload.txt", SYNTHETIC_FINE_GRAINED_PAT)
            result = self._run(SAFETY_VALIDATOR, root)
            self.assertNotEqual(result.returncode, 0)
            self.assertIn(
                "synthetic.zip!payload.txt: forbidden GitHub fine-grained PAT",
                result.stderr,
            )

    def test_public_safety_rejects_session_receipt_in_plain_json(self) -> None:
        with tempfile.TemporaryDirectory(prefix="stock-ci-session-plain-") as raw:
            root = Path(raw)
            self._public_fixture(root)
            receipt = root / "Stock_Skill/execution.json"
            key = "session" + "_" + "id"
            synthetic_identifier = (
                "019f8eda" + "-8938-7be0-9d40-" + "e6062b91c909"
            )
            receipt.write_text(
                json.dumps({key: synthetic_identifier})
                + "\n",
                encoding="utf-8",
            )
            result = self._run(SAFETY_VALIDATOR, root)
            self.assertNotEqual(result.returncode, 0)
            self.assertIn(
                "forbidden execution session metadata",
                result.stderr,
            )

    def test_public_safety_rejects_session_receipt_in_zip_json(self) -> None:
        with tempfile.TemporaryDirectory(prefix="stock-ci-session-zip-") as raw:
            root = Path(raw)
            self._public_fixture(root)
            archive_path = root / "Stock_Skill/synthetic.zip"
            key = "session" + "_" + "id"
            synthetic_identifier = (
                "019f8eda" + "-8938-7be0-9d40-" + "e6062b91c909"
            )
            with ZipFile(archive_path, "w", compression=ZIP_DEFLATED) as archive:
                archive.writestr(
                    "receipt.json",
                    json.dumps({key: synthetic_identifier}),
                )
            result = self._run(SAFETY_VALIDATOR, root)
            self.assertNotEqual(result.returncode, 0)
            self.assertIn(
                "synthetic.zip!receipt.json: forbidden execution session metadata",
                result.stderr,
            )

    def test_public_safety_rejects_generic_session_object_in_plain_json(self) -> None:
        with tempfile.TemporaryDirectory(prefix="stock-ci-session-object-plain-") as raw:
            root = Path(raw)
            self._public_fixture(root)
            receipt = root / "Stock_Skill/execution.json"
            receipt.write_text(
                json.dumps({"session": {"engine": "synthetic"}}) + "\n",
                encoding="utf-8",
            )
            result = self._run(SAFETY_VALIDATOR, root)
            self.assertNotEqual(result.returncode, 0)
            self.assertIn(
                "forbidden execution session metadata at $.session",
                result.stderr,
            )

    def test_public_safety_rejects_generic_session_object_in_zip_json(self) -> None:
        with tempfile.TemporaryDirectory(prefix="stock-ci-session-object-zip-") as raw:
            root = Path(raw)
            self._public_fixture(root)
            archive_path = root / "Stock_Skill/synthetic.zip"
            with ZipFile(archive_path, "w", compression=ZIP_DEFLATED) as archive:
                archive.writestr(
                    "execution.json",
                    json.dumps({"session": {"engine": "synthetic"}}),
                )
            result = self._run(SAFETY_VALIDATOR, root)
            self.assertNotEqual(result.returncode, 0)
            self.assertIn(
                "synthetic.zip!execution.json: forbidden execution session metadata "
                "at $.session",
                result.stderr,
            )

    def test_public_safety_rejects_uuid_v4_execution_receipt_in_plain_json(self) -> None:
        with tempfile.TemporaryDirectory(prefix="stock-ci-session-v4-plain-") as raw:
            root = Path(raw)
            self._public_fixture(root)
            receipt = root / "Stock_Skill/execution.json"
            synthetic_identifier = "123e4567-e89b-42d3-a456-426614174000"
            receipt.write_text(
                json.dumps({"receipt": synthetic_identifier}) + "\n",
                encoding="utf-8",
            )
            result = self._run(SAFETY_VALIDATOR, root)
            self.assertNotEqual(result.returncode, 0)
            self.assertIn(
                "forbidden execution session identifier at $.receipt",
                result.stderr,
            )

    def test_public_safety_rejects_uuid_v4_execution_receipt_in_zip_json(self) -> None:
        with tempfile.TemporaryDirectory(prefix="stock-ci-session-v4-zip-") as raw:
            root = Path(raw)
            self._public_fixture(root)
            archive_path = root / "Stock_Skill/synthetic.zip"
            synthetic_identifier = "123e4567-e89b-42d3-a456-426614174000"
            with ZipFile(archive_path, "w", compression=ZIP_DEFLATED) as archive:
                archive.writestr(
                    "execution.json",
                    json.dumps({"receipt": synthetic_identifier}),
                )
            result = self._run(SAFETY_VALIDATOR, root)
            self.assertNotEqual(result.returncode, 0)
            self.assertIn(
                "synthetic.zip!execution.json: forbidden execution session "
                "identifier at $.receipt",
                result.stderr,
            )

    def test_public_safety_allows_uuid_v4_request_id_and_public_url(self) -> None:
        with tempfile.TemporaryDirectory(prefix="stock-ci-public-v4-") as raw:
            root = Path(raw)
            self._public_fixture(root)
            receipt = root / "Stock_Skill/public.json"
            synthetic_identifier = "123e4567-e89b-42d3-a456-426614174000"
            receipt.write_text(
                json.dumps(
                    {
                        "request_id": synthetic_identifier,
                        "source_url": (
                            "https://example.com/public/"
                            + synthetic_identifier
                        ),
                    }
                )
                + "\n",
                encoding="utf-8",
            )
            result = self._run(SAFETY_VALIDATOR, root)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_public_safety_rejects_private_metadata_synonym_matrix(self) -> None:
        variants = (
            "provider_session",
            "agent_session",
            "chat_session",
            "dialog_session",
            "interaction_session",
            "conversation_metadata",
            "thread_metadata",
            "session_details",
            "execution_session_info",
            "model_session_id",
            "run_session_id",
            "provider_thread_id",
            "provider_response_id",
            "execution_trace_id",
            "executor_session",
            "agent_session_id",
            "session_context",
            "execution_metadata",
            "execution_id",
            "provider_session_id",
            "thread_info",
            "run_id",
            "turn_uuid",
            "session_info",
            "execution_session_metadata",
            "model_session",
            "run_session",
            "session_state",
            "executor_receipt",
            "execution_record",
            "conversation_id",
            "thread_id",
            "chat_id",
            "turn_id",
            "execution_context",
            "agent_run",
            "conversation",
        )
        for surface in ("plain", "zip"):
            for key in variants:
                with self.subTest(surface=surface, key=key):
                    with tempfile.TemporaryDirectory(
                        prefix="stock-ci-private-metadata-"
                    ) as raw:
                        root = Path(raw)
                        self._public_fixture(root)
                        payload = json.dumps({key: {"private": "synthetic"}})
                        if surface == "plain":
                            (
                                root / "Stock_Skill/execution.json"
                            ).write_text(payload + "\n", encoding="utf-8")
                        else:
                            archive_path = root / "Stock_Skill/synthetic.zip"
                            with ZipFile(
                                archive_path,
                                "w",
                                compression=ZIP_DEFLATED,
                            ) as archive:
                                archive.writestr("execution.json", payload)
                        result = self._run(SAFETY_VALIDATOR, root)
                        self.assertNotEqual(
                            result.returncode,
                            0,
                            result.stdout + result.stderr,
                        )
                        self.assertIn(
                            "forbidden execution session metadata",
                            result.stderr,
                        )

    def test_public_safety_rejects_opaque_runtime_identifier_family(self) -> None:
        variants = (
            "inference_id",
            "completion_id",
            "generation_id",
            "invocation_id",
            "process_id",
            "worker_id",
            "span_id",
            "trace_id",
            "call_id",
            "job_id",
            "attempt_id",
            "request_context",
            "provider_token",
            "provider_correlation",
            "runtime_id",
            "runtime_receipt",
            "runtime_metadata",
            "runtime_uuid",
            "execution_token",
            "request_token",
            "provider_run_handle",
            "execution_attempt_handle",
            "job_handle",
        )
        synthetic_identifier = "123e4567-e89b-42d3-a456-426614174000"
        for surface in ("plain", "zip"):
            for key in variants:
                with self.subTest(surface=surface, key=key):
                    with tempfile.TemporaryDirectory(
                        prefix="stock-ci-opaque-runtime-id-"
                    ) as raw:
                        root = Path(raw)
                        self._public_fixture(root)
                        payload = json.dumps({key: synthetic_identifier})
                        if surface == "plain":
                            (
                                root / "Stock_Skill/execution.json"
                            ).write_text(payload + "\n", encoding="utf-8")
                        else:
                            with ZipFile(
                                root / "Stock_Skill/synthetic.zip",
                                "w",
                                compression=ZIP_DEFLATED,
                            ) as archive:
                                archive.writestr("execution.json", payload)
                        result = self._run(SAFETY_VALIDATOR, root)
                        self.assertNotEqual(
                            result.returncode,
                            0,
                            result.stdout + result.stderr,
                        )
                        self.assertIn(
                            "forbidden execution session metadata",
                            result.stderr,
                        )

    def test_public_safety_allows_public_business_identifier_controls(self) -> None:
        controls = {
            "public_claim_ref": "CLAIM-001",
            "evidence_record_key": "EV-001",
            "research_case_ref": "CASE-001",
            "listed_issuer_name": "Example Issuer",
            "listed_security_symbol": "EXM",
            "global_benchmark_label": "Example Global Index",
            "public_source_uri": "https://example.invalid/source",
            "publication_date": "2026-07-24",
            "analysis_as_of": "2026-07-24",
            "research_cutoff": "2026-07-24",
            "horizon_month_count": 24,
            "bottleneck_score": 72.5,
            "investment_decision": "WATCHLIST",
            "valuation_metric": "EV/EBITDA",
            "proposed_weight": 0.0,
            "portfolio_risk_bucket": "medium",
            "public_request_ref": "REQ-PUBLIC-001",
            "request_public_reference": "public-request-20260724",
            "artifact_schema_version": "1.0",
            "content_digest_sha256": "a" * 64,
            "execution_trace": {
                "validator_replay": {
                    "evidence": {
                        "result": {"claims": [{"id": "C-001"}]}
                    }
                }
            },
            "executor_validator_replay": {
                "first_attempt_python_alias_missing_exit_code": 1
            },
        }
        for surface in ("plain", "zip"):
            with self.subTest(surface=surface):
                with tempfile.TemporaryDirectory(
                    prefix="stock-ci-public-business-controls-"
                ) as raw:
                    root = Path(raw)
                    self._public_fixture(root)
                    payload = json.dumps(controls)
                    if surface == "plain":
                        (root / "Stock_Skill/public.json").write_text(
                            payload + "\n",
                            encoding="utf-8",
                        )
                    else:
                        with ZipFile(
                            root / "Stock_Skill/synthetic.zip",
                            "w",
                            compression=ZIP_DEFLATED,
                        ) as archive:
                            archive.writestr("public.json", payload)
                    result = self._run(SAFETY_VALIDATOR, root)
                    self.assertEqual(
                        result.returncode,
                        0,
                        result.stdout + result.stderr,
                    )

    def test_public_safety_rejects_split_runtime_metadata_paths(self) -> None:
        payloads = (
            {"provider": {"token": "opaque-provider-token"}},
            {"runtime": {"receipt": {"token": "opaque-runtime-token"}}},
            {"execution": [{"handle": "opaque-execution-handle"}]},
            {"job": {"correlation": "opaque-job-correlation"}},
            {"trace": {"token": "opaque-trace-token"}},
            {"request": {"metadata": {"token": "opaque-request-token"}}},
            {
                "request_public_reference": (
                    "123e4567-e89b-42d3-a456-426614174000"
                )
            },
            {"request_public_reference": {"token": "private"}},
        )
        for surface in ("plain", "zip"):
            for payload in payloads:
                with self.subTest(surface=surface, payload=payload):
                    with tempfile.TemporaryDirectory(
                        prefix="stock-ci-split-runtime-metadata-"
                    ) as raw:
                        root = Path(raw)
                        self._public_fixture(root)
                        encoded = json.dumps(payload)
                        if surface == "plain":
                            (root / "Stock_Skill/execution.json").write_text(
                                encoded + "\n",
                                encoding="utf-8",
                            )
                        else:
                            with ZipFile(
                                root / "Stock_Skill/synthetic.zip",
                                "w",
                                compression=ZIP_DEFLATED,
                            ) as archive:
                                archive.writestr("execution.json", encoded)
                        result = self._run(SAFETY_VALIDATOR, root)
                        self.assertNotEqual(
                            result.returncode,
                            0,
                            result.stdout + result.stderr,
                        )
                        self.assertIn(
                            "forbidden execution session metadata",
                            result.stderr,
                        )

    def test_public_safety_rejects_t015_blind_private_semantics(self) -> None:
        payloads = (
            {"providerExecutionLocator": "opaque-provider-locator"},
            {"job_trace_cursor": "opaque-job-cursor"},
            {"modelRunLocator": ["opaque-model-run-locator"]},
            {"TRACE\u00a0JOB\u00a0CURSOR": "opaque-nbsp-cursor"},
            {"runtimeJob": {"entries": [{"cursor": "opaque-cursor"}]}},
            {
                "trace": {
                    "batches": [
                        {"provider": {"alias": "opaque-provider-alias"}}
                    ]
                }
            },
            {
                "job": {
                    "records": [
                        {"request": {"locator": "opaque-request-locator"}}
                    ]
                }
            },
            {
                "execution": {
                    "audit": {
                        "trail": {"locator": "opaque-execution-locator"}
                    }
                }
            },
            {
                "provider": {
                    "envelope": {
                        "id": "630eb68f-e0fa-5ecc-887a-7c7a62614681"
                    }
                }
            },
            {
                "runtime": {
                    "wrapper": {
                        "payload": {"cursor": "opaque-runtime-cursor"}
                    }
                }
            },
            {
                "job": {
                    "events": [
                        {
                            "envelope": {
                                "locator": "opaque-job-event-locator"
                            }
                        }
                    ]
                }
            },
            {
                "trace": {
                    "containers": [
                        {"data": {"alias": "opaque-trace-alias"}}
                    ]
                }
            },
            {
                "provider": {
                    "items": [
                        {
                            "record": {
                                "id": (
                                    "c87ee674-4ddc-5d34-bc3f-"
                                    "b3db78e9e3a0"
                                )
                            }
                        }
                    ]
                }
            },
            {
                "execution": {
                    "batches": [
                        {"trail": {"handle": "opaque-execution-handle"}}
                    ]
                }
            },
        )
        for surface in ("plain", "zip"):
            for payload in payloads:
                with self.subTest(surface=surface, payload=payload):
                    with tempfile.TemporaryDirectory(
                        prefix="stock-ci-t015-private-semantics-"
                    ) as raw:
                        root = Path(raw)
                        self._public_fixture(root)
                        encoded = json.dumps(payload)
                        if surface == "plain":
                            (root / "Stock_Skill/execution.json").write_text(
                                encoded + "\n",
                                encoding="utf-8",
                            )
                        else:
                            with ZipFile(
                                root / "Stock_Skill/synthetic.zip",
                                "w",
                                compression=ZIP_DEFLATED,
                            ) as archive:
                                archive.writestr("execution.json", encoded)
                        result = self._run(SAFETY_VALIDATOR, root)
                        self.assertNotEqual(
                            result.returncode,
                            0,
                            result.stdout + result.stderr,
                        )
                        self.assertIn(
                            "forbidden execution session",
                            result.stderr,
                        )

    def test_public_safety_allows_descriptive_public_request_reference(self) -> None:
        payload = {
            "publicResearchRequestReference": (
                "public-transformer-request-20260724"
            )
        }
        for surface in ("plain", "zip"):
            with self.subTest(surface=surface):
                with tempfile.TemporaryDirectory(
                    prefix="stock-ci-public-research-reference-"
                ) as raw:
                    root = Path(raw)
                    self._public_fixture(root)
                    encoded = json.dumps(payload)
                    if surface == "plain":
                        (root / "Stock_Skill/public.json").write_text(
                            encoded + "\n",
                            encoding="utf-8",
                        )
                    else:
                        with ZipFile(
                            root / "Stock_Skill/synthetic.zip",
                            "w",
                            compression=ZIP_DEFLATED,
                        ) as archive:
                            archive.writestr("public.json", encoded)
                    result = self._run(SAFETY_VALIDATOR, root)
                    self.assertEqual(
                        result.returncode,
                        0,
                        result.stdout + result.stderr,
                    )

    def test_public_safety_rejects_private_identifier_under_runtime_key(self) -> None:
        variants = (
            ("execution", "123e4567-e89b-42d3-a456-426614174000"),
            ("execution", "sess_live_synthetic_123"),
            ("executor_id", "sess_live_synthetic_123"),
        )
        for surface in ("plain", "zip"):
            for key, value in variants:
                with self.subTest(surface=surface, key=key, value=value):
                    with tempfile.TemporaryDirectory(
                        prefix="stock-ci-private-runtime-id-"
                    ) as raw:
                        root = Path(raw)
                        self._public_fixture(root)
                        payload = json.dumps({key: value})
                        if surface == "plain":
                            (
                                root / "Stock_Skill/execution.json"
                            ).write_text(payload + "\n", encoding="utf-8")
                        else:
                            with ZipFile(
                                root / "Stock_Skill/synthetic.zip",
                                "w",
                                compression=ZIP_DEFLATED,
                            ) as archive:
                                archive.writestr("execution.json", payload)
                        result = self._run(SAFETY_VALIDATOR, root)
                        self.assertNotEqual(
                            result.returncode,
                            0,
                            result.stdout + result.stderr,
                        )
                        self.assertIn(
                            "forbidden execution session identifier",
                            result.stderr,
                        )

    def test_public_safety_rejects_plaintext_session_identifier(self) -> None:
        with tempfile.TemporaryDirectory(prefix="stock-ci-session-text-") as raw:
            root = Path(raw)
            stock_readme = self._public_fixture(root)
            key = "session" + "_" + "id"
            synthetic_identifier = (
                "123e4567" + "-e89b-42d3-a456-" + "426614174000"
            )
            stock_readme.write_text(
                f"{key}={synthetic_identifier}\n",
                encoding="utf-8",
            )
            result = self._run(SAFETY_VALIDATOR, root)
            self.assertNotEqual(result.returncode, 0)
            self.assertIn(
                "forbidden plaintext execution session identifier",
                result.stderr,
            )

    def test_public_safety_allows_declared_boolean_execution_controls(self) -> None:
        with tempfile.TemporaryDirectory(prefix="stock-ci-safe-controls-") as raw:
            root = Path(raw)
            self._public_fixture(root)
            control = root / "Stock_Skill/control.json"
            control.write_text(
                json.dumps(
                    {
                        "fresh_ephemeral_session": True,
                        "conversation_history_forwarded": False,
                        "request_id": "public-request-001",
                        "execution_controls": {"network_allowed": False},
                        "execution_provenance": {"executor": "synthetic-host"},
                        "executor_id": "forward-executor-t002",
                        "execution_receipt_sha256": "a" * 64,
                    }
                )
                + "\n",
                encoding="utf-8",
            )
            result = self._run(SAFETY_VALIDATOR, root)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_public_safety_rejects_nonboolean_safe_control_shape(self) -> None:
        with tempfile.TemporaryDirectory(prefix="stock-ci-control-shape-") as raw:
            root = Path(raw)
            self._public_fixture(root)
            control = root / "Stock_Skill/control.json"
            control.write_text(
                json.dumps({"fresh_ephemeral_session": {"id": "private"}})
                + "\n",
                encoding="utf-8",
            )
            result = self._run(SAFETY_VALIDATOR, root)
            self.assertNotEqual(result.returncode, 0)
            self.assertIn(
                "malformed public execution control",
                result.stderr,
            )

    def test_public_safety_rejects_windows_style_zip_paths(self) -> None:
        with tempfile.TemporaryDirectory(prefix="stock-ci-zip-path-") as raw:
            root = Path(raw)
            self._public_fixture(root)
            archive_path = root / "Stock_Skill/synthetic.zip"
            for name in (
                "..\\escape.txt",
                "C:\\escape.txt",
                "C:/escape.txt",
                "\\\\server\\share\\escape.txt",
                "folder\\file.txt",
            ):
                with self.subTest(name=name):
                    with ZipFile(
                        archive_path, "w", compression=ZIP_DEFLATED
                    ) as archive:
                        archive.writestr(name, "benign")
                    result = self._run(SAFETY_VALIDATOR, root)
                    self.assertNotEqual(result.returncode, 0)
                    self.assertIn("unsafe ZIP path", result.stderr)

    def test_public_safety_rejects_nonempty_zip_directory_payload(self) -> None:
        with tempfile.TemporaryDirectory(prefix="stock-ci-zip-dir-payload-") as raw:
            root = Path(raw)
            self._public_fixture(root)
            archive_path = root / "Stock_Skill/synthetic.zip"
            directory = ZipInfo("concealed/")
            directory.compress_type = ZIP_DEFLATED
            with ZipFile(archive_path, "w") as archive:
                archive.writestr(directory, SYNTHETIC_FINE_GRAINED_PAT)
            result = self._run(SAFETY_VALIDATOR, root)
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("non-empty directory ZIP entry", result.stderr)

    def test_public_safety_allows_empty_zip_directory(self) -> None:
        with tempfile.TemporaryDirectory(prefix="stock-ci-zip-empty-dir-") as raw:
            root = Path(raw)
            self._public_fixture(root)
            archive_path = root / "Stock_Skill/synthetic.zip"
            with ZipFile(archive_path, "w", compression=ZIP_DEFLATED) as archive:
                archive.writestr("empty/", b"")
                archive.writestr("empty/payload.txt", "benign")
            result = self._run(SAFETY_VALIDATOR, root)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertIn("1 ZIP entries", result.stdout)

    def test_public_safety_rejects_stateless_app_token_in_plain_file(self) -> None:
        with tempfile.TemporaryDirectory(prefix="stock-ci-ghs-plain-") as raw:
            root = Path(raw)
            stock_readme = self._public_fixture(root)
            stock_readme.write_text(
                f"synthetic credential: {SYNTHETIC_STATELESS_APP_TOKEN}\n",
                encoding="utf-8",
            )
            result = self._run(SAFETY_VALIDATOR, root)
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("forbidden GitHub stateless App token", result.stderr)

    def test_public_safety_rejects_stateless_app_token_in_zip_payload(self) -> None:
        with tempfile.TemporaryDirectory(prefix="stock-ci-ghs-zip-") as raw:
            root = Path(raw)
            self._public_fixture(root)
            archive_path = root / "Stock_Skill/synthetic.zip"
            with ZipFile(archive_path, "w", compression=ZIP_DEFLATED) as archive:
                archive.writestr("payload.txt", SYNTHETIC_STATELESS_APP_TOKEN)
            result = self._run(SAFETY_VALIDATOR, root)
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("forbidden GitHub stateless App token", result.stderr)

    def test_public_safety_rejects_bare_and_child_user_home_paths(self) -> None:
        with tempfile.TemporaryDirectory(prefix="stock-ci-bare-home-") as raw:
            root = Path(raw)
            stock_readme = self._public_fixture(root)
            mac_root = "/" + "Users/"
            mac_case_root = "/" + "users/"
            linux_root = "/" + "home/"
            windows_root = "C:" + "\\" + "Users\\"
            windows_case_root = "c:" + "\\" + "users\\"
            windows_forward_case_root = "c:" + "/" + "users/"
            ascii_user = "exampleuser"
            unicode_user = "测试用户"
            cases = (
                ("macOS user path", mac_root + ascii_user),
                ("macOS user path", mac_root + ascii_user + "/project"),
                ("macOS user path", mac_case_root + ascii_user),
                ("macOS user path", mac_root + unicode_user),
                ("Linux user path", linux_root + ascii_user),
                ("Linux user path", linux_root + ascii_user + "/project"),
                ("Linux user path", linux_root + unicode_user),
                ("Windows user path", windows_root + ascii_user),
                ("Windows user path", windows_root + ascii_user + "\\project"),
                ("Windows user path", windows_case_root + ascii_user),
                ("Windows user path", windows_forward_case_root + ascii_user),
                ("Windows user path", windows_root + unicode_user),
            )
            for pattern_name, value in cases:
                with self.subTest(pattern_name=pattern_name):
                    stock_readme.write_text(value + "\n", encoding="utf-8")
                    result = self._run(SAFETY_VALIDATOR, root)
                    self.assertNotEqual(result.returncode, 0)
                    self.assertIn(f"forbidden {pattern_name}", result.stderr)

    def test_public_safety_rejects_case_and_unicode_user_homes_in_zip(self) -> None:
        with tempfile.TemporaryDirectory(prefix="stock-ci-home-zip-") as raw:
            root = Path(raw)
            self._public_fixture(root)
            archive_path = root / "Stock_Skill/synthetic.zip"
            values = (
                "/" + "users/" + "exampleuser",
                "c:" + "\\" + "users\\" + "exampleuser",
                "c:" + "/" + "users/" + "exampleuser",
                "/" + "Users/" + "测试用户",
                "/" + "home/" + "测试用户",
                "C:" + "\\" + "Users\\" + "测试用户",
            )
            for value in values:
                with self.subTest(value=value):
                    with ZipFile(
                        archive_path, "w", compression=ZIP_DEFLATED
                    ) as archive:
                        archive.writestr("payload.txt", value)
                    result = self._run(SAFETY_VALIDATOR, root)
                    self.assertNotEqual(result.returncode, 0)
                    self.assertIn("forbidden", result.stderr)

    def test_public_safety_allows_ellipsis_path_placeholder(self) -> None:
        with tempfile.TemporaryDirectory(prefix="stock-ci-path-placeholder-") as raw:
            root = Path(raw)
            stock_readme = self._public_fixture(root)
            placeholders = (
                "/" + "Users/" + "...",
                "/" + "users/" + "…",
                "/" + "home/" + "...",
                "C:" + "\\" + "Users\\" + "...",
            )
            for placeholder in placeholders:
                with self.subTest(placeholder=placeholder):
                    stock_readme.write_text(
                        f"portable documentation placeholder: `{placeholder}`\n",
                        encoding="utf-8",
                    )
                    result = self._run(SAFETY_VALIDATOR, root)
                    self.assertEqual(
                        result.returncode, 0, result.stdout + result.stderr
                    )

    def test_public_safety_allows_public_url_with_home_path_segment(self) -> None:
        with tempfile.TemporaryDirectory(prefix="stock-ci-public-home-url-") as raw:
            root = Path(raw)
            stock_readme = self._public_fixture(root)
            stock_readme.write_text(
                "source: https://example.com/global/en/home/press-releases/item.html\n",
                encoding="utf-8",
            )
            result = self._run(SAFETY_VALIDATOR, root)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_historical_path_allowlist_is_exact_and_backticked(self) -> None:
        with tempfile.TemporaryDirectory(prefix="stock-ci-historical-path-") as raw:
            root = Path(raw)
            stock_readme = self._public_fixture(root)
            exact_path = "/home/" + "oai/" + "skills"
            safe_boundaries = ("\n", ".\n", "；继续说明\n", ")\n")
            for boundary in safe_boundaries:
                with self.subTest(boundary=boundary):
                    stock_readme.write_text(
                        f"historical: `{exact_path}`{boundary}", encoding="utf-8"
                    )
                    passing = self._run(SAFETY_VALIDATOR, root)
                    self.assertEqual(
                        passing.returncode, 0, passing.stdout + passing.stderr
                    )
            stock_readme.write_text(
                f"unbackticked historical path: {exact_path}\n", encoding="utf-8"
            )
            unbackticked = self._run(SAFETY_VALIDATOR, root)
            self.assertNotEqual(unbackticked.returncode, 0)
            self.assertIn("forbidden Linux user path", unbackticked.stderr)
            stock_readme.write_text(
                f"historical file URI: `file://{exact_path}`\n", encoding="utf-8"
            )
            file_uri = self._run(SAFETY_VALIDATOR, root)
            self.assertNotEqual(file_uri.returncode, 0)
            self.assertIn("forbidden Linux user path", file_uri.stderr)
            stock_readme.write_text(
                f"historical child: `{exact_path}/private`\n", encoding="utf-8"
            )
            failing = self._run(SAFETY_VALIDATOR, root)
            self.assertNotEqual(failing.returncode, 0)
            self.assertIn("forbidden Linux user path", failing.stderr)

    def test_historical_path_allowlist_rejects_post_backtick_continuation(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory(prefix="stock-ci-historical-boundary-") as raw:
            root = Path(raw)
            stock_readme = self._public_fixture(root)
            archive_path = root / "Stock_Skill/synthetic.zip"
            exact_path = "/home/" + "oai/" + "skills"
            continuations = (
                "/private",
                "\\private",
                "suffix",
                "_suffix",
                "-suffix",
                "9",
                "测试",
                "@suffix",
            )
            for continuation in continuations:
                payload = f"`{exact_path}`{continuation}"
                with self.subTest(surface="plain", continuation=continuation):
                    if archive_path.exists():
                        archive_path.unlink()
                    stock_readme.write_text(payload + "\n", encoding="utf-8")
                    plain = self._run(SAFETY_VALIDATOR, root)
                    self.assertNotEqual(plain.returncode, 0)
                    self.assertIn(
                        "Stock_Skill/README.md: forbidden Linux user path",
                        plain.stderr,
                    )
                with self.subTest(surface="zip", continuation=continuation):
                    stock_readme.write_text("public stock skills\n", encoding="utf-8")
                    with ZipFile(
                        archive_path, "w", compression=ZIP_DEFLATED
                    ) as archive:
                        archive.writestr("payload.txt", payload)
                    zipped = self._run(SAFETY_VALIDATOR, root)
                    self.assertNotEqual(zipped.returncode, 0)
                    self.assertIn(
                        "synthetic.zip!payload.txt: forbidden Linux user path",
                        zipped.stderr,
                    )


if __name__ == "__main__":
    unittest.main()
