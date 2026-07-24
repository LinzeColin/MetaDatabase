"""Governance guard for ADP v1.2 S4.2 mobile four-tab candidate."""

from __future__ import annotations

import hashlib
import json
import re
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
ADP = ROOT / "arxiv-daily-push"
LIVE = ADP / "deploy/cloudflare/worker_cloud.js"
PATCH_01 = ADP / "deploy/cloudflare/v1_2/patches/01_human_language_fail_closed.patch"
PATCH_02 = ADP / "deploy/cloudflare/v1_2/patches/02_mobile_four_tab_nav.patch"
VERIFIER = ADP / "tools/verify_mobile_four_tab_nav.mjs"
CONTRACT = ADP / "docs/pursuing_goal/v1_2/RUN_CONTRACT_05_MOBILE_FOUR_TAB_NAV.md"
TASK_GRAPH = ADP / "docs/pursuing_goal/v1_2/TASK_GRAPH.yaml"
MANIFEST = ADP / "docs/pursuing_goal/v1_2/MANIFEST.yaml"

EXPECTED_LIVE_FILE_SHA256 = "319178f05490588701c10c40fd8dad653d4b58e35c7acbfe1224f7282a20a196"
EXPECTED_PATCH_01_SHA256 = "3f323220cad779d353e0b653d6edfdbd94292433aa8306f9045f9badcda8e9cf"
EXPECTED_S4_1_BLOB = "9ff676970c20369ca562aa8a9639016fa08bb1c7"
EXPECTED_CANDIDATE_BLOB = "461fb1a225c0a8826cf0647181a9969a53618c3a"
EXPECTED_BUILD = "a98b4c957f30"
EXPECTED_SOURCE_SHA256 = "a98b4c957f304600da1c95263c4232719ffaebf52cc3ff4bc9e3fd1910ac79c4"
EXPECTED_MOBILE_NAV = (
    "const MOBILE_NAV = [['/', '今天'], ['/review', '队列'], "
    "['/radar', '雷达'], ['/system', '系统']];"
)
EXPECTED_DESKTOP_NAV = (
    "const NAV = [['/', '今天'], ['/review', '复习'], ['/radar', '前沿雷达'], "
    "['/watchlist', '关注'], ['/library', '知识库'], ['/system', '系统']];"
)
NEGATIVE_CONTROL_NAMES = (
    "删除 mobile nav",
    "加入第五标签",
    "移动标签错序或改名",
    "移动 href 错配",
    "mobile 暴露 desktop nav",
    "breakpoint 回退到 640px",
    "点击高度低于 44px",
    "注入横向 overflow",
    "桌面导航被压成四项",
    "主题 desktop nav mode 被破坏",
)


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def materialize() -> tuple[str, str, str]:
    with tempfile.TemporaryDirectory(prefix="adp-s4-2-governance-") as raw:
        root = Path(raw)
        worker = root / "arxiv-daily-push/deploy/cloudflare/worker_cloud.js"
        worker.parent.mkdir(parents=True)
        shutil.copyfile(LIVE, worker)
        first = subprocess.run(
            ["git", "apply", "--unsafe-paths", str(PATCH_01)],
            cwd=root,
            capture_output=True,
            text=True,
            timeout=30,
        )
        if first.returncode:
            raise AssertionError(f"S4.1 patch failed:\n{first.stdout}\n{first.stderr}")
        s4_1_blob = subprocess.check_output(
            ["git", "hash-object", str(worker)], text=True
        ).strip()
        second = subprocess.run(
            ["git", "apply", "--unidiff-zero", "--unsafe-paths", str(PATCH_02)],
            cwd=root,
            capture_output=True,
            text=True,
            timeout=30,
        )
        if second.returncode:
            raise AssertionError(f"S4.2 patch failed:\n{second.stdout}\n{second.stderr}")
        candidate_blob = subprocess.check_output(
            ["git", "hash-object", str(worker)], text=True
        ).strip()
        return worker.read_text(encoding="utf-8"), s4_1_blob, candidate_blob


class ADPMobileFourTabNavTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.live = LIVE.read_text(encoding="utf-8")
        cls.patch = PATCH_02.read_text(encoding="utf-8")
        cls.verifier = VERIFIER.read_text(encoding="utf-8")
        cls.contract = CONTRACT.read_text(encoding="utf-8")
        cls.candidate, cls.s4_1_blob, cls.candidate_blob = materialize()

    def test_canonical_worker_remains_sealed(self) -> None:
        self.assertEqual(sha256(LIVE), EXPECTED_LIVE_FILE_SHA256)
        self.assertEqual(sha256(PATCH_01), EXPECTED_PATCH_01_SHA256)
        self.assertIn("build_id: 'c2ccc1fd01ec'", self.live)
        self.assertNotIn("MOBILE_NAV", self.live)

    def test_patch_chain_is_exact_and_build_stamp_reproduces(self) -> None:
        self.assertEqual(self.s4_1_blob, EXPECTED_S4_1_BLOB)
        self.assertEqual(self.candidate_blob, EXPECTED_CANDIDATE_BLOB)
        match = re.search(
            r"build_id: '([0-9a-f]{12})', source_sha256: '([0-9a-f]{64})'",
            self.candidate,
        )
        self.assertIsNotNone(match)
        build_id, source_sha = match.groups()
        zeroed = self.candidate.replace(
            f"build_id: '{build_id}'", f"build_id: '{'0' * 12}'"
        ).replace(
            f"source_sha256: '{source_sha}'", f"source_sha256: '{'0' * 64}'"
        )
        actual = hashlib.sha256(zeroed.encode()).hexdigest()
        self.assertEqual(build_id, EXPECTED_BUILD)
        self.assertEqual(source_sha, EXPECTED_SOURCE_SHA256)
        self.assertEqual(actual, source_sha)
        self.assertEqual(build_id, source_sha[:12])

    def test_mobile_and_desktop_navigation_contract_is_pinned(self) -> None:
        self.assertIn(EXPECTED_MOBILE_NAV, self.candidate)
        self.assertIn(EXPECTED_DESKTOP_NAV, self.candidate)
        self.assertIn("@media(max-width:779px)", self.candidate)
        self.assertNotIn("@media(max-width:640px)", self.candidate)
        self.assertIn("grid-template-columns:repeat(4,minmax(0,1fr))", self.candidate)
        self.assertIn("min-height:48px", self.candidate)
        self.assertIn("aria-label=\"${label}\"", self.candidate)
        self.assertEqual(
            self.candidate.count(
                "${navLinks('nav-mobile', page, MOBILE_NAV, '移动端主导航')}"
            ),
            1,
        )
        self.assertIn(
            "const THEME_NAV = { warm: 'sidebar', minimal: 'topbar', fresh: 'topbar', "
            "techno: 'dock', cosmos: 'dock', forest: 'sidebar' };",
            self.candidate,
        )

    def test_contract_and_taskpack_bind_only_s4_2(self) -> None:
        graph = TASK_GRAPH.read_text(encoding="utf-8")
        manifest = MANIFEST.read_text(encoding="utf-8")
        self.assertIn("task_id: ADP-V12-S4-T002", graph)
        self.assertIn("run_contract: RUN_CONTRACT_05_MOBILE_FOUR_TAB_NAV.md", graph)
        self.assertIn("RUN_CONTRACT_05_MOBILE_FOUR_TAB_NAV.md", manifest)
        for pin in (
            "ACC-V12-S4-003",
            "F-006",
            "375×812",
            "TST-V12-MOBILE-NAV-SIX-THEMES",
            "TST-V12-DESKTOP-NAV-REGRESSION",
            "--unidiff-zero",
            "S4.3",
            "canonical `deploy/cloudflare/worker_cloud.js`",
        ):
            self.assertIn(pin, self.contract)

    def test_negative_controls_are_explicit_and_exact(self) -> None:
        for name in NEGATIVE_CONTROL_NAMES:
            self.assertEqual(
                self.verifier.count(f"'{name}'"),
                1,
                f"negative control must be declared exactly once: {name}",
            )
        self.assertEqual(self.verifier.count("await runNegative("), len(NEGATIVE_CONTROL_NAMES))

    @unittest.skipUnless(
        shutil.which("node"),
        "Node unavailable; Chrome behavioural verifier is mandatory in S4.2 acceptance environment",
    )
    def test_system_chrome_behavioural_verifier_passes(self) -> None:
        with tempfile.TemporaryDirectory(prefix="adp-s4-2-browser-evidence-") as raw:
            evidence_dir = Path(raw)
            result = subprocess.run(
                ["node", str(VERIFIER), "--evidence-dir", str(evidence_dir)],
                cwd=ROOT,
                capture_output=True,
                text=True,
                timeout=120,
            )
            self.assertEqual(
                result.returncode,
                0,
                f"STDOUT:\n{result.stdout}\nSTDERR:\n{result.stderr}",
            )
            self.assertEqual(result.stdout.count("PASS 负控:"), len(NEGATIVE_CONTROL_NAMES))
            self.assertIn('"mobile_theme_count": 6', result.stdout)
            self.assertIn('"desktop_theme_count": 6', result.stdout)
            self.assertIn('"boundary_case_count": 12', result.stdout)
            self.assertIn('"active_route_count": 4', result.stdout)
            self.assertIn('"screenshot_count": 12', result.stdout)
            self.assertIn('"browser_errors": 0', result.stdout)
            self.assertIn('"verdict": "PASS"', result.stdout)

            report_path = evidence_dir / "mobile-four-tab-report.json"
            report = json.loads(report_path.read_text(encoding="utf-8"))
            screenshot_files = sorted(evidence_dir.glob("*.png"))
            self.assertEqual(report["verdict"], "PASS")
            self.assertEqual(len(report["screenshots"]), 12)
            self.assertEqual(len(screenshot_files), 12)
            self.assertTrue(all(not Path(item["file"]).is_absolute() for item in report["screenshots"]))
            self.assertEqual(
                sorted(item["file"] for item in report["screenshots"]),
                sorted(path.name for path in screenshot_files),
            )


if __name__ == "__main__":
    unittest.main()
