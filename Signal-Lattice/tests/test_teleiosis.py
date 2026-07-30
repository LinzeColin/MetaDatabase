import unittest
from signal_lattice.teleiosis import *
class T(unittest.TestCase):
 def ev(self,x):return Evaluation(x['score'],x.get('safe',True),True,{'score':x['score']})
 def test_keep_better(self):self.assertEqual(champion_challenger({'score':1},{'score':2},self.ev)['verdict'],'KEEP_CANDIDATE')
 def test_keep_base(self):self.assertEqual(champion_challenger({'score':2},{'score':1},self.ev)['verdict'],'KEEP_BASELINE')
 def test_revert_unsafe(self):self.assertEqual(champion_challenger({'score':1},{'score':9,'safe':False},self.ev)['verdict'],'REVERT')
