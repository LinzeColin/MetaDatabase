import unittest
from signal_lattice.status import default_matrix,reconcile
class T(unittest.TestCase):
 def test_shape(self):
  m=default_matrix();r=reconcile(m);self.assertEqual(r['line_count'],13);self.assertEqual(r['cell_count'],117);self.assertEqual(r['state'],'PASS')
 def test_target_requires_measurement(self):self.assertEqual(reconcile(default_matrix(),target=True)['state'],'BLOCKED')
 def test_target_pass(self):
  m=default_matrix('TARGET_ENVIRONMENT')
  for line in m['lines']:
   for c in line['cells']:c['measured']=True;c['evidence_ref']='sha256:x';c['state']='PASS'
  self.assertEqual(reconcile(m,target=True)['state'],'PASS')
