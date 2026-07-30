import unittest
from signal_lattice.skill_adapters import normalize_skill_artifact

class AdapterTests(unittest.TestCase):
 def test_commercial_artifact_normalizes(self):
  payload={'skill_id':'stock-commercial-opportunities','version':'1','symbol':'ABC','market':'US','as_of':'2026-07-30T00:00:00+00:00','available_at':'2026-07-30T00:00:00+00:00','ingested_at':'2026-07-30T00:00:00+00:00','decision':'RESEARCH_PRIORITY','confidence':80,'economic_edge':5.0,'evidence_roots':['filing:a'],'point_in_time_ok':True,'license_ok':True,'data_quality':.9,'oos_valid':True,'quant':{'dsr_confidence':.9,'pbo':.1,'cost_bps':10},'investability':{'liquidity_score':.8},'artifact_sha256':'a'*64}
  signal=normalize_skill_artifact(payload);self.assertEqual(signal['direction'],1);self.assertAlmostEqual(signal['confidence'],.8);self.assertEqual(signal['skill_id'],'stock-commercial-opportunities')
 def test_unregistered_rejected(self):
  with self.assertRaisesRegex(ValueError,'UNREGISTERED'):
   normalize_skill_artifact({'skill_id':'unknown','symbol':'ABC','market':'US','as_of':'2026-07-30T00:00:00+00:00'})
