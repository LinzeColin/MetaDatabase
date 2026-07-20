from __future__ import annotations

import io
import json
import os
import shutil
import stat
import tempfile
import unittest
import uuid
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any
from unittest import mock

from x2n_contracts import ErrorCode, canonical_json_sha256

from x2n_companion.canonical_store import CanonicalStore
from x2n_companion.native_host import (
    DEVELOPMENT_EXTENSION_ORIGIN,
    HOST_NAME,
    MAX_MESSAGE_BYTES,
    dispatch_wire,
    run_host,
)
from x2n_companion.native_host_installer import (
    INSTALL_CONFIRMATION,
    UNINSTALL_CONFIRMATION,
    create_plan,
    execute_plan,
)
from x2n_companion.runtime import RuntimePaths, X2NRuntimeError


PROJECT_ROOT = Path(__file__).resolve().parents[3]


def _request(
    action: str,
    payload: dict[str, Any],
    *,
    request_id: str | None = None,
    schema_version: str = "1.0",
    extra: dict[str, Any] | None = None,
) -> bytes:
    value: dict[str, Any] = {
        "action": action,
        "payload": payload,
        "payload_hash": canonical_json_sha256(payload),
        "request_id": request_id or str(uuid.uuid4()),
        "schema_version": schema_version,
        "sent_at": "2026-07-20T00:00:00Z",
    }
    if extra:
        value.update(extra)
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"), sort_keys=True).encode("utf-8")


def _capture_payload(content_id: str = "synthetic-001") -> dict[str, Any]:
    return {
        "auto_scroll": False,
        "category_id": None,
        "change_account_state": False,
        "page_context": {"content_id": content_id, "content_type": "video", "title": "Synthetic"},
        "page_url": f"https://www.xiaohongshu.com/explore/{content_id}",
        "platform": "xiaohongshu",
        "relation": "saved_current",
        "user_gesture": True,
    }


class NativeHostTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory(prefix="x2n-f004-host-")
        self.home = Path(self.temporary.name) / "home"
        self.home.mkdir(mode=0o700)
        self.destination = Path(self.temporary.name) / "MediaCrawler"
        self.destination.mkdir(mode=0o700)
        self.root = self.destination / "xhs-douyin-2notion"
        self.paths = RuntimePaths.from_values(
            str(self.root),
            str(self.destination),
            repository_root=PROJECT_ROOT,
            create=True,
        )
        self.store = CanonicalStore(self.paths)
        self.store.initialize()
        self.env = {
            "X2N_DATA_ROOT": str(self.root),
            "X2N_DOWNLOAD_DESTINATION": str(self.destination),
        }

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def test_health_and_capabilities_are_short_lived(self) -> None:
        for action in ("health", "get_capabilities"):
            response = dispatch_wire(_request(action, {}), origin=DEVELOPMENT_EXTENSION_ORIGIN, store=self.store)
            self.assertTrue(response.accepted)
            self.assertEqual(response.status.value, "completed")
            self.assertIsNone(response.job_id)
        self.assertEqual(self.store.counts()["request_ledger"], 0)

    def test_submission_is_atomic_idempotent_and_payload_free(self) -> None:
        request_id = str(uuid.uuid4())
        wire = _request("capture_current", _capture_payload(), request_id=request_id)
        first = dispatch_wire(wire, origin=DEVELOPMENT_EXTENSION_ORIGIN, store=self.store)
        duplicate = dispatch_wire(wire, origin=DEVELOPMENT_EXTENSION_ORIGIN, store=self.store)
        self.assertTrue(first.accepted)
        self.assertEqual(first.status.value, "queued")
        self.assertEqual(first.job_id, duplicate.job_id)
        self.assertEqual(self.store.counts()["request_ledger"], 1)
        self.assertEqual(self.store.counts()["run_record"], 1)

        state = dispatch_wire(
            _request("get_job", {"job_id": str(first.job_id)}),
            origin=DEVELOPMENT_EXTENSION_ORIGIN,
            store=self.store,
        )
        self.assertTrue(state.accepted)
        self.assertEqual(state.status.value, "queued")
        self.assertEqual(state.job_id, first.job_id)

        rendered_database = self.paths.database.read_bytes()
        self.assertNotIn(b"xiaohongshu.com", rendered_database)
        self.assertNotIn(b"Synthetic", rendered_database)

    def test_one_hundred_concurrent_duplicates_create_one_job(self) -> None:
        request_id = str(uuid.uuid4())
        payload_hash = canonical_json_sha256(_capture_payload())

        def submit(_: int) -> tuple[str, str]:
            job = self.store.submit_skeleton_job(
                request_id=request_id,
                payload_hash=payload_hash,
                run_kind="native_capture_skeleton",
            )
            return job.job_id, job.disposition.value

        with ThreadPoolExecutor(max_workers=12) as executor:
            results = list(executor.map(submit, range(100)))
        self.assertEqual(len({job_id for job_id, _ in results}), 1)
        self.assertEqual(sum(disposition == "new_request" for _, disposition in results), 1)
        self.assertEqual(sum(disposition == "return_existing_job" for _, disposition in results), 99)
        self.assertEqual(self.store.counts()["request_ledger"], 1)
        self.assertEqual(self.store.counts()["run_record"], 1)

    def test_duplicate_request_conflict_is_rejected(self) -> None:
        request_id = str(uuid.uuid4())
        accepted = dispatch_wire(
            _request("capture_current", _capture_payload("synthetic-001"), request_id=request_id),
            origin=DEVELOPMENT_EXTENSION_ORIGIN,
            store=self.store,
        )
        rejected = dispatch_wire(
            _request("capture_current", _capture_payload("synthetic-002"), request_id=request_id),
            origin=DEVELOPMENT_EXTENSION_ORIGIN,
            store=self.store,
        )
        self.assertTrue(accepted.accepted)
        self.assertFalse(rejected.accepted)
        self.assertEqual(rejected.error.code, ErrorCode.NATIVE_DUPLICATE_REQUEST)
        self.assertEqual(self.store.counts()["request_ledger"], 1)

    def test_origin_schema_action_size_and_injections_fail_closed(self) -> None:
        baseline = _request("capture_current", _capture_payload())
        cases = [
            (baseline, "chrome-extension://aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa/", ErrorCode.NATIVE_ORIGIN_REJECTED),
            (_request("unknown", {}), DEVELOPMENT_EXTENSION_ORIGIN, ErrorCode.NATIVE_ACTION_UNKNOWN),
            (_request("health", {}, schema_version="2.0"), DEVELOPMENT_EXTENSION_ORIGIN, ErrorCode.INVALID_SCHEMA_VERSION),
            (_request("health", {}, extra={"undeclared": True}), DEVELOPMENT_EXTENSION_ORIGIN, ErrorCode.UNKNOWN_FIELD),
            (_request("capture_current", {**_capture_payload(), "shell": "synthetic"}), DEVELOPMENT_EXTENSION_ORIGIN, ErrorCode.SECURITY_INJECTION_BLOCKED),
            (_request("capture_current", {**_capture_payload(), "local_path": "synthetic"}), DEVELOPMENT_EXTENSION_ORIGIN, ErrorCode.SECURITY_INJECTION_BLOCKED),
            (_request("capture_current", {**_capture_payload(), "download_url": "synthetic"}), DEVELOPMENT_EXTENSION_ORIGIN, ErrorCode.SECURITY_INJECTION_BLOCKED),
            (_request("capture_current", {**_capture_payload(), "page_url": "https://example.invalid/content"}), DEVELOPMENT_EXTENSION_ORIGIN, ErrorCode.URL_REJECTED),
            (b"x" * (MAX_MESSAGE_BYTES + 1), DEVELOPMENT_EXTENSION_ORIGIN, ErrorCode.NATIVE_MESSAGE_TOO_LARGE),
        ]
        for raw, origin, code in cases:
            with self.subTest(code=code.value):
                response = dispatch_wire(raw, origin=origin, store=self.store)
                self.assertFalse(response.accepted)
                self.assertEqual(response.error.code, code)
        self.assertEqual(self.store.counts()["request_ledger"], 0)
        self.assertEqual(self.store.counts()["run_record"], 0)

    def test_cancel_and_retry_are_policy_blocked(self) -> None:
        missing_job = str(uuid.uuid4())
        for action in ("cancel_job", "retry_job"):
            response = dispatch_wire(
                _request(action, {"job_id": missing_job}),
                origin=DEVELOPMENT_EXTENSION_ORIGIN,
                store=self.store,
            )
            self.assertFalse(response.accepted)
            self.assertEqual(response.error.code, ErrorCode.POLICY_BLOCKED)

    def test_native_framing_has_no_stdout_logs(self) -> None:
        raw = _request("get_capabilities", {})
        stdin = io.BytesIO(len(raw).to_bytes(4, byteorder=os.sys.byteorder) + raw)
        stdout = io.BytesIO()
        self.assertEqual(run_host(origin=DEVELOPMENT_EXTENSION_ORIGIN, stdin=stdin, stdout=stdout), 0)
        framed = stdout.getvalue()
        size = int.from_bytes(framed[:4], byteorder=os.sys.byteorder)
        self.assertEqual(size, len(framed[4:]))
        response = json.loads(framed[4:].decode("utf-8"))
        self.assertTrue(response["accepted"])
        self.assertEqual(response["status"], "completed")

    def test_oversized_frame_returns_one_rejection(self) -> None:
        stdin = io.BytesIO((MAX_MESSAGE_BYTES + 1).to_bytes(4, byteorder=os.sys.byteorder))
        stdout = io.BytesIO()
        self.assertEqual(run_host(origin=DEVELOPMENT_EXTENSION_ORIGIN, stdin=stdin, stdout=stdout), 2)
        framed = stdout.getvalue()
        size = int.from_bytes(framed[:4], byteorder=os.sys.byteorder)
        response = json.loads(framed[4 : 4 + size].decode("utf-8"))
        self.assertEqual(response["error"]["code"], ErrorCode.NATIVE_MESSAGE_TOO_LARGE.value)

    def test_installer_is_plan_first_user_level_and_reversible(self) -> None:
        uv_path = Path(shutil.which("uv") or "")
        self.assertTrue(uv_path.is_absolute())
        plan = create_plan(
            action="plan",
            browser="chromium",
            home=self.home,
            env=self.env,
            uv_path=uv_path,
        )
        result = execute_plan(plan, confirmation=None)
        self.assertEqual(result["status"], "PLAN_ONLY")
        self.assertFalse(plan.manifest_path.exists())
        self.assertNotIn(str(self.temporary.name), json.dumps(result, sort_keys=True))

        install = create_plan(
            action="install",
            browser="chromium",
            home=self.home,
            env=self.env,
            uv_path=uv_path,
        )
        with self.assertRaises(X2NRuntimeError):
            execute_plan(install, confirmation=None)
        installed = execute_plan(install, confirmation=INSTALL_CONFIRMATION)
        self.assertEqual(installed["status"], "INSTALLED")
        self.assertEqual(stat.S_IMODE(install.launcher_path.stat().st_mode), 0o700)
        self.assertEqual(stat.S_IMODE(install.manifest_path.stat().st_mode), 0o600)
        launcher = install.launcher_path.read_text(encoding="utf-8")
        self.assertIn("exec /usr/bin/env -i", launcher)
        self.assertIn("PYTHONNOUSERSITE=1", launcher)
        manifest = json.loads(install.manifest_path.read_text(encoding="utf-8"))
        self.assertEqual(manifest["name"], HOST_NAME)
        self.assertEqual(manifest["allowed_origins"], [DEVELOPMENT_EXTENSION_ORIGIN])
        self.assertNotIn("*", json.dumps(manifest, sort_keys=True))

        uninstall = create_plan(
            action="uninstall",
            browser="chromium",
            home=self.home,
            env={},
        )
        original_launcher = install.launcher_path.read_text(encoding="utf-8")
        install.launcher_path.write_text(original_launcher + "# tampered\n", encoding="utf-8")
        install.launcher_path.chmod(0o700)
        with self.assertRaises(X2NRuntimeError):
            execute_plan(uninstall, confirmation=UNINSTALL_CONFIRMATION)
        install.launcher_path.write_text(original_launcher, encoding="utf-8")
        install.launcher_path.chmod(0o700)
        with self.assertRaises(X2NRuntimeError):
            execute_plan(uninstall, confirmation=None)
        removed = execute_plan(uninstall, confirmation=UNINSTALL_CONFIRMATION)
        self.assertEqual(removed["status"], "UNINSTALLED")
        self.assertFalse(uninstall.manifest_path.exists())
        self.assertFalse(uninstall.launcher_path.exists())

    def test_installer_cleans_partial_staging_and_preserves_previous_runtime(self) -> None:
        uv_path = Path(shutil.which("uv") or "")
        install = create_plan(
            action="install",
            browser="chromium",
            home=self.home,
            env=self.env,
            uv_path=uv_path,
        )

        def fail_after_partial_venv(command: list[str], *, env: dict[str, str]) -> None:
            del env
            staging = Path(command[-1])
            staging.mkdir(parents=True)
            (staging / "partial").write_text("synthetic", encoding="utf-8")
            raise X2NRuntimeError(ErrorCode.DEPENDENCY_MISSING, "synthetic provision failure")

        with mock.patch(
            "x2n_companion.native_host_installer._run_provision",
            side_effect=fail_after_partial_venv,
        ):
            with self.assertRaises(X2NRuntimeError):
                execute_plan(install, confirmation=INSTALL_CONFIRMATION)
        self.assertFalse(install.runtime_path.exists())
        self.assertFalse(install.launcher_path.exists())
        self.assertFalse(install.manifest_path.exists())
        self.assertEqual(list(install.runtime_path.parent.glob(".runtime.x2n-*")), [])

        execute_plan(install, confirmation=INSTALL_CONFIRMATION)
        runtime_python = install.runtime_path / "bin/python"
        previous_runtime_hash = canonical_json_sha256(
            {"python": runtime_python.read_bytes().hex()}
        )
        with mock.patch(
            "x2n_companion.native_host_installer._run_provision",
            side_effect=fail_after_partial_venv,
        ):
            with self.assertRaises(X2NRuntimeError):
                execute_plan(install, confirmation=INSTALL_CONFIRMATION)
        self.assertEqual(
            canonical_json_sha256({"python": runtime_python.read_bytes().hex()}),
            previous_runtime_hash,
        )
        self.assertEqual(list(install.runtime_path.parent.glob(".runtime.x2n-*")), [])

        previous_launcher = install.launcher_path.read_text(encoding="utf-8")
        previous_manifest = install.manifest_path.read_text(encoding="utf-8")
        real_replace = os.replace
        manifest_commit_failed = False

        def fail_manifest_commit(source: Any, destination: Any) -> None:
            nonlocal manifest_commit_failed
            if Path(destination) == install.manifest_path and not manifest_commit_failed:
                manifest_commit_failed = True
                raise OSError("synthetic manifest commit failure")
            real_replace(source, destination)

        with mock.patch(
            "x2n_companion.native_host_installer.os.replace",
            side_effect=fail_manifest_commit,
        ):
            with self.assertRaises(X2NRuntimeError):
                execute_plan(install, confirmation=INSTALL_CONFIRMATION)
        self.assertEqual(
            canonical_json_sha256({"python": runtime_python.read_bytes().hex()}),
            previous_runtime_hash,
        )
        self.assertEqual(install.launcher_path.read_text(encoding="utf-8"), previous_launcher)
        self.assertEqual(install.manifest_path.read_text(encoding="utf-8"), previous_manifest)
        self.assertEqual(list(install.runtime_path.parent.glob(".runtime.x2n-*")), [])
        self.assertEqual(list(install.manifest_path.parent.glob(".com.linzecolin.x2n.json.x2n-*")), [])

    def test_installer_refuses_unowned_files_before_provisioning(self) -> None:
        uv_path = Path(shutil.which("uv") or "")
        install = create_plan(
            action="install",
            browser="chromium",
            home=self.home,
            env=self.env,
            uv_path=uv_path,
        )
        install.launcher_path.parent.mkdir(parents=True)
        install.launcher_path.write_text("unowned", encoding="utf-8")
        with mock.patch("x2n_companion.native_host_installer._run_provision") as provision:
            with self.assertRaises(X2NRuntimeError):
                execute_plan(install, confirmation=INSTALL_CONFIRMATION)
        provision.assert_not_called()

        install.launcher_path.unlink()
        install.manifest_path.parent.mkdir(parents=True, exist_ok=True)
        install.manifest_path.write_text("{}", encoding="utf-8")
        with mock.patch("x2n_companion.native_host_installer._run_provision") as provision:
            with self.assertRaises(X2NRuntimeError):
                execute_plan(install, confirmation=INSTALL_CONFIRMATION)
        provision.assert_not_called()

        install.manifest_path.unlink()
        residual = install.runtime_path.parent / ".runtime.x2n-staging-synthetic"
        residual.mkdir()
        with mock.patch("x2n_companion.native_host_installer._run_provision") as provision:
            with self.assertRaises(X2NRuntimeError):
                execute_plan(install, confirmation=INSTALL_CONFIRMATION)
        provision.assert_not_called()


if __name__ == "__main__":
    unittest.main()
