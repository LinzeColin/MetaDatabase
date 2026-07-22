from __future__ import annotations

import copy
import importlib.util
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "verify_stage_1_review",
    PROJECT_ROOT / "scripts/verify_stage_1_review.py",
)
assert SPEC and SPEC.loader
VERIFY = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = VERIFY
SPEC.loader.exec_module(VERIFY)


class Stage1ReviewTests(unittest.TestCase):
    def test_review_contract_dag_gate_and_findings_are_consistent(self) -> None:
        checks = (
            VERIFY.validate_review_documents(),
            VERIFY.validate_task_dag_and_state(),
            VERIFY.validate_gate_fact(),
            VERIFY.validate_findings(),
            VERIFY.validate_review_scope(),
        )
        self.assertEqual([check.status for check in checks], ["PASS"] * len(checks))

    def test_taskpack_delta_rejects_a_new_review_task(self) -> None:
        current = VERIFY._load_yaml(VERIFY.TASKPACK)
        baseline = VERIFY._load_yaml_at(VERIFY.REVIEW_BASE_COMMIT, VERIFY.TASKPACK)
        mutated = copy.deepcopy(current)
        mutated["tasks"].append({"id": "TSK.x2n.synthetic.review.escape", "stage": "STG.X2N.1"})
        with self.assertRaises(VERIFY.ReviewError):
            VERIFY._validate_taskpack_review_delta(mutated, baseline)

    def test_pr_merge_uses_only_the_foundation_descended_parent(self) -> None:
        merge = "a" * 40
        main_parent = "b" * 40
        review_parent = "c" * 40
        allowed_path = "xhs-douyin-2notion/scripts/verify_stage_1_review.py"
        with (
            patch.object(VERIFY, "_git", return_value=f"{merge} {main_parent} {review_parent}"),
            patch.object(VERIFY, "_is_ancestor", side_effect=lambda _ancestor, value: value == review_parent),
        ):
            self.assertEqual(VERIFY._logical_review_head(), review_parent)

        def merge_scope_git(args: list[str], *_args: object, **_kwargs: object) -> str:
            if args == ["rev-parse", "HEAD"]:
                return merge
            if args[-3:] == ["diff", "--name-only", f"{VERIFY.REVIEW_BASE_COMMIT}..{review_parent}"]:
                return allowed_path
            if args[-3:] == ["ls-files", "--others", "--exclude-standard"]:
                return ""
            self.fail(f"unexpected merge-scope git command: {args}")

        with (
            patch.object(VERIFY, "_logical_review_head", return_value=review_parent),
            patch.object(VERIFY, "_git", side_effect=merge_scope_git),
        ):
            self.assertEqual(VERIFY._changed_review_paths(), {allowed_path})

    def test_foundation_receipts_are_frozen_at_review_base(self) -> None:
        check = VERIFY.validate_foundation_evidence()
        self.assertEqual(check.status, "PASS")
        self.assertEqual(check.details["frozen_receipts"], 5)
        self.assertEqual(check.details["rewritten_receipts"], 0)

    def test_blocking_execution_identity_is_exact_and_ordered(self) -> None:
        rows = VERIFY._expected_blocking_results()
        self.assertEqual(len(rows), 24)
        self.assertEqual(len({row["label"] for row in rows}), 24)
        self.assertEqual(rows[0]["label"], "format_r1")
        self.assertEqual(rows[-1]["label"], "extension_native_e2e_r2")
        mutated = [dict(row) for row in rows]
        mutated[-1]["gate"] = "unexpected_gate"
        self.assertNotEqual(mutated, rows)

    def test_duplicate_json_key_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory(prefix="x2n-g1-json-") as value:
            path = Path(value) / "duplicate.json"
            path.write_text('{"status":"PASS","status":"FAIL"}\n', encoding="utf-8")
            with self.assertRaises(VERIFY.ReviewError):
                VERIFY._load_json(path)

    def test_history_scanner_detects_seeded_sensitive_shapes(self) -> None:
        secret = "github" + "_pat_" + "A" * 24
        local_path = "/" + "Users/example/private/item"
        cdn = "https://" + "video.ali" + "cdn.example/item"
        findings = VERIFY.scan_text("\n".join((secret, local_path, cdn)), "synthetic.txt")
        self.assertEqual(
            {finding.code for finding in findings},
            {"cdn.platform_media_url", "private.local_absolute_path", "secret.github_token_shape"},
        )

    def test_g1_does_not_overstate_remote_or_real_execution(self) -> None:
        fact = json.loads(VERIFY.G1_FACT.read_text(encoding="utf-8"))
        self.assertEqual(fact["gate_status"], "pass")
        self.assertEqual(fact["remote_ci_execution"], "pending_post_g1_upload")
        self.assertTrue(fact["stage_2_authorized"])
        for field in ("real_account_execution", "platform_calls", "notion_calls", "model_calls", "media_processing"):
            self.assertEqual(fact[field], "not_run")

    def test_runtime_cli_does_not_embed_dynamic_stage_gate(self) -> None:
        source = (PROJECT_ROOT / "apps/companion/src/x2n_companion/runtime_cli.py").read_text(encoding="utf-8")
        self.assertNotIn('"stage_gate"', source)
        self.assertIn('"acceptance_scope": "FOUNDATION_003_LOCAL_STORE"', source)


if __name__ == "__main__":
    unittest.main()
