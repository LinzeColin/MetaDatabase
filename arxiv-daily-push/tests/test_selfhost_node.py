"""自托管运行时（Node）测试的 pytest/unittest 入口。

真正的断言在 deploy/selfhost/tests/*.test.mjs（node:test）：
  · d1_overlay.test.mjs   D1 兼容层（绑定类型、事务、first/all/run 语义）与 worker 加载覆盖层（fail-closed）
  · pages.test.mjs        真流水线（假网络）造库后起真 HTTP 服务，逐页请求、写操作、健康检查、Range
  · job_retry.test.mjs    每日任务：arXiv 失败退避重试、重试有上限、失败留痕不静默、当天幂等、重开失败行、负控
这里只负责把它们接进本仓的 pytest 流程：node 必须退出 0，且确实跑了足够多的用例（防止「一个都没跑也算绿」）。
"""
from __future__ import annotations

import re
import shutil
import subprocess
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SELFHOST = ROOT / "deploy" / "selfhost"
NODE = shutil.which("node")
MIN_TESTS = 28   # 当前 29 个；有人删用例让总数掉下去时这里会报


@unittest.skipUnless(NODE, "需要 node >= 22.13（node:sqlite）")
class SelfhostNodeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        files = sorted(str(p) for p in (SELFHOST / "tests").glob("*.test.mjs"))
        cls.proc = subprocess.run(
            [NODE, "--disable-warning=ExperimentalWarning", "--test", "--test-reporter=tap", *files],
            cwd=SELFHOST, capture_output=True, text=True, timeout=600,
        )
        cls.out = cls.proc.stdout

    def _count(self, key: str) -> int:
        m = re.search(rf"^# {key} (\d+)$", self.out, re.M)
        self.assertIsNotNone(m, f"node 输出里找不到 '# {key}'：\n{self.out[-2000:]}\n{self.proc.stderr[-1000:]}")
        return int(m.group(1))

    def test_node_suite_passes(self) -> None:
        self.assertEqual(self._count("fail"), 0, self.out[-4000:])
        self.assertEqual(self.proc.returncode, 0, self.proc.stderr[-2000:])

    def test_node_suite_really_ran(self) -> None:
        self.assertGreaterEqual(self._count("pass"), MIN_TESTS)
        self.assertEqual(self._count("skipped"), 0)


if __name__ == "__main__":
    unittest.main()
