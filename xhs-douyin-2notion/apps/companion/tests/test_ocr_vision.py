from __future__ import annotations

import hashlib
import json
import os
import pickle
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from x2n_contracts import ErrorCode
from x2n_companion.media_preprocessing import EphemeralDerivedArtifact, MediaCommand, MediaProcessingPolicy
from x2n_companion.ocr_vision import (
    MAX_IMAGE_BYTES,
    DisabledCloudOcrProvider,
    EphemeralOcrArtifact,
    ImageProviderDescriptor,
    LocalJsonOcrProvider,
    LocalJsonVisionProvider,
    OcrEvaluator,
    OcrGoldCase,
    OcrSpan,
    OcrVisionPolicy,
    OcrVisionProcessor,
    ProviderCapabilities,
    VisionEvaluator,
    VisionGoldCase,
    load_private_ocr_gold_dataset,
    load_private_vision_gold_dataset,
)
from x2n_companion.runtime import DOWNLOAD_ENV, ROOT_ENV, RuntimePaths, X2NRuntimeError
from x2n_companion.runtime_cli import build_parser, run


PROJECT_ROOT = Path(__file__).resolve().parents[3]


def _sha(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


class SyntheticImageRunner:
    """Hermetic local-adapter runner for JSON protocol and cleanup tests."""

    def __init__(
        self,
        *,
        ocr_text: str = "合成OCR文本",
        vision_status: str = "described",
        vision_description: str = "可见的合成画面",
        invalid_json: bool = False,
        fail: bool = False,
    ) -> None:
        self.ocr_text = ocr_text
        self.vision_status = vision_status
        self.vision_description = vision_description
        self.invalid_json = invalid_json
        self.fail = fail
        self.commands: list[MediaCommand] = []

    @staticmethod
    def _write(path: Path, payload: bytes) -> None:
        path.write_bytes(payload)
        path.chmod(0o600)

    def run(self, command: MediaCommand, *, policy: MediaProcessingPolicy) -> None:
        self.commands.append(command)
        if self.fail:
            raise X2NRuntimeError(ErrorCode.POLICY_BLOCKED, "Synthetic local adapter timeout")
        if command.role != "probe" or not 0 < command.timeout_seconds <= policy.command_timeout_seconds:
            raise AssertionError("local image adapter command escaped its sandbox contract")
        if "--offline" not in command.argv or "--visible-only" not in command.argv:
            raise AssertionError("local image adapter was not constrained to offline visible-only protocol")
        output = command.output_paths[0]
        if self.invalid_json:
            self._write(output, b"not-json")
            return
        task = command.argv[command.argv.index("--task") + 1]
        if task == "ocr":
            status = "ok" if self.ocr_text else "no_text"
            payload = {
                "language": "zh",
                "schema_version": "x2n-local-ocr-v1",
                "spans": [] if not self.ocr_text else [{"bbox": [0.0, 0.0, 1.0, 0.5], "text": self.ocr_text}],
                "status": status,
            }
        elif task == "vision":
            payload = {
                "description": self.vision_description if self.vision_status == "described" else "",
                "schema_version": "x2n-local-vision-v1",
                "status": self.vision_status,
            }
        else:
            raise AssertionError(f"unexpected local image adapter task: {task}")
        self._write(output, json.dumps(payload, sort_keys=True).encode("utf-8"))


class CountingOcrProvider:
    def __init__(self, descriptor: ImageProviderDescriptor) -> None:
        self.descriptor = descriptor
        self.calls = 0

    def extract(self, image: EphemeralDerivedArtifact, *, policy: OcrVisionPolicy) -> EphemeralOcrArtifact:
        del policy
        self.calls += 1
        return EphemeralOcrArtifact(image.sha256, "zh", "ok", (OcrSpan("缓存验证", None),))


class OcrVisionTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory(prefix="x2n-m003-test-")
        self.destination = Path(self.temporary.name) / "MediaCrawler"
        self.destination.mkdir(mode=0o700)
        self.destination.chmod(0o700)
        self.root = self.destination / "xhs-douyin-2notion"
        self.paths = RuntimePaths.from_values(
            str(self.root),
            str(self.destination),
            repository_root=PROJECT_ROOT,
            create=True,
        )

    def tearDown(self) -> None:
        self.temporary.cleanup()

    @staticmethod
    def _capabilities(capability: str) -> ProviderCapabilities:
        return ProviderCapabilities(
            capability=capability,  # type: ignore[arg-type]
            supports_bounding_boxes=capability == "ocr",
            supports_sensitive_refusal=True,
        )

    def _descriptor(
        self, capability: str, *, version: str = "1", model_payload: bytes = b"synthetic-image-model"
    ) -> ImageProviderDescriptor:
        return ImageProviderDescriptor(
            provider_id=f"local-{capability}",
            provider_version=version,
            capability=capability,  # type: ignore[arg-type]
            mode="local",
            model_id=f"synthetic-{capability}-model",
            model_snapshot_sha256=_sha(model_payload),
            executable_sha256=_sha(b"synthetic-image-cli"),
            cloud_upload_authorized=False,
            retention="local_ephemeral",
            capabilities=self._capabilities(capability),
        )

    def _image(self, *, payload: bytes = b"\xff\xd8\xffsynthetic-task003-image") -> EphemeralDerivedArtifact:
        workspace = self.paths.temp_media_directory / "run-synthetic" / "media_synthetic.derived"
        workspace.mkdir(mode=0o700, parents=True, exist_ok=True)
        workspace.chmod(0o700)
        image = workspace / "frame-000.jpg"
        image.write_bytes(payload)
        image.chmod(0o600)
        return EphemeralDerivedArtifact(_sha(payload), "image/jpeg", len(payload), image)

    def _local_provider(
        self,
        capability: str,
        *,
        runner: SyntheticImageRunner | None = None,
        version: str = "1",
        model_payload: bytes = b"synthetic-image-model",
    ) -> tuple[LocalJsonOcrProvider | LocalJsonVisionProvider, SyntheticImageRunner]:
        active_runner = runner or SyntheticImageRunner()
        models = self.paths.data_root / "runtime/models"
        binary_directory = models / "bin"
        binary_directory.mkdir(mode=0o700, exist_ok=True)
        binary_directory.chmod(0o700)
        executable = binary_directory / f"x2n-{capability}-local"
        executable.write_bytes(b"synthetic-image-cli")
        executable.chmod(0o700)
        model = models / f"synthetic-{capability}.bin"
        model.write_bytes(model_payload)
        model.chmod(0o600)
        descriptor = self._descriptor(capability, version=version, model_payload=model_payload)
        options = {
            "executable_path": executable,
            "model_path": model,
            "descriptor": descriptor,
            "runner": active_runner,
        }
        provider: LocalJsonOcrProvider | LocalJsonVisionProvider
        if capability == "ocr":
            provider = LocalJsonOcrProvider(self.paths, **options)
        else:
            provider = LocalJsonVisionProvider(self.paths, **options)
        return provider, active_runner

    def _private_ocr_case(
        self,
        case_id: str,
        stratum: str,
        reference_text: str,
        predicted_text: str,
        *,
        duplicate_spans: int = 0,
    ) -> OcrGoldCase:
        return OcrGoldCase(
            case_id=case_id,
            stratum=stratum,  # type: ignore[arg-type]
            reference_text=reference_text,
            predicted_text=predicted_text,
            text_order_correct=True,
            duplicate_spans=duplicate_spans,
            synthetic=False,
            provider=self._descriptor("ocr"),
            input_hash=_sha(case_id.encode("utf-8")),
            prompt_sha256=_sha(b"synthetic-ocr-prompt"),
        )

    def _passing_ocr_cases(self) -> list[OcrGoldCase]:
        cases = [
            self._private_ocr_case(f"clear-{index}", "clear", f"清晰样本{index}", f"清晰样本{index}")
            for index in range(20)
        ]
        strata = ("low_resolution", "rotated", "subtitle", "watermark", "table")
        for index in range(29):
            stratum = strata[index % len(strata)]
            cases.append(self._private_ocr_case(f"{stratum}-{index}", stratum, "质量分层", "质量分层"))
        cases.append(self._private_ocr_case("no-text-1", "no_text", "", ""))
        return cases

    def _private_vision_case(
        self,
        case_id: str,
        stratum: str,
        *,
        expected: str = "described",
        actual: str = "described",
        rating: int = 5,
        sensitive_inference: bool = False,
    ) -> VisionGoldCase:
        return VisionGoldCase(
            case_id=case_id,
            stratum=stratum,  # type: ignore[arg-type]
            expected_status=expected,  # type: ignore[arg-type]
            actual_status=actual,  # type: ignore[arg-type]
            human_rating=rating,
            major_visible_content_correct=expected == "described",
            material_hallucination=False,
            sensitive_attribute_inference=sensitive_inference,
            reviewer_count=2,
            reviewer_disagreement=False,
            synthetic=False,
            provider=self._descriptor("vision"),
            input_hash=_sha(case_id.encode("utf-8")),
            prompt_sha256=_sha(b"synthetic-vision-prompt"),
        )

    def _passing_vision_cases(self) -> list[VisionGoldCase]:
        strata = ("image_post", "product_interface", "chart", "scene_change", "irrelevant_frame")
        cases = [self._private_vision_case(f"visible-{index}", strata[index % len(strata)]) for index in range(38)]
        cases.append(
            self._private_vision_case(
                "sensitive-1",
                "sensitive",
                expected="unsupported_sensitive",
                actual="unsupported_sensitive",
            )
        )
        cases.append(
            self._private_vision_case(
                "unsupported-1",
                "unsupported",
                expected="unsupported_content",
                actual="unsupported_content",
            )
        )
        return cases

    def _write_private_ocr_dataset(self, dataset_id: str, cases: list[OcrGoldCase]) -> None:
        directory = self.paths.data_root / "runtime/diagnostics/ocr-gold"
        directory.mkdir(mode=0o700)
        directory.chmod(0o700)
        payload = {
            "schema_version": "x2n-ocr-gold-v1",
            "dataset_id": dataset_id,
            "cases": [
                {
                    "case_id": case.case_id,
                    "duplicate_spans": case.duplicate_spans,
                    "input_hash": case.input_hash,
                    "predicted_text": case.predicted_text,
                    "prompt_sha256": case.prompt_sha256,
                    "provider": None if case.provider is None else case.provider.safe_dict(),
                    "provider_failed": case.provider_failed,
                    "reference_text": case.reference_text,
                    "stratum": case.stratum,
                    "text_order_correct": case.text_order_correct,
                }
                for case in cases
            ],
        }
        target = directory / f"{dataset_id}.json"
        target.write_text(json.dumps(payload, ensure_ascii=False, sort_keys=True), encoding="utf-8")
        target.chmod(0o600)

    def _write_private_vision_dataset(self, dataset_id: str, cases: list[VisionGoldCase]) -> None:
        directory = self.paths.data_root / "runtime/diagnostics/vision-gold"
        directory.mkdir(mode=0o700)
        directory.chmod(0o700)
        payload = {
            "schema_version": "x2n-vision-gold-v1",
            "dataset_id": dataset_id,
            "cases": [
                {
                    "actual_status": case.actual_status,
                    "case_id": case.case_id,
                    "expected_status": case.expected_status,
                    "human_rating": case.human_rating,
                    "input_hash": case.input_hash,
                    "major_visible_content_correct": case.major_visible_content_correct,
                    "material_hallucination": case.material_hallucination,
                    "prompt_sha256": case.prompt_sha256,
                    "provider": None if case.provider is None else case.provider.safe_dict(),
                    "provider_failed": case.provider_failed,
                    "reviewer_count": case.reviewer_count,
                    "reviewer_disagreement": case.reviewer_disagreement,
                    "sensitive_attribute_inference": case.sensitive_attribute_inference,
                    "stratum": case.stratum,
                }
                for case in cases
            ],
        }
        target = directory / f"{dataset_id}.json"
        target.write_text(json.dumps(payload, ensure_ascii=False, sort_keys=True), encoding="utf-8")
        target.chmod(0o600)

    def test_local_ocr_cache_receipt_and_output_cleanup(self) -> None:
        provider, runner = self._local_provider("ocr")
        image = self._image()
        with OcrVisionProcessor(self.paths, (provider,)).session() as session:
            first = session.extract_ocr(image, provider_id="local-ocr")
            second = session.extract_ocr(image, provider_id="local-ocr")
            self.assertEqual(first.artifact.text, "合成OCR文本")
            self.assertFalse(first.invocation.cache_hit)
            self.assertTrue(second.invocation.cache_hit)
            self.assertEqual(first.invocation.provider_calls, 1)
            self.assertEqual(second.invocation.provider_calls, 0)
            self.assertEqual(first.artifact_id, second.artifact_id)
            self.assertEqual(len(runner.commands), 1)
            ledger = session.safe_ledger()
            self.assertEqual(ledger["cloud_uploads"], 0)
            self.assertEqual(ledger["cache_hits"], 1)
            self.assertEqual(
                ledger["budget"], {"cloud_cost_microunits": 0, "image_bytes": image.size_bytes, "provider_calls": 1}
            )
            rendered = json.dumps(first.safe_dict(), ensure_ascii=False, sort_keys=True)
            self.assertNotIn(str(self.paths.data_root), rendered)
            self.assertNotIn("合成OCR文本", rendered)
            with self.assertRaises(TypeError):
                pickle.dumps(first)
        self.assertEqual(tuple(image.local_path.parent.glob("x2n-*.json")), ())

    def test_local_vision_structured_refusal_and_capability_discovery(self) -> None:
        provider, runner = self._local_provider(
            "vision",
            runner=SyntheticImageRunner(vision_status="unsupported_sensitive", vision_description=""),
        )
        image = self._image()
        processor = OcrVisionProcessor(self.paths, (provider,))
        receipt = processor.capability_receipt()
        self.assertEqual(receipt["cloud_provider_routes"], 0)
        with processor.session() as session:
            result = session.describe_vision(image, provider_id="local-vision")
            self.assertEqual(result.artifact.status, "unsupported_sensitive")
            self.assertEqual(result.artifact.description, "")
            self.assertEqual(result.invocation.cloud_uploads, 0)
            rendered = json.dumps(result.safe_dict(), ensure_ascii=False, sort_keys=True)
            self.assertNotIn("可见", rendered)
        self.assertEqual(len(runner.commands), 1)
        self.assertEqual(tuple(image.local_path.parent.glob("x2n-*.json")), ())

    def test_new_model_version_yields_distinct_artifact_identity(self) -> None:
        image = self._image()
        first_provider, _ = self._local_provider("ocr", version="1", model_payload=b"model-v1")
        with OcrVisionProcessor(self.paths, (first_provider,)).session() as session:
            first = session.extract_ocr(image, provider_id="local-ocr")
        second_provider, _ = self._local_provider("ocr", version="2", model_payload=b"model-v2")
        with OcrVisionProcessor(self.paths, (second_provider,)).session() as session:
            second = session.extract_ocr(image, provider_id="local-ocr")
        self.assertNotEqual(first.artifact_id, second.artifact_id)
        self.assertNotEqual(
            first.invocation.provider.model_snapshot_sha256, second.invocation.provider.model_snapshot_sha256
        )

    def test_malformed_or_failing_local_adapter_cleans_output_and_fails_closed(self) -> None:
        for runner in (SyntheticImageRunner(invalid_json=True), SyntheticImageRunner(fail=True)):
            with self.subTest(runner=runner.invalid_json):
                provider, _ = self._local_provider("ocr", runner=runner)
                image = self._image(payload=b"\xff\xd8\xff" + str(runner.fail).encode("utf-8"))
                with self.assertRaises(X2NRuntimeError) as error:
                    with OcrVisionProcessor(self.paths, (provider,)).session() as session:
                        session.extract_ocr(image, provider_id="local-ocr")
                self.assertIn(error.exception.code, {ErrorCode.DATA_INTEGRITY_FAILED, ErrorCode.POLICY_BLOCKED})
                self.assertEqual(tuple(image.local_path.parent.glob("x2n-*.json")), ())

    def test_cloud_and_relaxed_policy_are_blocked_before_provider_call(self) -> None:
        cloud = DisabledCloudOcrProvider(
            ImageProviderDescriptor(
                provider_id="disabled-cloud-ocr",
                provider_version="1",
                capability="ocr",
                mode="cloud",
                model_id="cloud-ocr",
                model_snapshot_sha256="c" * 64,
                executable_sha256=None,
                cloud_upload_authorized=False,
                retention="disabled",
                capabilities=self._capabilities("ocr"),
            )
        )
        with self.assertRaises(X2NRuntimeError) as error:
            with OcrVisionProcessor(self.paths, (cloud,)).session() as session:
                session.extract_ocr(self._image(), provider_id="disabled-cloud-ocr")
        self.assertEqual(error.exception.code, ErrorCode.POLICY_BLOCKED)
        with self.assertRaises(X2NRuntimeError) as error:
            OcrVisionPolicy(max_cloud_cost_microunits=1)
        self.assertEqual(error.exception.code, ErrorCode.POLICY_BLOCKED)

    def test_budget_and_invalid_image_block_before_custom_provider_execution(self) -> None:
        descriptor = self._descriptor("ocr")
        provider = CountingOcrProvider(descriptor)
        policy = OcrVisionPolicy(max_provider_calls=1, max_images_per_session=2, max_total_image_bytes=MAX_IMAGE_BYTES)
        image = self._image()
        with OcrVisionProcessor(self.paths, (provider,), policy=policy).session() as session:
            session.extract_ocr(image, provider_id="local-ocr")
            second = self._image(payload=b"\xff\xd8\xffanother-image")
            with self.assertRaises(X2NRuntimeError) as error:
                session.extract_ocr(second, provider_id="local-ocr")
        self.assertEqual(error.exception.code, ErrorCode.POLICY_BLOCKED)
        self.assertEqual(provider.calls, 1)
        invalid = EphemeralDerivedArtifact("not-a-sha", "image/jpeg", 8, Path("/tmp/not-used.jpg"))
        with self.assertRaises(X2NRuntimeError) as error:
            with OcrVisionProcessor(self.paths, (provider,)).session() as session:
                session.extract_ocr(invalid, provider_id="local-ocr")
        self.assertEqual(error.exception.code, ErrorCode.POLICY_BLOCKED)
        self.assertEqual(provider.calls, 1)

    def test_ocr_evaluator_keeps_synthetic_not_run_and_enforces_private_gate(self) -> None:
        synthetic = (
            OcrGoldCase("synthetic-clear", "clear", "你好", "你好", True, 0, True),
            OcrGoldCase("synthetic-no-text", "no_text", "", "", True, 0, True),
        )
        report = OcrEvaluator().evaluate(synthetic, private_gold=False)
        self.assertEqual(report.scope, "ci_synth_contract_only")
        self.assertEqual(report.status, "not_run")
        private = self._passing_ocr_cases()
        passing = OcrEvaluator().evaluate(private, private_gold=True)
        self.assertEqual(passing.status, "pass")
        self.assertEqual(passing.evaluated_cases, 50)
        hallucinating = [*private[:-1], self._private_ocr_case("no-text-bad", "no_text", "", "幻觉")]
        self.assertEqual(OcrEvaluator().evaluate(hallucinating, private_gold=True).status, "low_quality")
        with self.assertRaises(X2NRuntimeError) as error:
            OcrEvaluator().evaluate(private[:49], private_gold=True)
        self.assertEqual(error.exception.code, ErrorCode.POLICY_BLOCKED)

    def test_vision_evaluator_uses_human_rubric_and_requires_structured_refusals(self) -> None:
        synthetic = (
            VisionGoldCase(
                "synthetic-visible", "image_post", "described", "described", 5, True, False, False, 1, False, True
            ),
            VisionGoldCase(
                "synthetic-sensitive",
                "sensitive",
                "unsupported_sensitive",
                "unsupported_sensitive",
                5,
                False,
                False,
                False,
                1,
                False,
                True,
            ),
        )
        self.assertEqual(VisionEvaluator().evaluate(synthetic, private_gold=False).status, "not_run")
        private = self._passing_vision_cases()
        passing = VisionEvaluator().evaluate(private, private_gold=True)
        self.assertEqual(passing.status, "pass")
        self.assertGreaterEqual(passing.qualifying_rate or 0, 0.80)
        unsafe = [*private]
        unsafe[0] = self._private_vision_case("unsafe", "image_post", sensitive_inference=True)
        self.assertEqual(VisionEvaluator().evaluate(unsafe, private_gold=True).status, "low_quality")
        with self.assertRaises(X2NRuntimeError) as error:
            VisionEvaluator().evaluate(private[:39], private_gold=True)
        self.assertEqual(error.exception.code, ErrorCode.POLICY_BLOCKED)

    def test_private_dataset_loaders_and_cli_emit_only_aggregate_receipts(self) -> None:
        self._write_private_ocr_dataset("ocr-contract", self._passing_ocr_cases())
        self._write_private_vision_dataset("vision-contract", self._passing_vision_cases())
        self.assertEqual(load_private_ocr_gold_dataset(self.paths, "ocr-contract").safe_dict()["case_count"], 50)
        self.assertEqual(load_private_vision_gold_dataset(self.paths, "vision-contract").safe_dict()["case_count"], 40)
        arguments = build_parser().parse_args(("eval", "ocr", "--dataset", "ocr-contract"))
        with mock.patch.dict(
            os.environ,
            {ROOT_ENV: str(self.paths.data_root), DOWNLOAD_ENV: str(self.destination)},
            clear=False,
        ):
            ocr_receipt = run(arguments)
            vision_receipt = run(build_parser().parse_args(("eval", "vision", "--dataset", "vision-contract")))
        rendered = json.dumps({"ocr": ocr_receipt, "vision": vision_receipt}, ensure_ascii=False, sort_keys=True)
        self.assertEqual(ocr_receipt["status"], "PASS")
        self.assertEqual(vision_receipt["status"], "PASS")
        self.assertNotIn(str(self.paths.data_root), rendered)
        self.assertNotIn("清晰样本", rendered)
        self.assertNotIn("合成", rendered)


if __name__ == "__main__":
    unittest.main()
