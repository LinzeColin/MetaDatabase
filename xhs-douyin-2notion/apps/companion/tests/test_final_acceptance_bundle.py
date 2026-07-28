from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from x2n_companion.final_acceptance_bundle import (
    BUNDLE_FILENAMES,
    FinalAcceptanceBundleError,
    build_final_acceptance_bundle,
    verify_final_acceptance_bundle,
)


def _receipt() -> dict[str, object]:
    external_scopes = (
        "bilibili_selected_collection",
        "kuaishou_selected_collection",
        "weibo_selected_collection",
        "taobao_selected_collection",
    )
    return {
        "artifact": {
            "artifact_sha256": "a" * 64,
            "runtime_data_files": 0,
            "source_only_artifact": True,
        },
        "artifact_scan": {
            "allowlist_findings": 0,
            "artifact_sha256": "b" * 64,
            "member_count": 12,
            "runtime_data_files": 0,
            "status": "PASS",
        },
        "boundaries": {
            "external_disabled_scope_count": 4,
            "model_mode": "disabled",
            "private_manifest_item_count": 80,
            "private_manifest_scope_count": 4,
        },
        "external_gates": [
            {
                "feature_flag": "disabled",
                "live_support_claim": False,
                "platform_calls": 0,
                "reason_code": "BLOCKED_AUTH",
                "scope_id": scope_id,
                "status": "PASS_DISABLED_EXTERNAL_GATE",
            }
            for scope_id in external_scopes
        ],
        "knowledge_assets": {
            "markdown_content_count": 80,
            "markdown_library_sha256": "e" * 64,
            "markdown_renderer_version": "1.1.0",
            "notion_mode": "DISABLED_OWNER_INPUT",
            "notion_platform_calls": 0,
            "private_durability_manifest_sha256": "f" * 64,
        },
        "go_live": {
            "baseline_hash": "c" * 64,
            "owner_mvp_baseline_relations": 80,
            "rollback_rehearsed": True,
            "sidepanel_native_handshake": "PASS",
        },
        "native_host": {
            "native_host_release_bound": True,
            "release_artifact_sha256": "a" * 64,
        },
        "phase": "PH.X2N.6.5",
        "release_source": {"commit": "d" * 40, "tag": "v0.0.0.1"},
        "release_version": "v0.0.0.1",
        "schema_version": "1.0",
        "status": "PASS_OWNER_MVP_DIRECT_RELEASE_CORE",
        "task_id": "TSK.x2n.assurance.005",
    }


class FinalAcceptanceBundleTests(unittest.TestCase):
    def test_deterministic_aggregate_bundle_is_bound_to_receipt(self) -> None:
        receipt = _receipt()
        files, digest = build_final_acceptance_bundle(receipt)
        receipt["final_acceptance_bundle_sha256"] = digest
        self.assertEqual(tuple(files), BUNDLE_FILENAMES)
        self.assertNotIn("/" + "Users/", "".join(files.values()))
        self.assertNotIn("github" + "_pat_", "".join(files.values()))
        with tempfile.TemporaryDirectory(prefix="x2n-a005-bundle-") as temporary:
            destination = Path(temporary) / "FINAL_ACCEPTANCE_BUNDLE"
            destination.mkdir()
            for name, value in files.items():
                (destination / name).write_text(value, encoding="utf-8")
            verified = verify_final_acceptance_bundle(destination, receipt)
        self.assertEqual(verified["bundle_sha256"], digest)
        self.assertEqual(verified["bundle_file_count"], len(BUNDLE_FILENAMES))

    def test_checksum_or_release_note_tamper_fails_closed(self) -> None:
        receipt = _receipt()
        files, digest = build_final_acceptance_bundle(receipt)
        receipt["final_acceptance_bundle_sha256"] = digest
        with tempfile.TemporaryDirectory(prefix="x2n-a005-bundle-") as temporary:
            destination = Path(temporary) / "FINAL_ACCEPTANCE_BUNDLE"
            destination.mkdir()
            for name, value in files.items():
                (destination / name).write_text(value, encoding="utf-8")
            (destination / "release_notes.md").write_text("tampered\n", encoding="utf-8")
            with self.assertRaises(FinalAcceptanceBundleError):
                verify_final_acceptance_bundle(destination, receipt)


if __name__ == "__main__":
    unittest.main()
