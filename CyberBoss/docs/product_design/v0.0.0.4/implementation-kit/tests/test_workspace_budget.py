#!/usr/bin/env python3
from __future__ import annotations

import importlib.util
import json
import subprocess
import tempfile
import unittest
from pathlib import Path


KIT = Path(__file__).resolve().parents[1]
SCRIPT = KIT / "scripts/workspace_budget.py"
POLICY = KIT / "config/workspace-budget.json"
SPEC = importlib.util.spec_from_file_location("workspace_budget", SCRIPT)
assert SPEC and SPEC.loader
WORKSPACE_BUDGET = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(WORKSPACE_BUDGET)


def usage(
    *,
    workspace: int = 100,
    objects: int = 50,
    worktree: int = 50,
    cache: int = 0,
    available: int = 10 * 1024 * 1024 * 1024,
) -> dict[str, int]:
    return {
        "workspace_bytes": workspace,
        "repository_objects_bytes": objects,
        "worktree_bytes": worktree,
        "cache_bytes": cache,
        "host_available_bytes": available,
    }


class WorkspaceBudgetTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.policy = WORKSPACE_BUDGET.load_policy(POLICY)

    def test_policy_is_constrained_and_below_hard_stop(self) -> None:
        self.assertEqual(self.policy["profile"], "constrained")
        self.assertEqual(self.policy["workspace_max_bytes"], 4 * 1024**3)
        self.assertEqual(self.policy["hard_stop_workspace_bytes"], 8 * 1024**3)
        self.assertNotIn(
            "--prune=now", json.dumps(self.policy["cleanup_commands"])
        )

    def test_guard_protect_stop_and_recovery_ladder(self) -> None:
        maximum = self.policy["workspace_max_bytes"]
        fixtures = [
            ("recover", usage(workspace=100), "recover", "pass"),
            ("guard", usage(workspace=int(maximum * 0.8)), "guard", "pass"),
            ("protect", usage(workspace=int(maximum * 0.95)), "protect", "pass"),
            (
                "stop",
                usage(workspace=self.policy["hard_stop_workspace_bytes"] + 1),
                "stop",
                "fail",
            ),
            ("recovered", usage(workspace=100), "recover", "pass"),
        ]
        for name, fixture, state, result in fixtures:
            with self.subTest(name=name):
                evaluated = WORKSPACE_BUDGET.evaluate(self.policy, fixture)
                self.assertEqual(evaluated["state"], state)
                self.assertEqual(evaluated["result"], result)

    def test_host_reserve_protects_even_when_workspace_is_small(self) -> None:
        evaluated = WORKSPACE_BUDGET.evaluate(
            self.policy,
            usage(available=self.policy["host_reserve_min_bytes"] - 1),
        )
        self.assertEqual(evaluated["state"], "protect")
        self.assertIn("host_reserve_protect", evaluated["reasons"])

    def test_tree_measurement_does_not_follow_symlinks(self) -> None:
        with tempfile.TemporaryDirectory(prefix="cyberboss-budget-tree-") as raw:
            root = Path(raw)
            inside = root / "inside"
            outside = root / "outside"
            inside.mkdir()
            outside.mkdir()
            (inside / "small").write_bytes(b"x")
            (outside / "large").write_bytes(b"x" * 1024 * 1024)
            (inside / "escape").symlink_to(outside)
            measured = WORKSPACE_BUDGET.tree_bytes(inside)
        self.assertLess(measured, 4096)

    def test_fixture_cli_writes_bounded_evidence(self) -> None:
        with tempfile.TemporaryDirectory(prefix="cyberboss-budget-cli-") as raw:
            root = Path(raw)
            fixture = root / "usage.json"
            output = root / "result.json"
            fixture.write_text(json.dumps(usage()), encoding="utf-8")
            result = subprocess.run(
                [
                    "python3",
                    str(SCRIPT),
                    "--policy",
                    str(POLICY),
                    "--usage-fixture",
                    str(fixture),
                    "--output",
                    str(output),
                ],
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                check=False,
            )
            evidence = json.loads(output.read_text(encoding="utf-8"))
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("WORKSPACE_BUDGET=PASS state=recover", result.stdout)
        self.assertEqual(evidence["evidence_scope"], "deterministic_fixture")
        self.assertTrue(evidence["no_prune_now"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
