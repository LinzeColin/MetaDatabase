from __future__ import annotations

import hashlib
import json
import os
import pickle
import shutil
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path
from unittest import mock

from x2n_contracts import ErrorCode
from x2n_companion.asr import (
    MAX_CER_CHARS,
    AsrAudioNormalizer,
    AsrEvaluator,
    AsrGoldCase,
    AsrPolicy,
    AsrProcessor,
    AsrProviderDescriptor,
    AsrSegment,
    DisabledCloudAsrProvider,
    EphemeralTranscript,
    WhisperCppLocalProvider,
    character_error_rate,
    load_private_asr_gold_dataset,
    word_error_rate,
)
from x2n_companion.media_preprocessing import (
    EphemeralDerivedArtifact,
    MediaCommand,
    MediaProcessingPolicy,
    MediaToolchain,
)
from x2n_companion.runtime import DOWNLOAD_ENV, ROOT_ENV, RuntimePaths, X2NRuntimeError
from x2n_companion.runtime_cli import build_parser, run


PROJECT_ROOT = Path(__file__).resolve().parents[3]


def _sha(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


class SyntheticAsrRunner:
    """A hermetic runner for command shape and temporary-output contracts."""

    def __init__(self, *, text: str = "合成转录", invalid_json: bool = False, fail_role: str | None = None) -> None:
        self.text = text
        self.invalid_json = invalid_json
        self.fail_role = fail_role
        self.commands: list[MediaCommand] = []

    @staticmethod
    def _write(path: Path, payload: bytes) -> None:
        path.write_bytes(payload)
        path.chmod(0o600)

    def run(self, command: MediaCommand, *, policy: MediaProcessingPolicy) -> None:
        self.commands.append(command)
        if command.role == self.fail_role:
            raise X2NRuntimeError(ErrorCode.POLICY_BLOCKED, "Synthetic ASR command timeout")
        if not 0 < command.timeout_seconds <= policy.command_timeout_seconds:
            raise AssertionError("ASR command timeout escaped its sandbox policy")
        if command.role == "audio":
            self._write(command.output_paths[0], b"RIFF" + b"synthetic-wav" * 16)
            return
        if command.role == "probe":
            if self.invalid_json:
                self._write(command.output_paths[0], b"not-json")
                return
            rows: list[dict[str, object]] = []
            if self.text:
                rows.append({"offsets": {"from": 0, "to": 100}, "text": self.text})
            payload = {"result": {"transcription": rows}}
            self._write(command.output_paths[0], json.dumps(payload, sort_keys=True).encode("utf-8"))
            return
        raise AssertionError(f"unexpected synthetic ASR role: {command.role}")


class CountingProvider:
    def __init__(self, descriptor: AsrProviderDescriptor, *, text: str = "缓存验证") -> None:
        self.descriptor = descriptor
        self.text = text
        self.calls = 0

    def transcribe(
        self,
        audio: EphemeralDerivedArtifact,
        *,
        audio_seconds: float,
        language: str,
        policy: AsrPolicy,
    ) -> EphemeralTranscript:
        del audio_seconds, policy
        self.calls += 1
        return EphemeralTranscript((AsrSegment(0, 100, self.text),), language=language, input_hash=audio.sha256)


class AsrTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory(prefix="x2n-m002-test-")
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

    def _audio(self, *, payload: bytes = b"synthetic-task002-audio") -> EphemeralDerivedArtifact:
        workspace = self.paths.temp_media_directory / "synthetic-asr"
        workspace.mkdir(mode=0o700, exist_ok=True)
        workspace.chmod(0o700)
        source = workspace / "audio.m4a"
        source.write_bytes(payload)
        source.chmod(0o600)
        return EphemeralDerivedArtifact(_sha(payload), "audio/mp4", len(payload), source)

    def _local_provider(
        self,
        *,
        runner: SyntheticAsrRunner | None = None,
        version: str = "1",
        model_payload: bytes = b"synthetic-local-model-v1",
    ) -> tuple[WhisperCppLocalProvider, SyntheticAsrRunner]:
        active_runner = runner or SyntheticAsrRunner()
        models = self.paths.data_root / "runtime/models"
        binary_directory = models / "bin"
        binary_directory.mkdir(mode=0o700, exist_ok=True)
        binary_directory.chmod(0o700)
        executable = binary_directory / "whisper-cli"
        executable.write_bytes(b"synthetic-whisper-cli")
        executable.chmod(0o700)
        model = models / "ggml-synthetic.bin"
        model.write_bytes(model_payload)
        model.chmod(0o600)
        descriptor = AsrProviderDescriptor(
            provider_id="local-whispercpp",
            provider_version=version,
            mode="local",
            model_id="ggml-synthetic",
            model_snapshot_sha256=_sha(model_payload),
            executable_sha256=_sha(b"synthetic-whisper-cli"),
            cloud_upload_authorized=False,
            retention="local_ephemeral",
        )
        toolchain = MediaToolchain(Path(sys.executable), Path(sys.executable), active_runner)
        return (
            WhisperCppLocalProvider(
                self.paths,
                toolchain,
                executable_path=executable,
                model_path=model,
                descriptor=descriptor,
            ),
            active_runner,
        )

    @staticmethod
    def _counting_descriptor(*, version: str = "1") -> AsrProviderDescriptor:
        return AsrProviderDescriptor(
            provider_id="counting-local",
            provider_version=version,
            mode="local",
            model_id="synthetic-model",
            model_snapshot_sha256="a" * 64,
            executable_sha256="b" * 64,
            cloud_upload_authorized=False,
            retention="local_ephemeral",
        )

    def _private_gold_case(
        self,
        case_id: str,
        stratum: str,
        reference_text: str,
        predicted_text: str,
        *,
        provider_failed: bool = False,
    ) -> AsrGoldCase:
        return AsrGoldCase(
            case_id,
            stratum,  # type: ignore[arg-type]
            reference_text,
            predicted_text,
            synthetic=False,
            provider_failed=provider_failed,
            provider=self._counting_descriptor(),
            input_hash=_sha(case_id.encode("utf-8")),
            prompt_sha256=_sha(b"synthetic-asr-prompt"),
        )

    def _passing_private_cases(self) -> list[AsrGoldCase]:
        cases = [
            self._private_gold_case(
                f"clear-{index}", "clear_mandarin", f"清晰普通话样本{index}", f"清晰普通话样本{index}"
            )
            for index in range(20)
        ]
        cases.extend(
            (
                self._private_gold_case("noise-1", "noise", "带噪样本", "带噪样本"),
                self._private_gold_case("music-1", "music", "音乐背景样本", "音乐背景样本"),
                self._private_gold_case("dialect-1", "dialect", "方言样本", "方言样本"),
                self._private_gold_case("mixed-1", "mixed_language", "mixed language", "mixed language"),
                self._private_gold_case("silence-1", "no_speech", "", ""),
            )
        )
        return cases

    def _write_private_gold_dataset(self, dataset_id: str, cases: list[AsrGoldCase]) -> Path:
        directory = self.paths.data_root / "runtime/diagnostics/asr-gold"
        directory.mkdir(mode=0o700)
        directory.chmod(0o700)
        payload = {
            "schema_version": "x2n-asr-gold-v1",
            "dataset_id": dataset_id,
            "cases": [
                {
                    "case_id": case.case_id,
                    "input_hash": case.input_hash,
                    "predicted_text": case.predicted_text,
                    "prompt_sha256": case.prompt_sha256,
                    "provider": None if case.provider is None else case.provider.safe_dict(),
                    "provider_failed": case.provider_failed,
                    "reference_text": case.reference_text,
                    "stratum": case.stratum,
                }
                for case in cases
            ],
        }
        target = directory / f"{dataset_id}.json"
        target.write_text(json.dumps(payload, ensure_ascii=False, sort_keys=True), encoding="utf-8")
        target.chmod(0o600)
        return target

    def test_local_whisper_adapter_caches_same_input_and_cleans_normalized_audio(self) -> None:
        provider, runner = self._local_provider()
        audio = self._audio()
        processor = AsrProcessor((provider,))
        with processor.session() as session:
            first = session.transcribe(audio, audio_seconds=1.0, provider_id="local-whispercpp")
            second = session.transcribe(audio, audio_seconds=1.0, provider_id="local-whispercpp")
            self.assertEqual(first.transcript.text, "合成转录")
            self.assertFalse(first.invocation.cache_hit)
            self.assertTrue(second.invocation.cache_hit)
            self.assertEqual(first.invocation.provider_calls, 1)
            self.assertEqual(second.invocation.provider_calls, 0)
            self.assertEqual(first.artifact_id, second.artifact_id)
            self.assertEqual([command.role for command in runner.commands], ["audio", "probe"])
            ledger = session.safe_ledger()
            self.assertEqual(ledger["cache_entries"], 1)
            self.assertEqual(ledger["cache_hits"], 1)
            self.assertEqual(ledger["cache_misses"], 1)
            self.assertEqual(ledger["cloud_uploads"], 0)
            self.assertEqual(ledger["budget"], {"audio_seconds": 1.0, "cloud_cost_microunits": 0, "invocations": 1})
            receipt = json.dumps(first.safe_dict(), sort_keys=True)
            self.assertNotIn(str(self.paths.data_root), receipt)
            self.assertNotIn("合成转录", receipt)
            with self.assertRaises(TypeError):
                pickle.dumps(first)
        self.assertEqual(tuple(audio.local_path.parent.glob("asr-*")), ())

    def test_new_provider_version_produces_a_distinct_ephemeral_artifact(self) -> None:
        audio = self._audio()
        first_provider, _ = self._local_provider(version="1", model_payload=b"synthetic-local-model-v1")
        with AsrProcessor((first_provider,)).session() as session:
            first = session.transcribe(audio, audio_seconds=1.0, provider_id="local-whispercpp")
        second_provider, _ = self._local_provider(version="2", model_payload=b"synthetic-local-model-v2")
        with AsrProcessor((second_provider,)).session() as session:
            second = session.transcribe(audio, audio_seconds=1.0, provider_id="local-whispercpp")
        self.assertNotEqual(first.artifact_id, second.artifact_id)
        self.assertNotEqual(
            first.invocation.provider.model_snapshot_sha256,
            second.invocation.provider.model_snapshot_sha256,
        )

    def test_malformed_or_timed_out_local_cli_fails_closed_and_cleans(self) -> None:
        for runner in (SyntheticAsrRunner(invalid_json=True), SyntheticAsrRunner(fail_role="probe")):
            with self.subTest(runner=runner.fail_role or "malformed"):
                provider, _ = self._local_provider(runner=runner)
                audio = self._audio(payload=(runner.fail_role or "malformed").encode("utf-8"))
                with self.assertRaises(X2NRuntimeError) as error:
                    with AsrProcessor((provider,)).session() as session:
                        session.transcribe(audio, audio_seconds=1.0, provider_id="local-whispercpp")
                self.assertIn(error.exception.code, {ErrorCode.DATA_INTEGRITY_FAILED, ErrorCode.POLICY_BLOCKED})
                self.assertEqual(tuple(audio.local_path.parent.glob("asr-*")), ())

    def test_cloud_route_and_relaxed_policy_are_blocked_before_any_provider_call(self) -> None:
        cloud = DisabledCloudAsrProvider(
            AsrProviderDescriptor(
                provider_id="disabled-cloud",
                provider_version="1",
                mode="cloud",
                model_id="cloud-model",
                model_snapshot_sha256="c" * 64,
                executable_sha256=None,
                cloud_upload_authorized=False,
                retention="disabled",
            )
        )
        audio = self._audio()
        with self.assertRaises(X2NRuntimeError) as error:
            with AsrProcessor((cloud,)).session() as session:
                session.transcribe(audio, audio_seconds=1.0, provider_id="disabled-cloud")
        self.assertEqual(error.exception.code, ErrorCode.POLICY_BLOCKED)
        with self.assertRaises(X2NRuntimeError) as error:
            AsrPolicy(max_cloud_cost_microunits=1)
        self.assertEqual(error.exception.code, ErrorCode.POLICY_BLOCKED)

    def test_chunk_rate_budget_blocks_before_provider_execution(self) -> None:
        policy = AsrPolicy(max_audio_seconds=60, chunk_seconds=30, max_chunks=2, max_invocations=1)
        provider = CountingProvider(self._counting_descriptor())
        with self.assertRaises(X2NRuntimeError) as error:
            with AsrProcessor((provider,), policy=policy).session() as session:
                session.transcribe(self._audio(), audio_seconds=31.0, provider_id="counting-local")
        self.assertEqual(error.exception.code, ErrorCode.POLICY_BLOCKED)
        self.assertEqual(provider.calls, 0)
        invalid = EphemeralDerivedArtifact("not-a-sha", "audio/mp4", 1, Path("/tmp/not-used.m4a"))
        with self.assertRaises(X2NRuntimeError) as error:
            with AsrProcessor((provider,)).session() as session:
                session.transcribe(invalid, audio_seconds=1.0, provider_id="counting-local")
        self.assertEqual(error.exception.code, ErrorCode.DATA_INTEGRITY_FAILED)
        self.assertEqual(provider.calls, 0)

    def test_evaluator_keeps_synthetic_contract_not_run_and_enforces_private_gold_gate(self) -> None:
        synthetic = (
            AsrGoldCase("synthetic-clear", "clear_mandarin", "你好世界", "你好世界", synthetic=True),
            AsrGoldCase("synthetic-silence", "no_speech", "", "", synthetic=True),
        )
        synthetic_report = AsrEvaluator().evaluate(synthetic, private_gold=False)
        self.assertEqual(synthetic_report.scope, "ci_synth_contract_only")
        self.assertEqual(synthetic_report.status, "not_run")
        private_cases = self._passing_private_cases()
        private_report = AsrEvaluator().evaluate(private_cases, private_gold=True)
        self.assertEqual(private_report.status, "pass")
        self.assertEqual(private_report.clear_mandarin_cases, 20)
        self.assertEqual(private_report.no_speech_hallucinations, 0)
        hallucinating = [*private_cases[:-1], self._private_gold_case("silence-2", "no_speech", "", "幻觉文本")]
        self.assertEqual(AsrEvaluator().evaluate(hallucinating, private_gold=True).status, "low_quality")
        with self.assertRaises(X2NRuntimeError) as error:
            AsrEvaluator().evaluate(private_cases[:20], private_gold=True)
        self.assertEqual(error.exception.code, ErrorCode.POLICY_BLOCKED)

    def test_private_dataset_loader_and_cli_emit_only_aggregate_receipt(self) -> None:
        self._write_private_gold_dataset("synthetic-contract", self._passing_private_cases())
        dataset = load_private_asr_gold_dataset(self.paths, "synthetic-contract")
        self.assertEqual(len(dataset.cases), 25)
        self.assertEqual(dataset.safe_dict()["case_count"], 25)
        arguments = build_parser().parse_args(("eval", "asr", "--dataset", "synthetic-contract"))
        with mock.patch.dict(
            os.environ,
            {ROOT_ENV: str(self.paths.data_root), DOWNLOAD_ENV: str(self.destination)},
            clear=False,
        ):
            receipt = run(arguments)
        rendered = json.dumps(receipt, ensure_ascii=False, sort_keys=True)
        self.assertEqual(receipt["status"], "PASS")
        self.assertEqual(receipt["evaluation"]["status"], "pass")
        self.assertNotIn(str(self.paths.data_root), rendered)
        self.assertNotIn("清晰普通话", rendered)
        self.assertNotIn("带噪样本", rendered)

    def test_cer_uses_the_original_reference_denominator_and_is_bounded(self) -> None:
        self.assertEqual(character_error_rate("a", "ab"), 1.0)
        self.assertEqual(character_error_rate("你好，世界", "你好世界"), 0.0)
        self.assertGreater(word_error_rate("你好 world", "你好 worlds"), 0.0)
        with self.assertRaises(X2NRuntimeError) as error:
            character_error_rate("a" * (MAX_CER_CHARS + 1), "")
        self.assertEqual(error.exception.code, ErrorCode.POLICY_BLOCKED)

    def test_real_ffmpeg_normalization_smoke_uses_only_temporary_synthetic_audio(self) -> None:
        if not shutil.which("ffmpeg") or not shutil.which("ffprobe"):
            self.skipTest("local FFmpeg capability is unavailable")
        audio = self._audio(payload=b"placeholder")
        generated = subprocess.run(
            (
                "ffmpeg",
                "-nostdin",
                "-hide_banner",
                "-loglevel",
                "error",
                "-f",
                "lavfi",
                "-i",
                "sine=frequency=1000:duration=0.2",
                "-c:a",
                "aac",
                "-y",
                str(audio.local_path),
            ),
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            check=False,
        )
        if generated.returncode != 0:
            self.skipTest("local FFmpeg cannot create the bounded synthetic fixture")
        audio.local_path.chmod(0o600)
        generated_payload = audio.local_path.read_bytes()
        audio = EphemeralDerivedArtifact(_sha(generated_payload), "audio/mp4", len(generated_payload), audio.local_path)
        normalizer = AsrAudioNormalizer(MediaToolchain.discover())
        with normalizer.chunks(audio, audio_seconds=0.2, deadline=time.monotonic() + 30) as chunks:
            self.assertEqual(len(chunks), 1)
            self.assertTrue(chunks[0].path.is_file())
            self.assertEqual(chunks[0].path.read_bytes()[:4], b"RIFF")
        self.assertEqual(tuple(audio.local_path.parent.glob("asr-*")), ())


if __name__ == "__main__":
    unittest.main()
