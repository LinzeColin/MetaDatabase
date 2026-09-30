"""EDGAR 索引解析与发现：格式、过滤、季度/每日切换、as_of 之后的申报一律丢弃。"""

from __future__ import annotations

import gzip
import unittest
from datetime import date
from unittest.mock import patch

from signal_lattice.evidence import edgar_index
from signal_lattice.evidence.edgar_index import discover_filings, parse_form_index, quarter_bounds
from signal_lattice.evidence.sec_client import SecNotFound

DAILY = """Description:           Daily Index of EDGAR Dissemination Feed by Form Type
Last Data Received:    Sep 29, 2026
Comments:              webmaster@sec.gov

Form Type   Company Name                                                  CIK
      Date Filed  File Name
---------------------------------------------------------------------------------------------------------------------------------------------
4               ACME CORP                                                     1234567     20260929    edgar/data/1234567/0001234567-26-000123.txt
4               DOE JANE                                                      900001      20260929    edgar/data/1234567/0001234567-26-000123.txt
8-K             Other Co 2                                                    777         20260929    edgar/data/777/0000777000-26-000009.txt
SC 13D          Activist Fund LP                                              555         20260929    edgar/data/1234567/0000555000-26-000004.txt
1-A POS         Wellstreet Realty, Inc.                                       2041878     20260929    edgar/data/2041878/0001493152-26-044913.txt
"""
FULL = DAILY.replace("20260929", "2026-06-30")


class FakeClient:
    def __init__(self, files):
        self.files, self.requested = files, []

    def get_bytes(self, url, **kwargs):
        self.requested.append(url)
        if url not in self.files:
            raise SecNotFound(url)
        body = self.files[url]
        return body if isinstance(body, bytes) else body.encode("latin-1")


class ParseTests(unittest.TestCase):
    def test_rows_parse_with_form_names_containing_spaces_and_company_names_with_commas(self):
        rows = list(parse_form_index(DAILY))
        self.assertEqual([r.form for r in rows], ["4", "4", "8-K", "SC 13D", "1-A POS"])
        self.assertEqual(rows[4].company, "Wellstreet Realty, Inc.")
        self.assertEqual(rows[0].accession, "0001234567-26-000123")
        self.assertEqual(rows[0].filed, "2026-09-29")

    def test_filter_by_form_and_cik(self):
        rows = list(parse_form_index(DAILY, forms={"4"}, ciks={1234567}))
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0].cik, 1234567)

    def test_full_index_date_format_is_accepted(self):
        self.assertEqual(next(iter(parse_form_index(FULL))).filed, "2026-06-30")

    def test_index_url_is_a_real_edgar_filing_page(self):
        row = next(iter(parse_form_index(DAILY)))
        self.assertEqual(row.index_url, "https://www.sec.gov/Archives/edgar/data/1234567/000123456726000123/0001234567-26-000123-index.htm")


class DiscoverTests(unittest.TestCase):
    def test_closed_quarter_uses_full_index_and_open_quarter_uses_daily(self):
        listing = 'href="form.20260929.idx" href="form.20260928.idx"'
        client = FakeClient({
            "https://www.sec.gov/Archives/edgar/full-index/2026/QTR2/form.gz": gzip.compress(FULL.encode("latin-1")),
            "https://www.sec.gov/Archives/edgar/daily-index/2026/QTR3/": listing,
            "https://www.sec.gov/Archives/edgar/daily-index/2026/QTR3/form.20260929.idx": DAILY,
            "https://www.sec.gov/Archives/edgar/daily-index/2026/QTR3/form.20260928.idx": DAILY.replace("20260929", "20260928"),
        })
        with patch.object(edgar_index, "date") as fake_date:
            fake_date.today.return_value = date(2026, 9, 30)
            fake_date.side_effect = lambda *a, **k: date(*a, **k)
            fake_date.fromisoformat = date.fromisoformat
            rows = discover_filings(client, date(2026, 6, 1), date(2026, 9, 29), forms={"4"}, ciks={1234567})
        self.assertEqual(sorted({r.filed for r in rows}), ["2026-06-30", "2026-09-28", "2026-09-29"])

    def test_filings_after_as_of_are_dropped(self):
        listing = 'form.20260929.idx form.20260930.idx'
        client = FakeClient({
            "https://www.sec.gov/Archives/edgar/daily-index/2026/QTR3/": listing,
            "https://www.sec.gov/Archives/edgar/daily-index/2026/QTR3/form.20260929.idx": DAILY,
            "https://www.sec.gov/Archives/edgar/daily-index/2026/QTR3/form.20260930.idx": DAILY.replace("20260929", "20260930"),
        })
        rows = discover_filings(client, date(2026, 9, 1), date(2026, 9, 30), forms={"4"}, as_of=date(2026, 9, 29))
        self.assertEqual({r.filed for r in rows}, {"2026-09-29"})
        self.assertFalse(any("20260930" in url and url.endswith(".idx") for url in client.requested))

    def test_quarter_bounds(self):
        self.assertEqual(quarter_bounds(2026, 4), (date(2026, 10, 1), date(2026, 12, 31)))
        self.assertEqual(quarter_bounds(2026, 1), (date(2026, 1, 1), date(2026, 3, 31)))


if __name__ == "__main__":
    unittest.main()
