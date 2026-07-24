#!/usr/bin/env python3
"""Durable positive/negative Oracles for the BSS license-similarity audit."""
from __future__ import annotations

import copy
import importlib.util
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
PROJECT_ROOT = REPO_ROOT / "Stock_Skill/bottleneck-serenity-skill"
SCRIPT = PROJECT_ROOT / "scripts/audit_license_similarity.py"
REPORT = PROJECT_ROOT / "LICENSE_SIMILARITY_AUDIT.json"
ACCEPTANCE = PROJECT_ROOT / "task-pack/04_ACCEPTANCE_VALIDATION_STOP.md"
OWNER_COUNT_DOCS = (
    PROJECT_ROOT / "README.md",
    PROJECT_ROOT / "LICENSE_AND_ATTRIBUTION.md",
    PROJECT_ROOT / "SOURCE_INVENTORY.md",
    PROJECT_ROOT / "RESTORE_AND_VERIFY.md",
)
OWNER_COUNT_MARKER = re.compile(
    r"<!-- CURRENT_LICENSE_TARGET_COUNT=([0-9]+) -->"
)
CANONICAL = (
    PROJECT_ROOT / "task-pack/skill_draft/bottleneck-serenity-skill"
)

SPEC = importlib.util.spec_from_file_location("bss_license_audit", SCRIPT)
MODULE = importlib.util.module_from_spec(SPEC)
assert SPEC and SPEC.loader
sys.modules[SPEC.name] = MODULE
SPEC.loader.exec_module(MODULE)


def run_git(repo: Path, *arguments: str) -> str:
    result = subprocess.run(
        ["git", *arguments],
        cwd=repo,
        text=True,
        capture_output=True,
        check=False,
        env={
            **os.environ,
            "GIT_AUTHOR_NAME": "BSS Audit Fixture",
            "GIT_AUTHOR_EMAIL": "fixture@example.invalid",
            "GIT_COMMITTER_NAME": "BSS Audit Fixture",
            "GIT_COMMITTER_EMAIL": "fixture@example.invalid",
        },
    )
    if result.returncode:
        raise AssertionError(result.stdout + result.stderr)
    return result.stdout.strip()


