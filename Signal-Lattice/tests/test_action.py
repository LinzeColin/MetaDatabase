import unittest
from datetime import datetime,timezone
from signal_lattice.action import decide,REQUIRED_GATES

class T(unittest.TestCase):
 def test_client_cannot_bypass(self):
  p=decide({'symbol':'NVDA','market':'US','upstream_seal_ready':True,'point_in_time_data_ready':True},{},datetime(2026,1,1,tzinfo=timezone.utc));self.assertEqual(p['action'],'NO_ACTION');self.assertGreater(len(p['reasons']),1)
 def test_human_recommendation_can_be_emitted_only_with_trusted_snapshot(self):
  recommendation={'symbol':'NVDA','market':'US','recommended_action':'BUY','valid_until':'2026-01-02T00:00:00+00:00','human_execution_only':True,'automatic_execution_allowed':False,'evidence_refs':['filing:x']}
  p=decide({'symbol':'NVDA','market':'US'},{'gates':{x:True for x in REQUIRED_GATES},'recommendation':recommendation},datetime(2026,1,1,tzinfo=timezone.utc),recommendation_enabled=True)
  self.assertEqual(p['action'],'BUY');self.assertTrue(p['human_execution_only']);self.assertFalse(p['automatic_execution_allowed'])
 def test_mode_disabled_is_no_action(self):
  recommendation={'symbol':'NVDA','market':'US','recommended_action':'BUY','valid_until':'2026-01-02T00:00:00+00:00'}
  p=decide({'symbol':'NVDA','market':'US'},{'gates':{x:True for x in REQUIRED_GATES},'recommendation':recommendation},datetime(2026,1,1,tzinfo=timezone.utc),recommendation_enabled=False)
  self.assertEqual(p['action'],'NO_ACTION');self.assertIn('HUMAN_RECOMMENDATION_MODE_DISABLED',p['reasons'])
 def test_zero_runtime(self):
  p=decide({'symbol':'A','market':'US'},{},datetime(2026,1,1,tzinfo=timezone.utc));self.assertEqual(p['runtime_agent_dependency'],0);self.assertEqual(p['runtime_llm_tokens'],0);self.assertFalse(p['automatic_execution_allowed'])
