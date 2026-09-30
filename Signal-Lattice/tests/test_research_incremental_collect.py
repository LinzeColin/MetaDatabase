"""研究层增量采集（生产路径）：先装 DERA 内部人数据集再筛 Form 4；已安装 release 里没有 Stock_Skill 目录也能取到事件航图参数。"""

from __future__ import annotations

import json
import sys
import tempfile
import unittest
from datetime import date
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from signal_lattice import research_cycle as RC  # noqa: E402
from signal_lattice.evidence.sec_client import SecFetchError  # noqa: E402


def _fakes(coverage):
    events = mock.MagicMock()
    events.db.execute.return_value.fetchone.return_value = [None]
    events.db.execute.return_value.fetchall.return_value = []
    order = []
    ec = mock.MagicMock()
    ec.stage_dera.side_effect = lambda *a, **k: order.append("dera") or {}
    ec.stage_form4.side_effect = lambda *a, **k: order.append("form4") or {}
    ec.dera_coverage_end.return_value = coverage
    return events, ec, order


class IncrementalCollectTests(unittest.TestCase):
    def _run(self, events, ec):
        cfg = RC.CycleConfig(project_root=ROOT, work_dir=Path(tempfile.mkdtemp()), out_dir=Path(tempfile.mkdtemp()),
                             facts_db=Path("f"), events_db=Path("e"), bars_dir=Path("b"), text_cache_dir=Path("t"),
                             structure_cache_dir=Path("s"), sec_cache_dir=Path("c"))
        return RC.LiveHooks()._incremental_sec(cfg, mock.MagicMock(), mock.MagicMock(), events, [1], date(2026, 9, 29), lambda x: x, ec, lambda m: None)

    def test_dera_datasets_are_loaded_before_form4_is_screened(self):
        events, ec, order = _fakes(coverage=None)
        self._run(events, ec)
        self.assertEqual(order, ["dera", "form4"])

    def test_dera_failure_on_a_first_run_aborts_instead_of_fetching_every_form4(self):
        events, ec, order = _fakes(coverage=None)
        ec.stage_dera.side_effect = SecFetchError("boom")
        with self.assertRaises(SecFetchError):
            self._run(events, ec)
        self.assertNotIn("form4", order)

    def test_dera_failure_after_datasets_were_loaded_falls_back_to_the_loaded_coverage(self):
        events, ec, order = _fakes(coverage="2026-06-30")
        ec.stage_dera.side_effect = SecFetchError("boom")
        self._run(events, ec)
        self.assertEqual(order, ["form4"])


class EventAtlasParamsLookupTests(unittest.TestCase):
    def _cfg(self, work, root):
        return mock.Mock(work_dir=Path(work), project_root=Path(root))

    def test_the_registry_validated_active_file_wins_and_needs_no_source_tree(self):
        work = Path(tempfile.mkdtemp())
        (work / "params" / "active").mkdir(parents=True)
        (work / "params" / "active" / "equity-event-atlas.json").write_text(json.dumps({"dilution": {"atm_terms": ["at the market"]}}), "utf-8")
        params = RC._event_atlas_params(self._cfg(work, tempfile.mkdtemp()))         # project_root 下没有 Stock_Skill
        self.assertEqual(params["dilution"]["atm_terms"], ["at the market"])

    def test_falls_back_to_the_source_tree_then_fails_loudly(self):
        params = RC._event_atlas_params(self._cfg(tempfile.mkdtemp(), ROOT))
        self.assertTrue(params["dilution"]["atm_terms"])
        with self.assertRaises(FileNotFoundError):
            RC._event_atlas_params(self._cfg(tempfile.mkdtemp(), tempfile.mkdtemp()))


if __name__ == "__main__":
    unittest.main()
