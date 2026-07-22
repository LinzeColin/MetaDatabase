from __future__ import annotations

import io
import json
import stat
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest import mock

from x2n_contracts import ErrorCode
from x2n_contracts.models import HealthComponentName

from x2n_companion import runtime_cli
from x2n_companion.adapter_guard import (
    AdapterExecutionGate,
    BatchDeletionGuard,
    MINIMUM_BATCH_START_INTERVAL_SECONDS,
    MINIMUM_ITEM_OBSERVATION_INTERVAL_SECONDS,
)
from x2n_companion.profile_session import (
    PROFILE_LAUNCH_CONFIRMATION,
    DoctorProbe,
    ProfileLauncher,
    SessionHealth,
    SessionHealthStore,
    build_doctor_report,
)
from x2n_companion.runtime import PROFILE_PLATFORMS, RuntimePaths, X2NRuntimeError


PROJECT_ROOT = Path(__file__).resolve().parents[3]
NOW = datetime(2026, 7, 22, 12, 0, 0, tzinfo=timezone.utc)


class AdapterRuntimeTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory(prefix="x2n-adapters001-")
        temporary_root = Path(self.temporary.name)
        self.destination = temporary_root / "MediaCrawler"
        self.destination.mkdir(mode=0o700)
        self.root = self.destination / "xhs-douyin-2notion"
        self.paths = RuntimePaths.from_values(
            str(self.root),
            str(self.destination),
            repository_root=PROJECT_ROOT,
            create=True,
        )
        self.executable = temporary_root / "synthetic-chrome"
        self.executable.write_text("synthetic executable", encoding="utf-8")
        self.executable.chmod(0o700)

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def _launcher(self, calls: list[tuple[str, ...]] | None = None) -> ProfileLauncher:
        def starter(argv: object) -> object:
            assert not isinstance(argv, (str, bytes))
            if calls is not None:
                calls.append(tuple(argv))  # type: ignore[arg-type]
            return object()

        return ProfileLauncher(
            self.paths,
            executable_resolver=lambda: self.executable,
            starter=starter,
        )

    @staticmethod
    def _healthy_session(platform: str) -> SessionHealth:
        return SessionHealth(platform, "ok", "authenticated_live_probe", None, None, True)

    def _probe(self, **overrides: object) -> DoctorProbe:
        values: dict[str, object] = {
            "extension_reachable": True,
            "native_host_registered": True,
            "companion_reachable": True,
            "canonical_db_state": "ok",
            "ffmpeg_available": True,
            "provider_configured": True,
            "notion_authorized": True,
            "chrome_available": True,
            "sessions": tuple(self._healthy_session(platform) for platform in PROFILE_PLATFORMS),
        }
        values.update(overrides)
        return DoctorProbe(**values)  # type: ignore[arg-type]

    def test_profile_launcher_uses_only_fixed_private_profile_and_redacted_receipt(self) -> None:
        calls: list[tuple[str, ...]] = []
        launcher = self._launcher(calls)
        plan = launcher.build_plan("xiaohongshu")
        self.assertEqual(plan.profile_directory, self.paths.browser_profile_directory("xiaohongshu"))
        self.assertIn(f"--user-data-dir={plan.profile_directory}", plan.argv)
        self.assertIn("chrome://newtab/", plan.argv)
        self.assertFalse(any("remote-debugging" in item for item in plan.argv))
        self.assertFalse(any("xiaohongshu.com" in item for item in plan.argv))

        receipt = launcher.launch("xiaohongshu", confirmation=PROFILE_LAUNCH_CONFIRMATION)
        rendered = json.dumps(receipt, ensure_ascii=False, sort_keys=True)
        self.assertEqual(len(calls), 1)
        self.assertTrue(receipt["launched"])
        self.assertFalse(receipt["cookie_exported"])
        self.assertFalse(receipt["login_automated"])
        self.assertFalse(receipt["verification_bypass"])
        self.assertNotIn(str(self.root), rendered)
        self.assertNotIn(self.temporary.name, rendered)

    def test_profile_launcher_rejects_missing_confirmation_unknown_platform_and_start_error(self) -> None:
        launcher = self._launcher()
        with self.assertRaises(X2NRuntimeError) as confirmation:
            launcher.launch("douyin", confirmation="yes")
        self.assertEqual(confirmation.exception.code, ErrorCode.POLICY_BLOCKED)
        with self.assertRaises(X2NRuntimeError) as platform:
            launcher.plan("unknown")
        self.assertEqual(platform.exception.code, ErrorCode.INVALID_INPUT)

        failing = ProfileLauncher(
            self.paths,
            executable_resolver=lambda: self.executable,
            starter=mock.Mock(side_effect=OSError(str(self.root))),
        )
        with self.assertRaises(X2NRuntimeError) as start:
            failing.launch("douyin", confirmation=PROFILE_LAUNCH_CONFIRMATION)
        self.assertEqual(start.exception.code, ErrorCode.DEPENDENCY_MISSING)
        self.assertNotIn(str(self.root), start.exception.safe_message)

    def test_profile_directory_symlink_and_permission_drift_fail_closed(self) -> None:
        profile = self.paths.browser_profile_directory("bilibili")
        profile.chmod(0o755)
        with self.assertRaises(X2NRuntimeError) as mode:
            self.paths.browser_profile_directory("bilibili")
        self.assertEqual(mode.exception.code, ErrorCode.POLICY_BLOCKED)
        profile.chmod(0o700)
        profile.rmdir()
        profile.symlink_to(self.paths.browser_profile_directory("douyin"), target_is_directory=True)
        with self.assertRaises(X2NRuntimeError) as symlink:
            self.paths.browser_profile_directory("bilibili")
        self.assertEqual(symlink.exception.code, ErrorCode.POLICY_BLOCKED)

    def test_session_checkpoint_is_owner_only_path_free_and_short_lived(self) -> None:
        store = SessionHealthStore(self.paths)
        health = store.record("xiaohongshu", "authenticated", observed_at=NOW)
        self.assertEqual(health.state, "ok")
        self.assertEqual(stat.S_IMODE(store.path.stat().st_mode), 0o600)
        checkpoint = store.path.read_text(encoding="utf-8")
        self.assertNotIn(str(self.root), checkpoint)
        self.assertNotIn("cookie", checkpoint.lower())
        self.assertEqual(store.evaluate("xiaohongshu", now=NOW + timedelta(seconds=299)).state, "ok")
        stale = store.evaluate("xiaohongshu", now=NOW + timedelta(seconds=301))
        self.assertEqual(stale.state, "blocked")
        self.assertEqual(stale.reason, "session_observation_stale")
        self.assertEqual(stale.error_code, ErrorCode.ADAPTER_AUTH_EXPIRED)
        store.path.chmod(0o644)
        with self.assertRaises(X2NRuntimeError) as mode:
            store.evaluate("xiaohongshu", now=NOW)
        self.assertEqual(mode.exception.code, ErrorCode.POLICY_BLOCKED)

    def test_expired_login_verification_and_platform_drift_require_safe_user_action(self) -> None:
        store = SessionHealthStore(self.paths)
        expectations = {
            "login_required": ErrorCode.ADAPTER_AUTH_EXPIRED,
            "expired": ErrorCode.ADAPTER_AUTH_EXPIRED,
            "verification_required": ErrorCode.ADAPTER_AUTH_EXPIRED,
            "platform_changed": ErrorCode.PLATFORM_CHANGED,
        }
        for signal, code in expectations.items():
            with self.subTest(signal=signal):
                result = store.record("douyin", signal, observed_at=NOW)  # type: ignore[arg-type]
                self.assertEqual(result.state, "blocked")
                self.assertEqual(result.error_code, code)
                self.assertIsNotNone(result.safe_action)
                rendered = json.dumps(result.safe_dict(), ensure_ascii=False)
                self.assertNotIn(str(self.root), rendered)
                self.assertNotIn("bypass", rendered.lower())

    def test_missing_future_or_corrupt_session_health_never_claims_logged_in(self) -> None:
        store = SessionHealthStore(self.paths)
        self.assertEqual(store.evaluate("weibo", now=NOW).reason, "session_observation_missing")
        store.record("weibo", "authenticated", observed_at=NOW + timedelta(seconds=31))
        self.assertEqual(store.evaluate("weibo", now=NOW).reason, "session_observation_stale")
        store.path.write_text("{}", encoding="utf-8")
        store.path.chmod(0o600)
        with self.assertRaises(X2NRuntimeError) as corrupted:
            store.evaluate("weibo", now=NOW)
        self.assertEqual(corrupted.exception.code, ErrorCode.DATA_INTEGRITY_FAILED)

    def test_doctor_reports_all_components_and_distinguishes_core_from_optional(self) -> None:
        healthy = build_doctor_report(self._probe(), observed_at=NOW)
        self.assertEqual(healthy.overall, "ok")
        self.assertEqual({item.component for item in healthy.components}, set(HealthComponentName))

        optional = build_doctor_report(
            self._probe(ffmpeg_available=False, provider_configured=False, notion_authorized=False),
            observed_at=NOW,
        )
        self.assertEqual(optional.overall, "degraded")
        states = {item.component.value: item.state for item in optional.components}
        self.assertEqual(states["canonical_db"], "ok")
        self.assertEqual(states["ffmpeg"], "degraded")
        self.assertEqual(states["provider"], "degraded")
        self.assertEqual(states["notion"], "degraded")
        self.assertFalse(optional.safe_dict()["noncore_missing_disables_canonical"])

    def test_doctor_blocks_native_host_and_busy_database_with_executable_remediation(self) -> None:
        for field, component in (("native_host_registered", "native_host"), ("canonical_db_state", "canonical_db")):
            overrides = {field: False if field == "native_host_registered" else "busy"}
            with self.subTest(component=component):
                report = build_doctor_report(self._probe(**overrides), observed_at=NOW)
                self.assertEqual(report.overall, "blocked")
                row = next(item for item in report.safe_dict()["components"] if item["component"] == component)
                self.assertEqual(row["state"], "blocked")
                self.assertTrue(row["remediation"]["command"])

    def test_doctor_profile_not_logged_in_blocks_adapter_but_preserves_local_core(self) -> None:
        sessions = list(self._probe().sessions)
        sessions[0] = SessionHealth(
            "xiaohongshu",
            "blocked",
            "expired",
            ErrorCode.ADAPTER_AUTH_EXPIRED,
            "open_dedicated_profile_and_login_manually",
            True,
        )
        report = build_doctor_report(self._probe(sessions=tuple(sessions)), observed_at=NOW)
        self.assertEqual(report.overall, "degraded")
        adapter = next(item for item in report.components if item.component is HealthComponentName.ADAPTER)
        canonical = next(item for item in report.components if item.component is HealthComponentName.CANONICAL_DB)
        self.assertEqual(adapter.state, "blocked")
        self.assertEqual(canonical.state, "ok")
        rendered = json.dumps(report.safe_dict(), ensure_ascii=False, sort_keys=True)
        self.assertNotIn(str(self.root), rendered)
        self.assertNotIn(self.temporary.name, rendered)

        incomplete = build_doctor_report(self._probe(sessions=tuple(sessions[:2])), observed_at=NOW)
        incomplete_adapter = next(
            item for item in incomplete.components if item.component is HealthComponentName.ADAPTER
        )
        self.assertEqual(incomplete_adapter.state, "blocked")
        self.assertEqual(incomplete_adapter.error_code, ErrorCode.DATA_INTEGRITY_FAILED)

    def test_adapter_mutex_is_cross_instance_nonblocking_and_owner_only(self) -> None:
        first = AdapterExecutionGate(self.paths)
        second = AdapterExecutionGate(self.paths)
        with first.acquire("xiaohongshu", now=100.0) as lease:
            self.assertTrue(lease.safe_dict()["mutex_acquired"])
            with self.assertRaises(X2NRuntimeError) as blocked:
                with second.acquire("douyin", now=100.0):
                    self.fail("second Adapter must not acquire the shared Profile mutex")
            self.assertEqual(blocked.exception.code, ErrorCode.POLICY_BLOCKED)
        self.assertEqual(stat.S_IMODE(first.lock_path.stat().st_mode), 0o600)
        first.lock_path.chmod(0o644)
        with self.assertRaises(X2NRuntimeError) as mode:
            with AdapterExecutionGate(self.paths).acquire("bilibili", now=200.0):
                self.fail("non-private mutex must fail closed")
        self.assertEqual(mode.exception.code, ErrorCode.POLICY_BLOCKED)

    def test_adapter_rate_gate_never_sleeps_or_auto_retries(self) -> None:
        gate = AdapterExecutionGate(self.paths)
        with gate.acquire("xiaohongshu", now=100.0) as lease:
            first = lease.permit_item_observation(now=100.0)
            self.assertTrue(first["item_observation_permitted"])
            with self.assertRaises(X2NRuntimeError) as item_rate:
                lease.permit_item_observation(now=102.9)
            self.assertEqual(item_rate.exception.code, ErrorCode.RATE_LIMITED)
            self.assertTrue(lease.permit_item_observation(now=103.0)["item_observation_permitted"])

        with self.assertRaises(X2NRuntimeError) as batch_rate:
            with AdapterExecutionGate(self.paths).acquire("xiaohongshu", now=129.9):
                self.fail("batch start inside the minimum interval must fail")
        self.assertEqual(batch_rate.exception.code, ErrorCode.RATE_LIMITED)
        with AdapterExecutionGate(self.paths).acquire("xiaohongshu", now=130.0):
            pass
        state = gate.state_path.read_text(encoding="utf-8")
        self.assertNotIn(str(self.root), state)
        self.assertNotIn("cookie", state.lower())

    def test_adapter_gate_rejects_weaker_policy_clock_rollback_and_corrupt_state(self) -> None:
        with self.assertRaises(X2NRuntimeError) as batch:
            AdapterExecutionGate(
                self.paths,
                batch_interval_seconds=MINIMUM_BATCH_START_INTERVAL_SECONDS - 0.1,
            )
        self.assertEqual(batch.exception.code, ErrorCode.POLICY_BLOCKED)
        with self.assertRaises(X2NRuntimeError) as item:
            AdapterExecutionGate(
                self.paths,
                item_interval_seconds=MINIMUM_ITEM_OBSERVATION_INTERVAL_SECONDS - 0.1,
            )
        self.assertEqual(item.exception.code, ErrorCode.POLICY_BLOCKED)

        gate = AdapterExecutionGate(self.paths)
        with gate.acquire("douyin", now=200.0):
            pass
        with self.assertRaises(X2NRuntimeError) as rollback:
            with AdapterExecutionGate(self.paths).acquire("douyin", now=199.0):
                self.fail("clock rollback must fail closed")
        self.assertEqual(rollback.exception.code, ErrorCode.DATA_INTEGRITY_FAILED)
        gate.state_path.write_text("{}", encoding="utf-8")
        gate.state_path.chmod(0o600)
        with self.assertRaises(X2NRuntimeError) as corrupted:
            with AdapterExecutionGate(self.paths).acquire("taobao", now=300.0):
                self.fail("corrupt state must fail closed")
        self.assertEqual(corrupted.exception.code, ErrorCode.DATA_INTEGRITY_FAILED)

    def test_batch_deletion_guard_covers_all_non_authoritative_outcomes(self) -> None:
        for outcome in ("auth_expired", "http_error", "platform_changed", "empty_response", "partial_scan"):
            with self.subTest(outcome=outcome):
                decision = BatchDeletionGuard().observe(outcome, ("relation-a", "relation-b"))  # type: ignore[arg-type]
                self.assertEqual(decision.removed_count, 0)
                self.assertEqual(decision.tombstone_candidate_count, 0)
                self.assertEqual(decision.physical_delete_count, 0)
                self.assertEqual(decision.content_delete_count, 0)

    def test_batch_deletion_requires_two_consecutive_complete_successes_and_only_marks_candidate(self) -> None:
        guard = BatchDeletionGuard()
        first = guard.observe("complete_success", ("relation-a", "relation-b"))
        second = guard.observe("complete_success", ("relation-a", "relation-b"))
        self.assertEqual(first.tombstone_candidate_count, 0)
        self.assertEqual(second.tombstone_candidate_count, 2)
        self.assertEqual(second.removed_count, 0)
        self.assertEqual(second.physical_delete_count, 0)
        self.assertEqual(second.content_delete_count, 0)

        interrupted = guard.observe("http_error", ("relation-a",))
        restarted = guard.observe("complete_success", ("relation-a",))
        self.assertEqual(interrupted.tombstone_candidate_count, 0)
        self.assertEqual(restarted.tombstone_candidate_count, 0)

    def test_registered_fixture_drives_expired_session_and_batch_oracles(self) -> None:
        fixture_path = PROJECT_ROOT / "packages/test-fixtures/adapters/v1/profile_session/fixture_manifest.json"
        fixture = json.loads(fixture_path.read_text(encoding="utf-8"))
        self.assertTrue(fixture["synthetic"])
        self.assertEqual(len(fixture["session_cases"]), 7)
        self.assertEqual(len(fixture["batch_cases"]), 7)
        for field in (
            "contains_accounts",
            "contains_cookies",
            "contains_credentials",
            "contains_local_absolute_paths",
            "contains_media_urls",
            "contains_private_content",
            "contains_profile_paths",
        ):
            self.assertFalse(fixture[field])

        store = SessionHealthStore(self.paths)
        for case in fixture["session_cases"]:
            with self.subTest(case=case["id"]):
                if store.path.exists():
                    store.path.unlink()
                signal = case["signal"]
                if signal is None:
                    result = store.evaluate("kuaishou", now=NOW)
                else:
                    observed_at = NOW if case["fresh"] else NOW - timedelta(seconds=301)
                    store.record("kuaishou", signal, observed_at=observed_at)
                    result = store.evaluate("kuaishou", now=NOW)
                self.assertEqual(result.state, case["expected_state"])
                self.assertEqual(
                    None if result.error_code is None else result.error_code.value,
                    case["expected_error_code"],
                )

        guard = BatchDeletionGuard()
        for case in fixture["batch_cases"]:
            with self.subTest(case=case["id"]):
                decision = guard.observe(case["outcome"], ("synthetic-relation",))
                self.assertEqual(decision.removed_count, case["expected_removed"])
                self.assertEqual(
                    decision.tombstone_candidate_count,
                    case["expected_tombstone_candidates"],
                )

    def test_cli_exposes_only_fixed_profile_actions_and_safe_health_receipts(self) -> None:
        parser = runtime_cli.build_parser()
        health_args = parser.parse_args(["profile", "health", "--platform", "xiaohongshu"])
        with mock.patch.object(runtime_cli, "_paths", return_value=self.paths):
            payload = runtime_cli.run(health_args)
        rendered = json.dumps(payload, ensure_ascii=False, sort_keys=True)
        self.assertEqual(payload["task_id"], "TSK.x2n.adapters.001")
        self.assertEqual(payload["state"], "blocked")
        self.assertNotIn(str(self.root), rendered)

        with self.assertRaises(SystemExit):
            with mock.patch("sys.stderr", new=io.StringIO()):
                parser.parse_args(["profile", "launch", "--platform", "unknown", "--confirm", "anything"])


if __name__ == "__main__":
    unittest.main()
