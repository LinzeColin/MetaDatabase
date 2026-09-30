import unittest

from fifa_daily import teams


class TeamNames(unittest.TestCase):
    def test_variants_collapse(self):
        same = [("Arsenal FC", "Arsenal", "Arsenal F.C."),
                ("FC Bayern München", "Bayern Munich"),
                ("FC Internazionale Milano", "Inter Milan"),
                ("Paris Saint-Germain FC (FRA)", "Paris Saint-Germain"),
                ("Club Atlético de Madrid (ESP)", "Atlético Madrid"),
                ("Racing Lens", "Lens"), ("SK Slavia Praha (CZE)", "Slavia Prague")]
        for group in same:
            self.assertEqual(len({teams.key(n) for n in group}), 1, group)

    def test_different_clubs_stay_different(self):
        pairs = [("Paris FC", "Paris Saint-Germain FC"), ("Real Madrid CF", "Real Betis"),
                 ("Sparta Praha", "Sparta Rotterdam"), ("Union Berlin", "Union Saint-Gilloise"),
                 ("AC Milan", "Inter Milan"), ("Manchester City", "Manchester United")]
        for a, b in pairs:
            self.assertNotEqual(teams.key(a), teams.key(b), (a, b))

    def test_registry_display_and_zh(self):
        reg = teams.Registry()
        k = reg.add("Arsenal FC")
        reg.add("Arsenal")
        self.assertEqual(reg.display(k), "Arsenal")
        self.assertEqual(reg.zh(k), "阿森纳")


if __name__ == "__main__":
    unittest.main()
