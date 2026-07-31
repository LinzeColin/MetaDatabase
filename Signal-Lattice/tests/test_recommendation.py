from __future__ import annotations
import json,tempfile,unittest
from datetime import datetime,timezone
from pathlib import Path
from signal_lattice.clock import FakeClock
from signal_lattice.config import Settings
from signal_lattice.db import RuntimeDB
from signal_lattice.orchestrator import build_for_request
from signal_lattice.recommendation import build_trusted_snapshot,validate_market_snapshot,validate_skill_signal

class RecommendationTests(unittest.TestCase):
 @classmethod
 def setUpClass(cls):
  cls.root=Path(__file__).resolve().parents[1]
  cls.market=json.loads((cls.root/'fixtures/northstar/market_snapshot.json').read_text())
  cls.signals=[json.loads((cls.root/'fixtures/northstar/commercial_signal.json').read_text()),json.loads((cls.root/'fixtures/northstar/bottleneck_signal.json').read_text())]
  cls.policy=json.loads((cls.root/'config/decision_policy.json').read_text());cls.policy={**cls.policy,'minimum_independent_skills':2,'minimum_evidence_independence_ratio':0.6,'maximum_freshness_seconds':86400}
 def test_northstar_snapshot_passes_and_recommends(self):
  snap=build_trusted_snapshot(self.signals,self.market,self.policy,current_position_pct=0,requested_position_value_usd=1000,now=datetime(2026,7,30,0,10,tzinfo=timezone.utc))
  self.assertEqual(snap['state'],'PASS');self.assertEqual(snap['recommendation']['recommended_action'],'BUY');self.assertTrue(all(snap['gates'].values()));self.assertEqual(snap['runtime_agent_dependency'],0);self.assertEqual(snap['runtime_llm_tokens'],0)
 def test_same_evidence_fails_independence(self):
  sigs=[dict(x) for x in self.signals];sigs[1]['evidence_roots']=sigs[0]['evidence_roots']
  snap=build_trusted_snapshot(sigs,self.market,self.policy,requested_position_value_usd=1000,now=datetime(2026,7,30,0,10,tzinfo=timezone.utc))
  self.assertFalse(snap['gates']['evidence_independence']);self.assertEqual(snap['state'],'BLOCKED')
 def test_orchestrator_human_mode_and_fail_closed(self):
  with tempfile.TemporaryDirectory() as t:
   r=Path(t);db=RuntimeDB(r/'runtime.db',self.root/'db/schema.sql',FakeClock(datetime(2026,7,30,0,10,tzinfo=timezone.utc)))
   signals=[dict(x) for x in self.signals]
   third=dict(signals[0]);third['skill_id']='serenity-skill';third['evidence_roots']=['company-ir:demo-2026q2'];third['source_digest']='d'*64
   for signal in [*signals,third]:db.upsert_skill_signal(validate_skill_signal(signal))
   db.upsert_market_snapshot(validate_market_snapshot(self.market))
   enabled=Settings(r,r/'artifacts',self.root/'web',recommendation_enabled=True,runtime_environment='test',decision_policy_path=self.root/'config/decision_policy.json')
   packet,snapshot=build_for_request(db,enabled,{'symbol':'DEMO','market':'US','requested_position_value_usd':1000},now=datetime(2026,7,30,0,1,tzinfo=timezone.utc))
   self.assertEqual(packet['action'],'BUY');self.assertIsNotNone(snapshot);self.assertFalse(packet['automatic_execution_allowed'])
   disabled=Settings(r,r/'artifacts',self.root/'web',recommendation_enabled=False,runtime_environment='test',decision_policy_path=self.root/'config/decision_policy.json')
   no_action,_=build_for_request(db,disabled,{'symbol':'DEMO','market':'US','requested_position_value_usd':1000},now=datetime(2026,7,30,0,1,tzinfo=timezone.utc))
   self.assertEqual(no_action['action'],'NO_ACTION');self.assertIn('HUMAN_RECOMMENDATION_MODE_DISABLED',no_action['reasons'])
   system_blocked,_=build_for_request(db,enabled,{'symbol':'MISSING','market':'US'},now=datetime(2026,7,30,0,1,tzinfo=timezone.utc))
   self.assertEqual(system_blocked['action'],'SYSTEM_BLOCKED')
   self.assertEqual(set(system_blocked['reasons']),{'NO_TRUSTED_SKILL_SIGNALS','NO_TRUSTED_MARKET_SNAPSHOT'})
   self.assertNotEqual(system_blocked['action'],'NO_ACTION')
