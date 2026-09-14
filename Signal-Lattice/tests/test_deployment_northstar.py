import json,os,shutil,subprocess,tempfile,unittest
from pathlib import Path
from signal_lattice.constants import VERSION

class DeploymentNorthStarTests(unittest.TestCase):
 @classmethod
 def setUpClass(cls):
  cls.root=Path(__file__).resolve().parents[1]
  cls.python=Path('/Users/linzezhang/.local/share/uv/python/cpython-3.11.15-macos-aarch64-none/bin/python3')
 def test_shell_syntax_and_completion_contract(self):
  scripts=['deploy_northstar.sh','install_cloudflare_tunnel.sh','status_closure.sh','install_release.sh','rollback.sh','provision_runtime.sh']
  for name in scripts:
   r=subprocess.run(['bash','-n',str(self.root/'scripts'/name)],text=True,stdout=subprocess.PIPE,stderr=subprocess.PIPE);self.assertEqual(r.returncode,0,name+':'+r.stderr)
  deploy=(self.root/'scripts/deploy_northstar.sh').read_text();self.assertIn('verify_public_release.py',deploy);self.assertIn('DELIVERY_RESULT.json',deploy);self.assertIn('status_closure.sh',deploy);self.assertIn('verify_moomoo_opend.py',deploy);self.assertIn('signal-lattice-cycle.service',deploy);self.assertIn('ingest_api_token',deploy)
 def test_cloudflare_script_does_not_replace_active_shared_service(self):
  text=(self.root/'scripts/install_cloudflare_tunnel.sh').read_text();self.assertIn('EXISTING_CLOUDFLARED_SERVICE_ACTIVE_NO_REPLACEMENT',text);self.assertNotIn('service uninstall',text)

 def test_v2_wheel_install_and_rollback_console_paths_complete(self):
  with tempfile.TemporaryDirectory(dir='/private/tmp') as tmp:
   tmp=Path(tmp);wheel_dir=tmp/'wheel';receipt=tmp/'wheel.json';install_root=tmp/'install'
   built=subprocess.run([str(self.python),str(self.root/'scripts/build_wheel.py'),'--root',str(self.root),'--output-dir',str(wheel_dir),'--receipt',str(receipt)],cwd=self.root,text=True,stdout=subprocess.PIPE,stderr=subprocess.PIPE)
   self.assertEqual(built.returncode,0,built.stderr)
   wheel=next(wheel_dir.glob('*.whl'))
   previous_source=tmp/'previous-source'
   shutil.copytree(self.root,previous_source,ignore=shutil.ignore_patterns('.git','.pytest_cache','build','*.pyc'))
   previous_pyproject=previous_source/'pyproject.toml'
   previous_pyproject.write_text(previous_pyproject.read_text().replace('version = "0.0.0.2.8"','version = "0.0.0.2.2"'))
   previous_wheel_dir=tmp/'previous-wheel';previous_receipt=tmp/'previous-wheel.json'
   previous_built=subprocess.run([str(self.python),str(previous_source/'scripts/build_wheel.py'),'--root',str(previous_source),'--output-dir',str(previous_wheel_dir),'--receipt',str(previous_receipt)],cwd=previous_source,text=True,stdout=subprocess.PIPE,stderr=subprocess.PIPE)
   self.assertEqual(previous_built.returncode,0,previous_built.stderr)
   previous_wheel=next(previous_wheel_dir.glob('*.whl'))
   state_dir=tmp/'state'
   env=os.environ.copy();env['SIGNAL_LATTICE_INSTALL_ROOT']=str(install_root);env['SIGNAL_LATTICE_STATE_DIR']=str(state_dir);env['SIGNAL_LATTICE_PYTHON']=str(self.python);env['PYTHONPATH']=str(self.root/'src')
   previous_installed=subprocess.run(['bash',str(previous_source/'scripts/install_release.sh'),str(previous_wheel)],cwd=previous_source,env=env,text=True,stdout=subprocess.PIPE,stderr=subprocess.PIPE)
   self.assertEqual(previous_installed.returncode,0,previous_installed.stderr)
   installed=subprocess.run(['bash',str(self.root/'scripts/install_release.sh'),str(wheel)],cwd=self.root,env=env,text=True,stdout=subprocess.PIPE,stderr=subprocess.PIPE)
   self.assertEqual(installed.returncode,0,installed.stderr)
   cli=install_root/'current/venv/bin/signal-lattice'
   self.assertTrue(cli.is_file())
   clean_env={k:v for k,v in os.environ.items() if k not in {'PYTHONPATH','PYTHONHOME'}}
   smoke=subprocess.run([str(cli),'--help'],cwd=tmp,env=clean_env,text=True,stdout=subprocess.PIPE,stderr=subprocess.PIPE)
   self.assertEqual(smoke.returncode,0,smoke.stderr)
   release=json.loads((install_root/'current/release.json').read_text())
   self.assertTrue(release['console_script_verified'])
   self.assertFalse(release['relocatable_venv'])
   self.assertEqual(release['version'], VERSION)
   state_dir.mkdir()
   verify=subprocess.run([str(cli),'verify-runtime'],cwd=tmp,env=clean_env|{'SIGNAL_LATTICE_STATE_DIR':str(state_dir),'SIGNAL_LATTICE_WEB_DIR':str(install_root/'current/web')},text=True,stdout=subprocess.PIPE,stderr=subprocess.PIPE)
   self.assertEqual(verify.returncode,0,verify.stderr)
   self.assertEqual(json.loads(verify.stdout)['state'],'PASS')

   previous=install_root/'releases'/'0.0.0.2.2'
   prior_receipt=json.loads((previous/'release.json').read_text())
   self.assertEqual(prior_receipt['version'],'0.0.0.2.2')
   self.assertTrue((previous/'venv/bin/signal-lattice').is_file())
   self.assertEqual((install_root/'previous').resolve(),previous.resolve())
   rollback_env=clean_env|{
    'SIGNAL_LATTICE_INSTALL_ROOT':str(install_root),
    'SIGNAL_LATTICE_STATE_DIR':str(state_dir),
    'SIGNAL_LATTICE_PYTHON':str(self.python),
    'SIGNAL_LATTICE_RESTART_SERVICES':'0',
   }
   rolled=subprocess.run(['bash',str(self.root/'scripts/rollback.sh')],cwd=self.root,env=rollback_env,text=True,stdout=subprocess.PIPE,stderr=subprocess.PIPE)
   self.assertEqual(rolled.returncode,0,rolled.stderr)
   self.assertEqual((install_root/'current').resolve(),previous.resolve())
   rollback_receipt=json.loads((state_dir/'artifacts/rollback_receipt.json').read_text())
   self.assertEqual(rollback_receipt['state'],'PASS')
   self.assertEqual(rollback_receipt['to'],str(previous))

 def test_v2_collector_uses_bounded_once_timer_and_v2_contract(self):
  contract=json.loads((self.root/'deploy/V2_RELEASE_CONTRACT.json').read_text())
  service=(self.root/'deploy/systemd-v2/signal-lattice-v2-loop.service').read_text()
  timer=(self.root/'deploy/systemd-v2/signal-lattice-v2-loop.timer').read_text()
  self.assertEqual(contract['install_root'],'/opt/signal-lattice-v2')
  self.assertEqual(contract['version_source'],'pyproject.toml:[project].version')
  self.assertIn('Type=oneshot',service)
  self.assertIn('signal-lattice once',service)
  self.assertNotIn('Restart=always',service)
  self.assertIn('OnUnitInactiveSec=60',timer)
  self.assertIn('Unit=signal-lattice-v2-loop.service',timer)
 def test_required_schemas_and_northstar_fixtures(self):
  for name in ('skill_signal.schema.json','market_snapshot.schema.json','recommendation_snapshot.schema.json','public_release_receipt.schema.json','delivery_result.schema.json'):
   json.loads((self.root/'schemas'/name).read_text())
  for name in ('market_snapshot.json','commercial_signal.json','bottleneck_signal.json'):
   json.loads((self.root/'fixtures/northstar'/name).read_text())
