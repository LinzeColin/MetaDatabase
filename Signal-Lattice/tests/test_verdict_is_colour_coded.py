"""结论标题必须按方向上色，样式表里不能留没人匹配的死选择器。

线上出过的事故：aggregate 只输出中文动作文案（“看涨”），而样式表按
BUY/SELL 这类机器码上色，于是看涨、看跌、观望全部退回 --text 白色，
一眼分不出多空。这里把「后端能产出的每个动作码」和「样式表里真的有
颜色规则的动作码」钉在一起。
"""
import re
import unittest
from pathlib import Path

from signal_lattice.aggregate import ACTION_CODES, blocked_decision, resolve_action_code

ROOT = Path(__file__).resolve().parents[1]
STYLES = (ROOT / "web" / "styles.css").read_text(encoding="utf-8")
APP_JS = (ROOT / "web" / "app.js").read_text(encoding="utf-8")
INDEX = (ROOT / "web" / "index.html").read_text(encoding="utf-8")

COLOURED_CODES = set(re.findall(r'#decision-title\[data-action="([^"]+)"\]', STYLES))


class VerdictColourCoding(unittest.TestCase):
    def test_every_emittable_action_code_has_a_colour_rule(self):
        for code in ACTION_CODES.values():
            with self.subTest(code=code):
                self.assertIn(code, COLOURED_CODES, f"{code} 没有颜色规则，标题会退回白色")

    def test_no_colour_rule_targets_an_action_code_the_backend_never_emits(self):
        self.assertEqual(COLOURED_CODES - set(ACTION_CODES.values()), set())

    def test_bullish_and_bearish_do_not_share_one_colour(self):
        bullish = re.search(r'#decision-title\[data-action="BULLISH"\]\{([^}]*)\}', STYLES)
        bearish = re.search(r'#decision-title\[data-action="BEARISH"\]\{([^}]*)\}', STYLES)
        self.assertIsNotNone(bullish)
        self.assertIsNotNone(bearish)
        self.assertNotEqual(bullish.group(1), bearish.group(1))

    def test_page_binds_the_machine_code_not_the_chinese_label(self):
        self.assertIn("'data-action':decision.action_code||'NONE'", APP_JS)
        self.assertNotIn("'data-action':decision.action|", APP_JS)

    def test_decision_payload_carries_the_action_code(self):
        self.assertEqual(blocked_decision()["action_code"], "NONE")
        self.assertEqual(resolve_action_code("看涨"), "BULLISH")
        self.assertEqual(resolve_action_code("看跌"), "BEARISH")

    def test_unknown_action_is_rejected_instead_of_rendering_white(self):
        with self.assertRaises(ValueError):
            resolve_action_code("暴涨")

    def test_live_pill_reflects_run_state(self):
        self.assertIn("live-pill pass", APP_JS)

    def test_every_static_class_in_index_html_is_styled(self):
        used = set()
        for attr in re.findall(r'class="([^"]+)"', INDEX):
            used.update(attr.split())
        for name in sorted(used):
            with self.subTest(cls=name):
                self.assertRegex(STYLES, rf"\.{re.escape(name)}\b", f".{name} 无样式，会以正文形态泄漏到页面上")


if __name__ == "__main__":
    unittest.main()
