import unittest

from fifa_daily import sources

JSON_SAMPLE = {"name": "X", "matches": [
    {"round": "Matchday 1", "date": "2026-08-21", "time": "20:00", "team1": "A", "team2": "B",
     "score": {"ht": [1, 0], "ft": [3, 0]}},
    {"round": "Matchday 1", "date": "2026-08-22", "time": "12:30", "team1": "C", "team2": "D", "score": [0, 0]},
    {"round": "Matchday 2", "date": "2026-10-10", "time": "15:00", "team1": "E", "team2": "F"},
    {"round": "Matchday 2", "date": "2026-10-10", "team1": "G", "team2": "H", "score": None},
]}

TXT_SAMPLE = """= UEFA Champions League 2025/26

▪ League, Matchday 1
  Tue Sep 16 2025
    18:45  Athletic Club (ESP)     v Arsenal FC (ENG)         0-2 (0-0)
           PSV (NED)               v Royale Union Saint-Gilloise (BEL)  1-3 (0-2)
  Wed Sep 17
    18:45  PAE Olympiakos SFP (GRE) v Paphos FC (CYP)          0-0

▪ Finals, Round of 16
  Tue Mar 10
    21:00  Juventus FC (ITA)       v Galatasaray SK (TUR)     3-2 a.e.t. (3-0, 1-0)
  Sat May 30
    18:00  Paris Saint-Germain FC (FRA) v Arsenal FC (ENG)         4-3 pen. 1-1 a.e.t. (1-1, 0-1)
"""

WIKI_SAMPLE = """==Matches==
===Matchday 1===
{{#invoke:Football box|main
|date       = {{Start date|2026|9|8|df=y}}
|time       = 18:45&nbsp;{{small|(19:45 [[UTC+03:00|UTC+3]])}}
|team1      = [[AEK Athens F.C.|AEK Athens]] {{fbaicon|GRE}}
|score      = 1–0
|team2      = {{fbaicon|AUT}} [[LASK]]
|goals1     =
*[[Răzvan Marin|Marin]] {{goal|21}}
|stadium    = [[Agia Sophia Stadium]], [[Athens]]
}}
----
===Matchday 2===
{{#invoke:Football box|main
|date       = {{Start date|2026|10|13|df=y}}
|time       = 21:00
|team1      = [[Arsenal F.C.|Arsenal]] {{fbaicon|ENG}}
|score      =
|team2      = {{fbaicon|FRA}} [[Lille OSC|Lille]]
|goals1     =
|attendance = <!-- <ref>x</ref> -->
}}
"""


class SourceParsing(unittest.TestCase):
    def test_football_json_three_score_shapes(self):
        ms = sources.parse_football_json(JSON_SAMPLE, "en.1", "2026-27", "Europe/London")
        self.assertEqual([(m.hg, m.ag) for m in ms], [(3, 0), (0, 0), (None, None), (None, None)])
        # 8 月英国夏令时 UTC+1：20:00 -> 19:00Z
        self.assertEqual(ms[0].kickoff_utc, "2026-08-21T19:00Z")
        self.assertIsNone(ms[3].kickoff_utc)  # 没有开球时间就如实为 None

    def test_to_utc_handles_dst_switch(self):
        self.assertEqual(sources.to_utc("2026-10-24", "21:00", "Europe/Paris"), "2026-10-24T19:00Z")  # CEST
        self.assertEqual(sources.to_utc("2026-10-26", "21:00", "Europe/Paris"), "2026-10-26T20:00Z")  # CET
        self.assertIsNone(sources.to_utc("2026-10-26", "", "Europe/Paris"))

    def test_football_txt_scores_and_years(self):
        ms = sources.parse_football_txt(TXT_SAMPLE, "uefa.cl", "2025-26")
        got = [(m.date, m.home.split(" (")[0], m.hg, m.ag) for m in ms]
        self.assertEqual(got[0], ("2025-09-16", "Athletic Club", 0, 2))
        self.assertEqual(got[2][0], "2025-09-17")
        # 加时赛取 90 分钟比分（括号里第一个）；点球大战同理
        self.assertEqual(got[3][2:], (3, 0))
        self.assertEqual(got[4][2:], (1, 1))
        # 1-5 月属于赛季的后一年
        self.assertEqual(got[3][0], "2026-03-10")
        self.assertEqual(len(ms), 5)

    def test_wikipedia_boxes(self):
        ms = sources.parse_wiki_boxes(WIKI_SAMPLE, "uefa.cl", "2026-27", "Europe/Paris")
        self.assertEqual(len(ms), 2)
        a, b = ms
        self.assertEqual((a.home, a.away, a.hg, a.ag), ("AEK Athens", "LASK", 1, 0))
        self.assertEqual(a.kickoff_utc, "2026-09-08T16:45Z")  # 18:45 CEST（括号里的当地时间不能取）
        self.assertEqual(a.round, "Matchday 1")
        self.assertEqual((b.home, b.away, b.hg, b.ag), ("Arsenal", "Lille", None, None))
        self.assertEqual(b.kickoff_utc, "2026-10-13T19:00Z")
        self.assertEqual(b.round, "Matchday 2")

    def test_wikipedia_structure_change_yields_zero(self):
        self.assertEqual(sources.parse_wiki_boxes("nothing here", "uefa.cl", "2026-27", "Europe/Paris"), [])


if __name__ == "__main__":
    unittest.main()
