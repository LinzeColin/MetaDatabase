import unittest
from datetime import date

import numpy as np

from fifa_daily import model, teams
from fifa_daily.dataset import prepare
from tests.helpers import STRENGTH, synth_raw


class ModelTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.now = date(2026, 9, 30)
        cls.ds = prepare(synth_raw(cls.now)["matches"])
        cls.fitted = model.fit(cls.ds.played, cls.ds.team_group, "2026-10-01")

    def test_recovers_strength_ordering(self):
        f = self.fitted
        order = [k for k, _ in sorted(STRENGTH.items(), key=lambda kv: -kv[1])]
        rating = {}
        for name in order:
            s = f.team_strength(teams.key(f"en.1-{name}"))
            self.assertIsNotNone(s, name)
            rating[name] = s["att"] + s["def"]
        got = sorted(rating, key=lambda n: -rating[n])
        self.assertEqual(got[0], "Alpha")
        self.assertEqual(got[-1], "Echo")

    def test_probabilities_are_coherent(self):
        f = self.fitted
        p = f.predict(teams.key("en.1-Alpha"), teams.key("en.1-Echo"), "en.1", draws=200)
        self.assertAlmostEqual(p["p_home"] + p["p_draw"] + p["p_away"], 1.0, places=6)
        self.assertGreater(p["p_home"], p["p_away"])
        for k, lo_hi in p["interval"].items():
            self.assertLess(lo_hi[0], lo_hi[1])
        self.assertTrue(p["interval"]["home"][0] < p["p_home"] < p["interval"]["home"][1])
        self.assertEqual(len(p["top_scores"]), 3)

    def test_unknown_team_is_flagged_by_missing_strength_and_wide(self):
        f = self.fitted
        self.assertIsNone(f.team_strength("nobody"))
        known = f.predict(teams.key("en.1-Charlie"), teams.key("en.1-Delta"), "en.1", draws=300)
        unk = f.predict("nobody", teams.key("en.1-Delta"), "en.1", draws=300)
        self.assertAlmostEqual(unk["p_home"] + unk["p_draw"] + unk["p_away"], 1.0, places=6)
        w = lambda p: p["interval"]["home"][1] - p["interval"]["home"][0]  # noqa: E731
        self.assertGreaterEqual(w(unk), w(known) * 0.9)

    def test_only_uses_matches_before_as_of(self):
        early = model.fit(self.ds.played, self.ds.team_group, "2026-08-15")
        self.assertLess(early.n_matches, self.fitted.n_matches)

    def test_score_matrix_normalised(self):
        m = model.score_matrix(1.6, 1.1, -0.05)
        self.assertAlmostEqual(float(m.sum()), 1.0, places=9)
        s = model.summarize_matrix(m)
        self.assertAlmostEqual(s["p_home"] + s["p_draw"] + s["p_away"], 1.0, places=9)

    def test_too_little_data_refuses(self):
        with self.assertRaises(ValueError):
            model.fit(self.ds.played[:10], self.ds.team_group, "2026-10-01")


if __name__ == "__main__":
    unittest.main()
