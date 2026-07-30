from __future__ import annotations

import hashlib
import json
import os
import tempfile
import unittest
import uuid
from collections.abc import Callable
from pathlib import Path
from unittest import mock

from x2n_contracts import ErrorCode, build_content_key, canonical_json_sha256
from x2n_contracts.models import CaptureCurrentPayload

from x2n_companion.adapter_dispatch import SCOPE_BINDINGS
from x2n_companion.canonical_store import CanonicalStore, current_page_identity_from_job
from x2n_companion.notion_sink import NotionMockServer, NotionSinkWorker, RateLimitedNotionClient, RequestRateGate
from x2n_companion.operations import (
    RECOVERY_STAGES,
    DiagnosticJournal,
    OperationsService,
    assert_diagnostic_safe,
)
from x2n_companion.orchestrator import (
    TRANSITION_AFTER_CANONICAL,
    TRANSITION_BEFORE_CANONICAL,
    CurrentPageOrchestrator,
)
from x2n_companion.profile_session import DoctorProbe, SessionHealth
from x2n_companion.runtime import PROFILE_PLATFORMS, RuntimePaths, X2NRuntimeError
from x2n_companion.runtime_cli import build_parser, run


PROJECT_ROOT = Path(__file__).resolve().parents[3]
NOW = "2026-07-29T00:00:00Z"


class InjectedKill(RuntimeError):
    pass


class FakeClock:
    def __init__(self) -> None:
        self.value = 0.0

    def monotonic(self) -> float:
        return self.value

    def sleep(self, seconds: float) -> None:
        self.value += seconds


def _payload(index: int = 0) -> CaptureCurrentPayload:
    content_id = f"operations-{index:05d}"
    return CaptureCurrentPayload.model_validate_json(
        json.dumps(
            {
                "auto_scroll": False,
                "category_id": None,
                "change_account_state": False,
                "page_context": {
                    "content_id": content_id,
                    "content_type": "video",
                    "title": f"Synthetic operations title {index}",
                },
                "page_url": f"https://www.xiaohongshu.com/explore/{content_id}",
                "platform": "xiaohongshu",
                "relation": "saved_current",
                "user_gesture": True,
            },
            ensure_ascii=False,
        )
    )


def _request_id(index: int) -> str:
    return str(uuid.uuid5(uuid.NAMESPACE_URL, f"x2n-operations:{index}"))


