#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Regression guards for ADP's canonical MetaDatabase migration contract.

The predecessor test guarded CodexProject's retired repository-hygiene policy.
MetaDatabase consumes governance from LinzeColin/Governance and intentionally
does not carry that policy. These five tests preserve the original intent --
detecting silent loss or drift of ADP's large/history-bearing artifacts --
against the current repository layout and dual-plane contract.
"""

import hashlib
import pathlib
import unittest


ROOT = pathlib.Path(__file__).resolve().parents[2]
ADP = ROOT / "arxiv-daily-push"
BUNDLE = ROOT / "FINAL_ACCEPTANCE_BUNDLE"
MANIFESTS = ROOT / "governance" / "run_manifests"


def _tree_digest(paths):
    """Hash each path label plus its content hash in deterministic order."""
    digest = hashlib.sha256()
    files = sorted(path for path in paths if path.is_file())
    for path in files:
        digest.update(path.relative_to(ROOT).as_posix().encode("utf-8"))
        digest.update(b"\0")
        digest.update(hashlib.sha256(path.read_bytes()).digest())
    return len(files), digest.hexdigest()


class TestAdpCanonicalGovernanceOids(unittest.TestCase):
    def test_root_contract_names_the_canonical_migrated_location(self):
        agents = (ROOT / "AGENTS.md").read_text(encoding="utf-8")
        readme = (ROOT / "README.md").read_text(encoding="utf-8")

        self.assertIn("ADP（`arxiv-daily-push/`）已于 2026-07-20 迁入", agents)
        self.assertIn("canonical 交接入口是 `arxiv-daily-push/docs/HANDOFF.md`", agents)
        self.assertIn("禁止从历史、\n  备份或任务包恢复", agents)
        self.assertIn("| ADP | ✅ 已迁入 | canonical 路径 `arxiv-daily-push/`", readme)

    def test_current_dual_plane_registers_adp_without_retired_root_policy(self):
        workflow = (ROOT / ".github/workflows/dual-plane.yml").read_text(encoding="utf-8")

        self.assertIn('"arxiv-daily-push"', workflow)
        self.assertIn("check_dual_plane_ci.py", workflow)
        self.assertFalse((ROOT / ".github/workflows/project-governance.yml").exists())
        self.assertFalse((ROOT / "governance/repository_hygiene_policy.json").exists())
        self.assertFalse((ROOT / "scripts/generate_governance_dashboard.py").exists())

    def test_final_acceptance_bundle_is_complete_and_content_identical(self):
        count, digest = _tree_digest(BUNDLE.rglob("*"))

        self.assertEqual(count, 30)
        self.assertEqual(digest, "fba1d24b53d877c3f0dace82b67f017b70154eb11ff4b88193a2a4537e53d776")

    def test_adp_run_manifests_are_complete_and_content_identical(self):
        paths = list(MANIFESTS.glob("ADP-*"))
        all_files = [path for path in MANIFESTS.glob("*") if path.is_file()]
        count, digest = _tree_digest(paths)

        self.assertEqual(count, 424)
        self.assertEqual(digest, "b268aedd2d9e712bd89fcd6abf7b7609b787d31738dd4d8e70c3611ba2cab64d")
        self.assertEqual({path.name for path in all_files}, {path.name for path in paths})

    def test_owner_frontend_archive_remains_exact_and_tracked(self):
        archive = ADP / "docs/design/前端呈现基线_v1/_原始存档/ADP主题动效v1.1.zip"

        self.assertTrue(archive.is_file())
        self.assertEqual(archive.stat().st_size, 6106)
        self.assertEqual(
            hashlib.sha256(archive.read_bytes()).hexdigest(),
            "253f7bf6881bd2df377d6a286670f1441b3c093b94de34c7b01f1406dfda91a7",
        )


if __name__ == "__main__":
    unittest.main()
