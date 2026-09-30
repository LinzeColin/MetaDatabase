"""arXiv 抓取「有上限的重试 + 指数退避」的回归测试。

真正的断言在 tools/verify_arxiv_retry.mjs：它从发货中的 deploy/cloudflare/worker_cloud.js 里
抽取真实代码，用脚本化的 fetch/sleep 实跑（不联网、不真等），并带一条负控。
本测试只负责把它接进 unittest：验证器必须退出 0，且每个场景都通过。

看门狗阈值（scripts/adp_liveness_check.py）不在本测试的改动范围：重试用尽后 arXiv 仍为 0，
liveness 仍应变红——测试 `persistent_timeout_is_bounded` 保证「持续故障」仍带着 truncatedReason 返回。
"""
from __future__ import annotations

import json
import subprocess
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = ROOT.parent
VERIFY = ROOT / "tools" / "verify_arxiv_retry.mjs"

REQUIRED_SCENARIOS = {
    "first_try_success_no_retry",
    "two_timeouts_then_success_recovers",
    "persistent_timeout_is_bounded",
    "http_503_429_retried",
    "http_404_not_retried",
    "body_read_failure_retried",
    "page2_exhausted_keeps_page1",
    "page2_uses_resumption_token",
    "call_budget_is_capped",
    "backoff_exponential_and_capped",
    "negative_control_prefix_loses_the_day",
}


class ArxivFetchRetryTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        completed = subprocess.run(
            ["node", str(VERIFY)],
            cwd=REPO_ROOT,
            check=False,
            capture_output=True,
            text=True,
        )
        try:
            cls.report = json.loads(completed.stdout)
        except json.JSONDecodeError as exc:
            raise AssertionError(
                f"arXiv retry verifier emitted invalid JSON; stderr={completed.stderr!r}"
            ) from exc
        cls.returncode = completed.returncode

    def test_verifier_exits_zero_with_no_failed_scenario(self) -> None:
        self.assertEqual(self.report["failed"], [], self.report)
        self.assertEqual(self.returncode, 0)

    def test_every_required_scenario_ran_and_passed(self) -> None:
        scenarios = self.report["scenarios"]
        self.assertEqual(REQUIRED_SCENARIOS - set(scenarios), set(), "verifier skipped a scenario")
        for name in REQUIRED_SCENARIOS:
            with self.subTest(scenario=name):
                self.assertTrue(scenarios[name]["pass"], scenarios[name])

    def test_attempts_are_bounded_and_more_than_the_old_single_retry(self) -> None:
        # 旧版每页最多 2 次尝试（1 次重试）；新版必须更多，且有硬上限。
        self.assertGreater(self.report["attempts_per_page"], 2)
        self.assertLessEqual(self.report["attempts_per_page"], 5)


if __name__ == "__main__":
    unittest.main()
