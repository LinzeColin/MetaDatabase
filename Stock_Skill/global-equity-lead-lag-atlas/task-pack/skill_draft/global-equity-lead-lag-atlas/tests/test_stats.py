from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from gela.stats import benjamini_hochberg, pearson, spearman


class StatsTests(unittest.TestCase):
    def test_pearson_identity(self) -> None:
        self.assertAlmostEqual(pearson([1, 2, 3, 4], [1, 2, 3, 4]) or 0, 1.0)

    def test_spearman_reverse(self) -> None:
        self.assertAlmostEqual(spearman([1, 2, 3, 4], [4, 3, 2, 1]) or 0, -1.0)

    def test_bh_monotonic_mapping(self) -> None:
        values = benjamini_hochberg([0.001, 0.02, 0.5, None])
        self.assertIsNone(values[3])
        self.assertLessEqual(values[0] or 1, values[1] or 1)
        self.assertLessEqual(values[1] or 1, values[2] or 1)


if __name__ == "__main__":
    unittest.main()
