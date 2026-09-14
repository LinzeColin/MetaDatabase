import ast,json,re,unittest
from pathlib import Path
class T(unittest.TestCase):
 @classmethod
 def setUpClass(cls):cls.root=Path(__file__).resolve().parents[1]
 def owned(self,pattern):
  return (p for p in self.root.rglob(pattern) if p.relative_to(self.root).parts[:1]!=('Stock_Skill',))
 def test_python_syntax(self):
  for p in self.owned('*.py'):
   if any(x in p.parts for x in ('.venv','build','dist')):continue
   ast.parse(p.read_text())
 def test_json(self):
  for p in self.owned('*.json'):json.loads(p.read_text())
 def test_no_launchd(self):self.assertEqual(list(self.owned('*.plist')),[])
 def test_no_model_sdks(self):
  text='\n'.join(p.read_text(errors='ignore') for p in (self.root/'src').rglob('*.py'))
  self.assertNotRegex(text,r'\b(openai|anthropic|google\.generativeai|langchain|autogen|crewai)\b')
 def test_ui_accessibility_contract(self):
  h=(self.root/'web/index.html').read_text();c=(self.root/'web/styles.css').read_text();self.assertIn('skip-link',h);self.assertIn('prefers-reduced-motion',c);self.assertRegex(c,r'min-height:44px')
 def test_market_delay_disclosure_is_visible_with_the_decision(self):
  app=(self.root/'web/app.js').read_text();self.assertIn('港股行情为交易所规定的延迟数据（约 ${declaredDelay} 分钟），非实时。',app);self.assertIn('renderMarketDataDisclosure(report),renderDecision(report)',app);self.assertIn('observed_lag_minutes',app)
 def test_systemd_units(self):
  units=list((self.root/'deploy/systemd').iterdir());self.assertEqual(len(units),12);self.assertFalse(any('launchd' in p.name for p in units))

 def test_root_delivery_file_allowlist(self):
  allowed={
   '00_READ_FIRST.md','CANONICAL_STATE.json','CODEX_LAST_MILE_PROMPT.txt','MEMORY_RECONCILIATION.md',
   'PURSUING_GOAL.txt','README.md','ROADMAP.md','SUBJECT_LOCK.json','MANIFEST.json',
   'events.yaml','openapi.yaml','pyproject.toml'
  }
  actual={p.name for p in self.root.iterdir() if p.is_file()}
  self.assertEqual(actual,allowed)
  self.assertFalse(any(name.startswith('-') for name in actual))
