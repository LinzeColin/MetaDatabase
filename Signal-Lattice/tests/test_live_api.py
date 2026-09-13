"""API 的阻断响应无需监听 TCP 即可验证；监听和 curl 交由目标机验收。"""

import unittest

from signal_lattice.live_api import HEADERS, blocked_report


class LiveApiTests(unittest.TestCase):
    def test_blocked_response_refuses_investment_action(self):
        report = blocked_report()
        self.assertEqual(report["state"], "SYSTEM_BLOCKED")
        self.assertIsNone(report["decision"]["action"])
        self.assertEqual(report["message"], "数据链路不完整，不出结论")
        self.assertEqual(HEADERS["Cache-Control"], "no-store")


if __name__ == "__main__":
    unittest.main()
