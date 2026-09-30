"""424B5 定性：ATM / 普通股增发 / 债券等其他发行；读不出来就是 UNVERIFIED（风险口径上按增发处理）。"""

from __future__ import annotations

import unittest

from signal_lattice.branches.event_atlas import load_params
from signal_lattice.evidence.prospectus import ATM, EQUITY_OFFERING, OTHER, UNVERIFIED, classify_prospectus, plain_text

TERMS = load_params()["dilution"]["atm_terms"]


class ProspectusTests(unittest.TestCase):
    def test_atm_terms_win(self):
        self.assertEqual(classify_prospectus("We entered into an Equity Distribution Agreement to sell shares of common stock "
                                             "in at-the-market offerings", TERMS), ATM)

    def test_common_stock_offering(self):
        text = "PROSPECTUS SUPPLEMENT 5,000,000 shares of common stock offered by the company. " * 5
        self.assertEqual(classify_prospectus(text, TERMS), EQUITY_OFFERING)

    def test_notes_offering_is_other(self):
        text = "$300,000,000 5.250% Senior Notes due 2031. The notes will be senior unsecured obligations. " * 3
        self.assertEqual(classify_prospectus(text, TERMS), OTHER)

    def test_unreadable_is_unverified(self):
        self.assertEqual(classify_prospectus("cover page only", TERMS), UNVERIFIED)

    def test_entities_and_nbsp_do_not_hide_atm_wording(self):
        text = plain_text(b"<p>deemed to be an &#8220;at&nbsp;the&nbsp;market offering&#8221; as defined in Rule 415</p>")
        self.assertEqual(classify_prospectus(text, TERMS), ATM)

    def test_plain_text_strips_markup(self):
        self.assertEqual(plain_text(b"<p>Hello <b>world</b></p>"), "Hello world")


if __name__ == "__main__":
    unittest.main()
