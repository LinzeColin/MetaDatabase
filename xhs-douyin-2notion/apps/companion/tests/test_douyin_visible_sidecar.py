from __future__ import annotations

import socket
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from x2n_contracts import ErrorCode

from x2n_companion.douyin_visible_sidecar import (
    PROVISION_CONFIRMATION,
    OwnerPrivateVisibleSidecarClient,
    VisibleBatchRequest,
    provision_owner_private_visible_sidecar,
)
from x2n_companion.runtime import RuntimePaths, X2NRuntimeError


PROJECT_ROOT = Path(__file__).resolve().parents[3]


def _visible_batch() -> dict[str, object]:
    return {
        "batch": {
            "automatic_scroll": False,
            "completion_signal": "bounded_limit_reached",
            "explicit_owner_action": True,
            "visible_card_count": 20,
        },
        "code": None,
        "errors": [],
        "items": [
            {"content_id": f"sidecar-visible-{index:02d}", "content_type": "video", "title": None}
            for index in range(20)
        ],
        "platform": "douyin",
        "schema_version": "1.0",
        "status": "ready",
    }


def _available_loopback_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as listener:
        listener.bind(("127.0.0.1", 0))
        return int(listener.getsockname()[1])


class DouyinVisibleSidecarTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        destination = Path(self.temporary.name) / "MediaCrawler"
        destination.mkdir(mode=0o700)
        destination.chmod(0o700)
        self.paths = RuntimePaths.from_values(
            str(destination / "xhs-douyin-2notion"),
            str(destination),
            repository_root=PROJECT_ROOT,
            create=True,
        )

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def test_provisioned_clean_room_sidecar_binds_one_visible_batch_and_exits(self) -> None:
        build = provision_owner_private_visible_sidecar(self.paths, confirmation=PROVISION_CONFIRMATION)
        batch = OwnerPrivateVisibleSidecarClient(
            self.paths,
            expected_build=build,
            port=_available_loopback_port(),
        ).fetch_owner_batch(
            VisibleBatchRequest(mode="favorites", sequence=0, visible_batch=_visible_batch()),
        )[1]
        self.assertEqual(batch.mode, "favorites")
        self.assertEqual(batch.status, "ready")
        self.assertEqual(batch.completion_signal, "bounded_limit_reached")
        self.assertEqual(len(batch.items), 20)
        self.assertEqual(batch.items[0].content_id, "sidecar-visible-00")

    def test_invalid_visible_batch_stops_before_any_private_sidecar_process_starts(self) -> None:
        value = _visible_batch()
        items = value["items"]
        assert isinstance(items, list)
        item = items[0]
        assert isinstance(item, dict)
        item["title"] = "https://unsafe.example/"
        with self.assertRaises(X2NRuntimeError) as blocked:
            VisibleBatchRequest(mode="likes", sequence=0, visible_batch=value)
        self.assertEqual(blocked.exception.code, ErrorCode.POLICY_BLOCKED)
        self.assertFalse(self.paths.douyin_sidecar_bundle_directory.exists())

    def test_provision_requires_explicit_confirmation(self) -> None:
        with self.assertRaises(X2NRuntimeError) as blocked:
            provision_owner_private_visible_sidecar(self.paths, confirmation="wrong")
        self.assertEqual(blocked.exception.code, ErrorCode.POLICY_BLOCKED)
        self.assertFalse(self.paths.douyin_sidecar_bundle_directory.exists())

    def test_startup_failure_terminates_the_spawned_sidecar(self) -> None:
        build = provision_owner_private_visible_sidecar(self.paths, confirmation=PROVISION_CONFIRMATION)
        client = OwnerPrivateVisibleSidecarClient(self.paths, expected_build=build, port=_available_loopback_port())
        process = mock.Mock()
        process.poll.return_value = None
        with (
            mock.patch("x2n_companion.douyin_visible_sidecar.subprocess.Popen", return_value=process),
            mock.patch("x2n_companion.douyin_visible_sidecar.select.select", return_value=([], [], [])),
        ):
            with self.assertRaises(X2NRuntimeError) as blocked:
                client._start()
        self.assertEqual(blocked.exception.code, ErrorCode.DEPENDENCY_MISSING)
        process.kill.assert_called_once_with()
        process.wait.assert_called_once_with()
