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
  app=(self.root/'web/app.js').read_text();self.assertIn('港股行情为交易所规定的延迟数据（约 ${declaredDelay} 分钟），非实时。',app);self.assertIn('const heroNotice=marketDelayDisclosure(report);',app);self.assertIn('hero-delay-notice',app);self.assertIn('observed_lag_minutes',app)
 def test_systemd_units(self):
  units=list((self.root/'deploy/systemd').iterdir());self.assertEqual(len(units),12);self.assertFalse(any('launchd' in p.name for p in units))

 def _script_allowed_root_files(self,relative):
  """从脚本源码里解析 ALLOWED_ROOT_FILES，不执行脚本（verify_package 需要 3.11+ 的 tomllib）。"""
  tree=ast.parse((self.root/relative).read_text(encoding='utf-8'))
  for node in tree.body:
   if not isinstance(node,ast.Assign):continue
   if not any(isinstance(t,ast.Name) and t.id=='ALLOWED_ROOT_FILES' for t in node.targets):continue
   return set(ast.literal_eval(node.value))
  self.fail('ALLOWED_ROOT_FILES not found in %s'%relative)

 def test_root_delivery_file_allowlist(self):
  allowed={
   '00_READ_FIRST.md','ACTIVE_RELEASE.md','CANONICAL_STATE.json','CODEX_LAST_MILE_PROMPT.txt',
   'HANDOFF.md','MANIFEST.json','MEMORY_RECONCILIATION.md','PURSUING_GOAL.txt','README.md',
   'ROADMAP.md','SUBJECT_LOCK.json','V19_CANONICAL_STATE.json',
   'events.yaml','openapi.yaml','pyproject.toml'
  }
  actual={p.name for p in self.root.iterdir() if p.is_file()}
  self.assertEqual(actual,allowed)
  self.assertFalse(any(name.startswith('-') for name in actual))

 def test_root_allowlist_has_one_meaning_across_tooling(self):
  """根交付清单在测试、build_manifest、verify_package 三处必须字面一致。

  这三份曾各自硬编码同一集合并独立漂移：ACTIVE_RELEASE.md / HANDOFF.md /
  V19_CANONICAL_STATE.json 已进入两个脚本却没进测试，红灯出在测试而非事实。
  """
  expected={
   '00_READ_FIRST.md','ACTIVE_RELEASE.md','CANONICAL_STATE.json','CODEX_LAST_MILE_PROMPT.txt',
   'HANDOFF.md','MANIFEST.json','MEMORY_RECONCILIATION.md','PURSUING_GOAL.txt','README.md',
   'ROADMAP.md','SUBJECT_LOCK.json','V19_CANONICAL_STATE.json',
   'events.yaml','openapi.yaml','pyproject.toml'
  }
  for relative in ('scripts/build_manifest.py','scripts/verify_package.py'):
   self.assertEqual(self._script_allowed_root_files(relative),expected,relative)
