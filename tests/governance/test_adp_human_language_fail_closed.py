#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""S4.1 guard: English papers fail closed into honest Chinese, never English-as-explanation."""

import pathlib
import re
import shutil
import subprocess
import unittest


ROOT = pathlib.Path(__file__).resolve().parents[2]
WORKER = ROOT / "arxiv-daily-push" / "deploy" / "cloudflare" / "worker_cloud.js"
PATCH = ROOT / "arxiv-daily-push" / "deploy" / "cloudflare" / "v1_2" / "patches" / "01_human_language_fail_closed.patch"
VERIFIER = ROOT / "arxiv-daily-push" / "tools" / "verify_human_language_fail_closed.mjs"
CONTRACT = ROOT / "arxiv-daily-push" / "docs" / "pursuing_goal" / "v1_2" / "RUN_CONTRACT_04_HUMAN_LANGUAGE_FAIL_CLOSED.md"


class TestAdpHumanLanguageFailClosed(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.src = WORKER.read_text(encoding="utf-8")
        cls.patch = PATCH.read_text(encoding="utf-8")

    def test_run_contract_and_executable_verifier_exist(self):
        self.assertTrue(CONTRACT.is_file())
        body = CONTRACT.read_text(encoding="utf-8")
        self.assertIn("ACC-V12-S4-001..002", body)
        self.assertIn("unsupported_translation_claim", body)
        self.assertTrue(VERIFIER.is_file())

    def test_candidate_patch_pins_fail_closed_content_mechanism(self):
        required = (
            "ENGLISH_SOURCE_NO_RELIABLE_ZH",
            "needsEnglishHumanLanguageFallback",
            "buildEnglishFailClosedLesson",
            "content_contract.no_reliable_zh",
            "data-claim-state",
            "originalSourceHTML",
            "查看英文原文标题与摘要（默认折叠）",
        )
        for value in required:
            self.assertIn(value, self.patch)
        self.assertRegex(
            self.patch,
            r"const sections = failClosed \? buildEnglishFailClosedLesson\(item\) : JSON\.parse\(lesson\.sections_json\)",
            "English item can still trust legacy cn_lessons instead of rebuilding the safe fallback",
        )

    def test_all_lesson_render_calls_supply_item_context(self):
        calls = re.findall(r"lessonHTML\((.*?)\)", self.patch)
        self.assertGreaterEqual(len(calls), 4)
        # Exact call-site pins are easier to audit than pretending nested-regex parsing is a JS parser.
        for pin in (
            "lessonHTML(lesson, item)",
            "lessonHTML(stored || { sections_json: JSON.stringify(buildLesson(dueRow)) }, dueRow)",
        ):
            self.assertIn(pin, self.patch)

    def test_item_today_review_hide_english_source_in_collapsed_region(self):
        self.assertIn("${englishFallback ? originalSourceHTML(item) : ''}", self.patch)
        self.assertIn("if (lesson || englishFallback)", self.patch)
        self.assertIn("${originalSourceHTML(item)}", self.patch)
        self.assertIn("${englishFallback ? originalSourceHTML(dueRow) : ''}", self.patch)
        self.assertIn("needsEnglishHumanLanguageFallback(r) ? '英文论文复习项'", self.patch)
        # `<details open>` would defeat the product contract; selector CSS may mention [open], renderer may not.
        start = self.patch.find("+function originalSourceHTML(item) {")
        end = self.patch.find(" function itemListHTML", start)
        self.assertGreaterEqual(start, 0)
        self.assertGreater(end, start)
        self.assertNotRegex(self.patch[start:end], r"<details\s+open(?:\s|>)")

    def test_live_worker_remains_the_sealed_production_subject(self):
        self.assertIn("build_id: 'c2ccc1fd01ec'", self.src)
        self.assertNotIn("ENGLISH_SOURCE_NO_RELIABLE_ZH", self.src)
        self.assertTrue(PATCH.is_file())

    def test_negative_controls_are_load_bearing(self):
        body = VERIFIER.read_text(encoding="utf-8")
        for name in (
            "旧模板把英文摘要放进人话版",
            "旧存储英文与伪造中文 claim 直出",
            "原文 details 被默认展开",
            "移除 UNKNOWN 状态",
            "把未生成推断改成 unsupported claim",
        ):
            self.assertIn(name, body)

    @unittest.skipUnless(shutil.which("node"), "Node unavailable; behavioural verifier is mandatory in S4.1 acceptance environment")
    def test_behavioural_verifier_passes(self):
        result = subprocess.run(
            ["node", str(VERIFIER)], cwd=str(ROOT), capture_output=True, text=True, timeout=60
        )
        self.assertEqual(result.returncode, 0, f"STDOUT:\n{result.stdout}\nSTDERR:\n{result.stderr}")
        self.assertIn("ACC-V12-S4-001..002", result.stdout)
        self.assertEqual(result.stdout.count("✅ 负控:"), 5)


if __name__ == "__main__":
    unittest.main()
