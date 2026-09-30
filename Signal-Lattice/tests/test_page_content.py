"""B5 页面：版式（九个栏目、结论优先）不变，内容换成规则自证门 / 影子候选 / 分支卡片 / 候选比较 / 收益与硬门。

页面是静态文件，这里只钉「不会悄悄退化」的几条：栏目锚点齐、空值统一显示「—」、手机宽度不横向滚动整页、
证据不足时页面自己不去拼收益数字。渲染效果由人工在桌面与手机宽度各截图确认（见交付记录）。
"""

import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
APP = (ROOT / "web" / "app.js").read_text(encoding="utf-8")
STYLES = (ROOT / "web" / "styles.css").read_text(encoding="utf-8")
INDEX = (ROOT / "web" / "index.html").read_text(encoding="utf-8")

NAV = ["唯一建议", "本轮链路", "为什么", "分支独立判断", "候选比较", "收益与硬门", "贡献度权重", "数据与时效", "系统运行"]
ANCHORS = ["decision", "cycle", "evidence", "skills", "candidates", "quant", "evolution", "lattice", "operations"]


class PageStructureTests(unittest.TestCase):
    def test_the_nine_navigation_entries_are_unchanged_and_every_anchor_is_rendered(self):
        links = re.findall(r'<a href="#([a-z]+)">([^<]+)</a>', INDEX)
        self.assertEqual([text for _, text in links], NAV)
        self.assertEqual([anchor for anchor, _ in links], ANCHORS)
        for anchor in ANCHORS:
            with self.subTest(anchor=anchor):
                self.assertRegex(APP, r"(?:\bid:|setAttribute\('id',)\s*'%s'" % anchor)

    def test_the_first_screen_states_the_decision_the_gate_and_the_shadow_candidate(self):
        for needle in ("本轮不给建议", "规则自证门", "影子候选", "decision.rationale", "shadow_candidate", "proof_gate"):
            with self.subTest(needle=needle):
                self.assertIn(needle, APP)

    def test_terms_are_explained_where_they_first_appear(self):
        for term in ("IWM", "安慰剂", "影子候选", "回测", "超额"):
            with self.subTest(term=term):
                self.assertRegex(APP, r"\['%s','" % term)

    def test_empty_values_render_as_a_dash_never_as_a_literal(self):
        self.assertIn("const txt=value=>blank(value)?'—'", APP)
        self.assertNotIn("`${undefined", APP)
        for helper in ("pct", "spct", "num", "yi", "billions", "money"):
            with self.subTest(helper=helper):
                self.assertRegex(APP, r"const %s=[^\n]*'—'" % helper)

    def test_the_page_never_composes_return_numbers_for_an_insufficient_sample(self):
        # 影子候选前向成绩：只有 sample_status 为 SUFFICIENT 才读 hit_rate / mean_excess
        block = APP[APP.index("function shadowRecord"):APP.index("function renderProofRow")]
        self.assertIn("shadow.sample_status==='SUFFICIENT'", block)
        self.assertIn("样本不足", block)
        # 回测：只有 stitched 存在（后端只在窗口 >= 6 时给）才画结果表
        self.assertIn("const published=!!(hub&&hub.stitched)", APP)

    def test_phones_get_card_layouts_instead_of_a_horizontally_scrolling_page(self):
        self.assertIn("data-label", APP)
        self.assertIn("attr(data-label)", STYLES)
        self.assertRegex(STYLES, r"@media\(max-width:680px\)\{[^@]*\.cand-table\{display:none\}\.cand-cards\{display:grid")
        self.assertIn("min-width:0!important", STYLES)                      # 手机宽度下表格不再撑出 980px

    def test_sec_links_are_only_ever_sec_https_urls(self):
        self.assertIn("url.startsWith('https://www.sec.gov/')", APP)

    def test_every_receipt_becomes_a_card_with_counts_version_hash_and_a_sentence(self):
        block = APP[APP.index("function branchCard"):APP.index("function renderBranches")]
        for needle in ("verdict_counts", "params_version", "snapshot_hash", "slice(0,12)", "r.note"):
            with self.subTest(needle=needle):
                self.assertIn(needle, block)


if __name__ == "__main__":
    unittest.main()
