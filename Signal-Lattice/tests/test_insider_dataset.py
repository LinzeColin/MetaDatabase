"""DERA 内部人数据集：只把 Form 4 里的 P 买入与首次出现日读进库，4/A 与卖出不入买入历史。"""

from __future__ import annotations

import io
import unittest
import zipfile

from signal_lattice.evidence.eventstore import EventStore
from signal_lattice.evidence.insider_dataset import dera_date, load_dataset_zip, pool_p_candidates


def make_zip():
    submission = ("ACCESSION_NUMBER\tFILING_DATE\tDOCUMENT_TYPE\tISSUERCIK\tISSUERNAME\n"
                  "A-1\t30-JUN-2026\t4\t0000000100\tPool Co\n"
                  "A-2\t30-JUN-2026\t4\t0000000100\tPool Co\n"
                  "A-3\t30-JUN-2026\t4/A\t0000000100\tPool Co\n"
                  "A-4\t29-JUN-2026\t4\t0000000200\tOutside Co\n"
                  "A-5\t28-JUN-2026\t3\t0000000100\tPool Co\n")
    owners = ("ACCESSION_NUMBER\tRPTOWNERCIK\n"
              "A-1\t0000900001\nA-2\t0000900002\nA-3\t0000900001\nA-4\t0000900003\nA-5\t0000900004\n")
    trans = ("ACCESSION_NUMBER\tTRANS_DATE\tTRANS_CODE\tTRANS_SHARES\tTRANS_PRICEPERSHARE\tTRANS_ACQUIRED_DISP_CD\n"
             "A-1\t26-JUN-2026\tP\t1000\t30.0\tA\n"
             "A-2\t26-JUN-2026\tS\t5000\t30.0\tD\n"
             "A-3\t26-JUN-2026\tP\t1000\t30.0\tA\n"
             "A-4\t26-JUN-2026\tP\t10\t5.0\tA\n")
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        archive.writestr("SUBMISSION.tsv", submission)
        archive.writestr("REPORTINGOWNER.tsv", owners)
        archive.writestr("NONDERIV_TRANS.tsv", trans)
    return buffer.getvalue()


class DatasetTests(unittest.TestCase):
    def test_dates(self):
        self.assertEqual(dera_date("30-JUN-2026"), "2026-06-30")
        self.assertIsNone(dera_date("garbage"))

    def test_load_keeps_only_form4_code_p_and_tracks_first_seen(self):
        store = EventStore(":memory:")
        stats = load_dataset_zip(store, make_zip(), "2026q2", pool_ciks=[100])
        rows = store.db.execute("SELECT accession, owner_cik, issuer_cik, trade_date, filed FROM insider_p ORDER BY accession").fetchall()
        self.assertEqual([tuple(r) for r in rows], [("A-1", 900001, 100, "2026-06-26", "2026-06-30"),
                                                    ("A-4", 900003, 200, "2026-06-26", "2026-06-29")])
        self.assertEqual(stats["pool_p_accessions"], 1)
        self.assertEqual(store.owner_first_filed(900004), "2026-06-28")      # Form 3 也算「首次出现」
        self.assertEqual(store.owner_first_filed(900001), "2026-06-30")

    def test_candidates_are_pool_only_and_respect_amount_and_dates(self):
        store = EventStore(":memory:")
        load_dataset_zip(store, make_zip(), "2026q2", pool_ciks=[100])
        self.assertEqual(pool_p_candidates(store, [100], "2026-01-01", "2026-06-30", 25_000), [("A-1", 100)])
        self.assertEqual(pool_p_candidates(store, [100], "2026-01-01", "2026-06-30", 40_000), [])
        self.assertEqual(pool_p_candidates(store, [100], "2026-07-01", "2026-09-30", 25_000), [])
        self.assertEqual(pool_p_candidates(store, [200], "2026-01-01", "2026-06-30", 10), [("A-4", 200)])


if __name__ == "__main__":
    unittest.main()
