import ast,json,re,unittest
from pathlib import Path
class T(unittest.TestCase):
 @classmethod
 def setUpClass(cls):cls.root=Path(__file__).resolve().parents[1]
 def test_python_syntax(self):
  for p in self.root.rglob('*.py'):
   if any(x in p.parts for x in ('.venv','build','dist')):continue
   ast.parse(p.read_text())
 def test_json(self):
  for p in self.root.rglob('*.json'):json.loads(p.read_text())
 def test_no_launchd(self):self.assertEqual(list(self.root.rglob('*.plist')),[])
 def test_no_model_sdks(self):
  text='\n'.join(p.read_text(errors='ignore') for p in (self.root/'src').rglob('*.py'))
  self.assertNotRegex(text,r'\b(openai|anthropic|google\.generativeai|langchain|autogen|crewai)\b')
 def test_ui_accessibility_contract(self):
  h=(self.root/'web/index.html').read_text();c=(self.root/'web/styles.css').read_text();self.assertIn('skip-link',h);self.assertIn('prefers-reduced-motion',c);self.assertRegex(c,r'min-height:44px')
 def test_systemd_units(self):
  units=list((self.root/'deploy/systemd').iterdir());self.assertEqual(len(units),13);self.assertFalse(any('launchd' in p.name for p in units))

 def test_root_delivery_file_allowlist(self):
  allowed={
   '00_READ_FIRST.md','CANONICAL_STATE.json','CODEX_LAST_MILE_PROMPT.txt','MEMORY_RECONCILIATION.md',
   'PURSUING_GOAL.txt','README.md','ROADMAP.md','SUBJECT_LOCK.json','MANIFEST.json',
   'events.yaml','openapi.yaml','pyproject.toml'
  }
  actual={p.name for p in self.root.iterdir() if p.is_file()}
  self.assertEqual(actual,allowed)
  self.assertFalse(any(name.startswith('-') for name in actual))
