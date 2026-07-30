import unittest
from datetime import datetime,timezone
from signal_lattice.action import decide,REQUIRED_GATES
class T(unittest.TestCase):
 def test_client_cannot_bypass(self):
  p=decide({'symbol':'NVDA','market':'US','upstream_seal_ready':True,'point_in_time_data_ready':True},{},datetime(2026,1,1,tzinfo=timezone.utc));self.assertEqual(p['action'],'NO_ACTION');self.assertGreater(len(p['reasons']),1)
 def test_live_action_disabled_even_all_gates(self):
  p=decide({'symbol':'NVDA','market':'US'},{x:True for x in REQUIRED_GATES},datetime(2026,1,1,tzinfo=timezone.utc));self.assertEqual(p['action'],'NO_ACTION');self.assertIn('LIVE_ACTION_DISABLED_IN_CURRENT_RELEASE',p['reasons'])
 def test_zero_runtime(self):
  p=decide({'symbol':'A','market':'US'},{},datetime(2026,1,1,tzinfo=timezone.utc));self.assertEqual(p['runtime_agent_dependency'],0);self.assertEqual(p['runtime_llm_tokens'],0);self.assertFalse(p['automatic_execution_allowed'])
