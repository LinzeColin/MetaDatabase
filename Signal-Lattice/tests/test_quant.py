import unittest
from datetime import datetime,timedelta,timezone
from signal_lattice.quant import *
class T(unittest.TestCase):
 def test_pit_requires_ingested(self):
  d=datetime(2026,1,2,tzinfo=timezone.utc);r=[PointInTimeRecord(d-timedelta(days=3),d-timedelta(days=1),d+timedelta(days=1),1.0)];self.assertEqual(visible_at(r,d),[])
 def test_pit_accepts_known(self):
  d=datetime(2026,1,2,tzinfo=timezone.utc);r=PointInTimeRecord(d-timedelta(days=3),d-timedelta(days=2),d-timedelta(days=1),1.0);self.assertEqual(visible_at([r],d),[r])
 def test_high_win_rate_can_be_negative(self):self.assertLess(net_expected_return(.75,.01,.08,.001,.001,.002),0)
 def test_cost_erases_edge(self):self.assertLess(net_expected_return(.55,.02,.015,.004,.003,.006),0)
 def test_drawdown(self):self.assertLess(max_drawdown([.1,-.2,.05]),-.1)
 def test_pbo(self):
  ins=[[.9,.2],[.8,.1],[.7,.2]];outs=[[.1,.8],[.2,.7],[.1,.6]];self.assertEqual(pbo(ins,outs),1.0)
 def test_dsr_penalty(self):self.assertLess(deflated_sharpe_gate(2.0,100),2.0)
