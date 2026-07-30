import unittest
from signal_lattice.consensus import reconcile_claims
class T(unittest.TestCase):
 def test_duplicate_root_not_multiple_votes(self):
  c=[{'subject':'X','predicate':'p','horizon':'1m','as_of':'t','direction':'UP','root_evidence_sha256':'a'},{'subject':'X','predicate':'p','horizon':'1m','as_of':'t','direction':'UP','root_evidence_sha256':'a'}]
  r=reconcile_claims(c);self.assertEqual(r['consensus'][0]['independent_root_count'],1)
 def test_conflict_preserved(self):
  c=[{'subject':'X','predicate':'p','horizon':'1m','as_of':'t','direction':'UP','root_evidence_sha256':'a'},{'subject':'X','predicate':'p','horizon':'1m','as_of':'t','direction':'DOWN','root_evidence_sha256':'b'}]
  self.assertEqual(len(reconcile_claims(c)['conflicts']),1)
 def test_order_invariant(self):
  c=[{'subject':'X','predicate':'p','horizon':'1m','as_of':'t','direction':'UP','root_evidence_sha256':'a'}];self.assertEqual(reconcile_claims(c),reconcile_claims(list(reversed(c))))