class LicenseSimilarityAuditTests(unittest.TestCase):
    maxDiff = None

    def test_fixture_freezes_full_history_text_and_count_algorithm(self) -> None:
        with tempfile.TemporaryDirectory(prefix="bss-license-audit-test-") as raw:
            root = Path(raw)
            target = root / "target"
            upstream = root / "upstream"
            target.mkdir()
            upstream.mkdir()
            exact_payload = "Alpha one\nBeta two\nGamma three\nDelta four\n"
            normalized_payload = (
                "One alpha beta gamma delta\n"
                "Two epsilon zeta eta theta\n"
                "Three iota kappa lambda mu\n"
                "Four nu xi omicron pi\n"
            )
            (target / "alpha.txt").write_text(exact_payload, encoding="utf-8")
            (target / "spacing.txt").write_text(normalized_payload, encoding="utf-8")

            run_git(upstream, "init", "-q")
            (upstream / "exact.txt").write_text(exact_payload, encoding="utf-8")
            run_git(upstream, "add", "exact.txt")
            run_git(upstream, "commit", "-q", "-m", "historical exact payload")
            (upstream / "exact.txt").unlink()
            (upstream / "normalized.txt").write_text(
                " One  alpha beta gamma delta \n"
                "Two epsilon   zeta eta theta\n"
                "Three iota kappa lambda mu\n"
                "Four nu xi omicron pi\n",
                encoding="utf-8",
            )
            (upstream / "current.txt").write_text("current text\n", encoding="utf-8")
            (upstream / "nul.bin").write_bytes(b"text\x00payload")
            (upstream / "invalid.bin").write_bytes(b"invalid-utf8-\xff")
            run_git(upstream, "add", "-A")
            run_git(upstream, "commit", "-q", "-m", "eligibility matrix")
            commit = run_git(upstream, "rev-parse", "HEAD")
            spec = MODULE.UpstreamSpec(
                name="fixture/upstream",
                url="",
                commit=commit,
                license_status="NO_LICENSE_FOUND",
                expected_license_paths=(),
            )

            report = MODULE.build_report(
                target,
                (spec,),
                {spec.name: upstream},
                target_label="fixture-target",
            )
            self.assertEqual(report["target"]["file_count"], 2)
            self.assertEqual(
                report["upstreams"][0]["eligible_text_blob_count"], 3
            )
            self.assertEqual(report["upstreams"][0]["nul_rejected_blob_count"], 1)
            self.assertEqual(
                report["upstreams"][0]["non_utf8_rejected_blob_count"], 1
            )
            self.assertEqual(report["summary"]["exact_pair_count"], 1)
            self.assertEqual(
                report["summary"]["normalized_four_line_pair_count"], 2
            )
            self.assertEqual(report["summary"]["token20_pair_count"], 1)
            MODULE.validate_report_targets(
                report,
                target,
                target_label="fixture-target",
                specs=(spec,),
            )

            algorithm_mutant = copy.deepcopy(report)
            algorithm_mutant["algorithm"]["window_lines"] = 3
            with self.assertRaises(MODULE.AuditError):
                MODULE.validate_report_targets(
                    algorithm_mutant,
                    target,
                    target_label="fixture-target",
                    specs=(spec,),
                )

            target_mutant = copy.deepcopy(report)
            target_mutant["target"]["files"][0]["sha256"] = "0" * 64
            with self.assertRaises(MODULE.AuditError):
                MODULE.validate_report_targets(
                    target_mutant,
                    target,
                    target_label="fixture-target",
                    specs=(spec,),
                )

    def test_committed_report_covers_exact_current_canonical_file_set(self) -> None:
        report = MODULE.load_report(REPORT)
        MODULE.validate_report_targets(
            report,
            CANONICAL,
            target_label=MODULE.CANONICAL_RELATIVE.as_posix(),
        )
        current_target_count = len(MODULE.collect_targets(CANONICAL))
        self.assertEqual(report["target"]["file_count"], current_target_count)
        self.assertEqual(
            report["summary"]["target_file_count"],
            current_target_count,
        )
        self.assertEqual(report["summary"]["upstream_repository_count"], 4)
        self.assertEqual(
            report["summary"]["upstream_eligible_text_blob_instances"], 2485
        )
        self.assertEqual(report["summary"]["exact_pair_count"], 0)
        self.assertEqual(report["summary"]["normalized_four_line_pair_count"], 5)
        self.assertEqual(report["summary"]["token20_pair_count"], 1)
        self.assertEqual(report["summary"]["unlicensed_exact_pair_count"], 0)
        self.assertEqual(
            report["summary"]["unlicensed_normalized_four_line_pair_count"], 3
        )
        self.assertEqual(report["summary"]["unlicensed_token20_pair_count"], 0)

        metadata_mutant = copy.deepcopy(report)
        metadata_mutant["upstreams"][1]["commit"] = "0" * 40
        with self.assertRaises(MODULE.AuditError):
            MODULE.validate_report_targets(
                metadata_mutant,
                CANONICAL,
                target_label=MODULE.CANONICAL_RELATIVE.as_posix(),
            )

        summary_mutant = copy.deepcopy(report)
        summary_mutant["summary"]["unlicensed_token20_pair_count"] = 1
        with self.assertRaises(MODULE.AuditError):
            MODULE.validate_report_targets(
                summary_mutant,
                CANONICAL,
                target_label=MODULE.CANONICAL_RELATIVE.as_posix(),
            )

        with tempfile.TemporaryDirectory(prefix="bss-license-target-mutation-") as raw:
            mutated = Path(raw) / "canonical"
            shutil.copytree(CANONICAL, mutated)
            path = mutated / "SKILL.md"
            path.write_text(path.read_text(encoding="utf-8") + "\nmutation\n", encoding="utf-8")
            with self.assertRaises(MODULE.AuditError):
                MODULE.validate_report_targets(
                    report,
                    mutated,
                    target_label=MODULE.CANONICAL_RELATIVE.as_posix(),
                )

    def test_report_is_canonical_json_without_local_clone_paths(self) -> None:
        report = MODULE.load_report(REPORT)
        self.assertEqual(REPORT.read_bytes(), MODULE.serialize_report(report))
        serialized = json.dumps(report, ensure_ascii=False)
        self.assertNotIn("/tmp/", serialized)
        self.assertNotIn("/Users/", serialized)
        self.assertNotIn("\\Users\\", serialized)

    def test_acceptance_oracle_derives_current_target_count_from_report(self) -> None:
        report = MODULE.load_report(REPORT)
        acceptance = ACCEPTANCE.read_text(encoding="utf-8")
        self.assertIn(
            "current exact target 集（计数必须等于 "
            "`LICENSE_SIMILARITY_AUDIT.summary.target_file_count`）",
            acceptance,
        )
        self.assertNotIn("current 39-file exact target", acceptance)
        self.assertEqual(
            report["target"]["file_count"],
            report["summary"]["target_file_count"],
        )

    def test_owner_facing_target_counts_match_committed_report(self) -> None:
        report = MODULE.load_report(REPORT)
        expected = report["summary"]["target_file_count"]
        for path in OWNER_COUNT_DOCS:
            with self.subTest(path=path.name):
                text = path.read_text(encoding="utf-8")
                matches = OWNER_COUNT_MARKER.findall(text)
                self.assertEqual(matches, [str(expected)])
                self.assertIsNone(
                    re.search(r"(?<![0-9])229(?![0-9])", text),
                    f"{path.name} retains the stale target count",
                )


if __name__ == "__main__":
    unittest.main()
