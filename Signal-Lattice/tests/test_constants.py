import unittest
from signal_lattice import constants as c
class T(unittest.TestCase):
 def test_runtime_invariants(self):
  self.assertEqual(c.RUNTIME_MODE,'DETERMINISTIC_ONLY');self.assertEqual(c.MODEL_MODE,'DISABLED');self.assertEqual(c.RUNTIME_TOKEN_BUDGET,0);self.assertFalse(c.AUTOMATIC_TRADING);self.assertFalse(c.UPSTREAM_WRITEBACK);self.assertFalse(c.MACOS_RUNTIME_ALLOWED)
 def test_business_line_shape(self):self.assertEqual(len(c.BUSINESS_LINES),13);self.assertEqual(len(c.SLICES),9)