def _sha(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


class OperationsTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory(prefix="x2n-operations-")
        self.destination = Path(self.temporary.name) / "MediaCrawler"
        self.destination.mkdir(mode=0o700)
        self.paths = RuntimePaths.from_values(
            str(self.destination / "xhs-douyin-2notion"),
            str(self.destination),
            repository_root=PROJECT_ROOT,
            create=True,
        )
        self.store = CanonicalStore(self.paths)
        self.store.initialize()
        self.service = OperationsService(self.store)
        self.clock = FakeClock()

    def tearDown(self) -> None:
        self.temporary.cleanup()

    @staticmethod
    def _healthy_probe(**overrides: object) -> DoctorProbe:
        values: dict[str, object] = {
            "extension_reachable": True,
            "native_host_registered": True,
            "companion_reachable": True,
            "canonical_db_state": "ok",
            "ffmpeg_available": True,
            "provider_configured": True,
            "notion_authorized": True,
            "chrome_available": True,
            "sessions": tuple(
                SessionHealth(platform, "ok", "authenticated_live_probe", None, None, True)
                for platform in PROFILE_PLATFORMS
            ),
        }
        values.update(overrides)
        return DoctorProbe(**values)  # type: ignore[arg-type]

    def _capture(
        self,
        index: int,
        *,
        transition_hook: Callable[[str], None] | None = None,
    ) -> object:
        payload = _payload(index)
        return CurrentPageOrchestrator(self.store, clock=lambda: NOW).execute(
            payload,
            request_id=_request_id(index),
            payload_hash=canonical_json_sha256(payload.model_dump(mode="json", by_alias=True)),
            transition_hook=transition_hook,
        )

    def _notion_worker(self) -> tuple[NotionMockServer, NotionSinkWorker]:
        server = NotionMockServer(monotonic=self.clock.monotonic)
        client = RateLimitedNotionClient(
            server,
            RequestRateGate(monotonic=self.clock.monotonic, sleeper=self.clock.sleep),
        )
        return server, NotionSinkWorker(self.store, client)

    def test_redaction_canaries_and_allowlisted_journal(self) -> None:
        event = self.service.record_stage_outcome(
            stage="asr",
            state="failed",
            error_code=ErrorCode.PROVIDER_FAILED,
            occurred_at=NOW,
        )
        self.assertEqual(event["error_code"], ErrorCode.PROVIDER_FAILED.value)
        self.assertTrue(str(event["run_id"]).startswith("run_diag_"))
        job = self.store.submit_scope_dispatch_job(
            request_id=str(uuid.uuid4()),
            payload_hash=_sha("operations-dispatch-payload"),
            binding=SCOPE_BINDINGS[0],
            dispatch_receipt_hash=_sha("operations-dispatch-receipt"),
        )
        self.store.fail_scope_dispatch_job(
            job_id=job.job_id,
            provenance_hash=_sha("operations-dispatch-failure"),
            fallback_eligible=True,
        )
        bundle = self.service.diagnostic_bundle(probe=self._healthy_probe())
        rendered = json.dumps(bundle, ensure_ascii=False, sort_keys=True)
        journal = DiagnosticJournal(self.paths).path.read_text(encoding="utf-8")
        for canary in (
            {"unrecognized": "private model completion"},
            {"body": "private article text"},
            {"token": ("gh" + "p_") + "a" * 36},
            {"cookie": "session=private"},
            {"url": "https://example.invalid/path?token=private"},
            {"local_username": "local-user"},
            {"profile_path": "/" + "Users/" + "local-user/private-profile"},
            {"model_output": "private model completion"},
        ):
            with self.subTest(canary=next(iter(canary))):
                with self.assertRaises(X2NRuntimeError) as blocked:
                    assert_diagnostic_safe(canary)
                self.assertEqual(blocked.exception.code, ErrorCode.POLICY_BLOCKED)
                self.assertNotIn(next(iter(canary.values())), rendered)
                self.assertNotIn(next(iter(canary.values())), journal)
        with self.assertRaises(X2NRuntimeError) as component:
            self.service.record_stage_outcome(stage="asr", state="succeeded", component="private model completion")
        self.assertEqual(component.exception.code, ErrorCode.INVALID_INPUT)
        self.assertNotIn(str(self.paths.data_root), rendered)
        self.assertNotIn("https://", rendered)
        self.assertEqual(bundle["journal"]["event_count"], 1)
        self.assertEqual(bundle["metrics"]["authority"], "derived_from_canonical_store_not_persisted")
        failed_run = bundle["metrics"]["failed_runs"]
        self.assertEqual(len(failed_run), 1)
        self.assertEqual(failed_run[0]["error_code"], ErrorCode.ADAPTER_FAILED_FALLBACK_AVAILABLE.value)
        self.assertEqual(failed_run[0]["state"], "failed")
        self.assertTrue(failed_run[0]["run_id"].startswith("run_diag_"))

    def test_doctor_degraded_cases_are_safe_and_precise(self) -> None:
        blocked_session = SessionHealth(
            "xiaohongshu",
            "blocked",
            "expired",
            ErrorCode.ADAPTER_AUTH_EXPIRED,
            "open_dedicated_profile_and_login_manually",
            False,
        )
        sessions = list(self._healthy_probe().sessions)
        sessions[0] = blocked_session
        cases = {
            "ffmpeg": (self._healthy_probe(ffmpeg_available=False), "ffmpeg", "degraded", "degraded"),
            "native": (self._healthy_probe(native_host_registered=False), "native_host", "blocked", "blocked"),
            "profile": (self._healthy_probe(sessions=tuple(sessions)), "adapter", "blocked", "degraded"),
            "notion": (self._healthy_probe(notion_authorized=False), "notion", "degraded", "degraded"),
            "provider": (self._healthy_probe(provider_configured=False), "provider", "degraded", "degraded"),
            "db_busy": (self._healthy_probe(canonical_db_state="busy"), "canonical_db", "blocked", "blocked"),
        }
        for name, (probe, component, expected_state, overall) in cases.items():
            with self.subTest(case=name):
                report = self.service.doctor(probe=probe).safe_dict()
                row = next(item for item in report["components"] if item["component"] == component)
                self.assertEqual((row["state"], report["overall"]), (expected_state, overall))
                self.assertTrue(row["remediation"]["action"])
                self.assertNotIn(str(self.paths.data_root), json.dumps(report, ensure_ascii=False))
                assert_diagnostic_safe(report)
        optional = self.service.doctor(
            probe=self._healthy_probe(ffmpeg_available=False, provider_configured=False, notion_authorized=False)
        ).safe_dict()
        self.assertEqual(optional["overall"], "degraded")
        self.assertFalse(optional["noncore_missing_disables_canonical"])

    def test_all_stage_kill_records_are_terminal_and_do_not_write_canonical_content(self) -> None:
        before = self.store.counts()

        def kill_before(transition: str) -> None:
            if transition == TRANSITION_BEFORE_CANONICAL:
                raise InjectedKill("source")

        with self.assertRaises(InjectedKill):
            self._capture(1, transition_hook=kill_before)
        self.assertEqual(self.store.counts(), before)
        for stage in RECOVERY_STAGES:
            with self.subTest(stage=stage):
                record = self.service.record_stage_outcome(
                    stage=stage,
                    state="failed",
                    error_code=ErrorCode.PROVIDER_FAILED,
                    occurred_at=NOW,
                )
                self.assertEqual(record["stage"], stage)
                self.assertEqual(record["error_code"], ErrorCode.PROVIDER_FAILED.value)
                self.assertTrue(str(record["run_id"]).startswith("run_diag_"))
        self.assertEqual(self.store.counts(), before)
        events = DiagnosticJournal(self.paths).events(limit=len(RECOVERY_STAGES))
        self.assertEqual(tuple(item.stage for item in events), RECOVERY_STAGES)
        self.assertTrue(all(item.state == "failed" for item in events))

    def test_startup_recovery_resumes_rebuilds_and_reconciles_without_duplicates(self) -> None:
        def kill_after_canonical(transition: str) -> None:
            if transition == TRANSITION_AFTER_CANONICAL:
                raise InjectedKill(transition)

        with self.assertRaises(InjectedKill):
            self._capture(2, transition_hook=kill_after_canonical)
        job_id = self.store.resumable_current_page_jobs()[0]
        identity = current_page_identity_from_job(job_id)
        content_key = build_content_key("xiaohongshu", "operations-00002")
        self.store.create_media_lease(
            run_id=identity.run_id,
            content_key=content_key,
            purpose="synthetic",
            content_hash=_sha("operations-media"),
            mime="application/octet-stream",
            size_bytes=0,
            duration_seconds=None,
            ttl_seconds=1,
            now=NOW,
        )
        first = self.service.startup_recovery(now="2026-07-29T00:00:02Z")
        self.assertEqual(first.current_page_resumed, 1)
        self.assertEqual(first.after.expired_media_leases, 0)
        self.assertEqual(first.after.running_jobs, 0)
        self.assertEqual(first.canonical_before, first.canonical_after)
        self.assertEqual((first.artifacts_before, first.artifacts_after), (0, 1))
        self.assertEqual(first.notion_mode, "disabled_not_configured")
        self.assertEqual(first.markdown.manifest.content_count, 1)

        server, worker = self._notion_worker()
        reconciled = self.service.startup_recovery(now="2026-07-29T00:00:03Z", notion_worker=worker)
        self.assertEqual(
            (reconciled.notion_mode, server.page_create_count, len(server.pages)), ("explicit_worker", 1, 1)
        )
        repeated = self.service.startup_recovery(now="2026-07-29T00:00:04Z", notion_worker=worker)
        self.assertEqual((repeated.current_page_resumed, server.page_create_count, len(server.pages)), (0, 1, 1))
        self.assertEqual(self.store.counts()["artifact"], 1)
        self.assertEqual(self.store.resumable_current_page_jobs(), ())
        self.assertFalse(repeated.safe_dict()["append_only_artifacts"]["decreased"])

    def test_cli_operations_is_redacted_and_recovery_requires_confirmation(self) -> None:
        environment = {
            "X2N_DATA_ROOT": str(self.paths.data_root),
            "X2N_DOWNLOAD_DESTINATION": str(self.destination),
        }
        with mock.patch.dict(os.environ, environment):
            parser = build_parser()
            diagnostics = run(parser.parse_args(["operations", "diagnostics"]))
            self.assertEqual((diagnostics["task_id"], diagnostics["status"]), ("TSK.x2n.uxops.004", "PASS"))
            rendered = json.dumps(diagnostics, ensure_ascii=False, sort_keys=True)
            self.assertNotIn(str(self.paths.data_root), rendered)
            self.assertNotIn("https://", rendered)
            rejected = parser.parse_args(["operations", "startup-recovery", "--confirm", "wrong"])
            with self.assertRaises(X2NRuntimeError) as blocked:
                run(rejected)
            self.assertEqual(blocked.exception.code, ErrorCode.POLICY_BLOCKED)


if __name__ == "__main__":
    unittest.main()
