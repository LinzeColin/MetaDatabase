import json,os,subprocess,tempfile,unittest
from pathlib import Path

class DeploymentNorthStarTests(unittest.TestCase):
 @classmethod
 def setUpClass(cls):cls.root=Path(__file__).resolve().parents[1]
 def test_shell_syntax_and_completion_contract(self):
  scripts=['deploy_northstar.sh','install_cloudflare_tunnel.sh','status_closure.sh','install_release.sh','provision_runtime.sh']
  for name in scripts:
   r=subprocess.run(['bash','-n',str(self.root/'scripts'/name)],text=True,stdout=subprocess.PIPE,stderr=subprocess.PIPE);self.assertEqual(r.returncode,0,name+':'+r.stderr)
  deploy=(self.root/'scripts/deploy_northstar.sh').read_text();self.assertIn('verify_public_release.py',deploy);self.assertIn('DELIVERY_RESULT.json',deploy);self.assertIn('status_closure.sh',deploy);self.assertIn('verify_moomoo_opend.py',deploy);self.assertIn('signal-lattice-cycle.service',deploy);self.assertIn('ingest_api_token',deploy)
 def test_cloudflare_script_does_not_replace_active_shared_service(self):
  text=(self.root/'scripts/install_cloudflare_tunnel.sh').read_text();self.assertIn('EXISTING_CLOUDFLARED_SERVICE_ACTIVE_NO_REPLACEMENT',text);self.assertNotIn('service uninstall',text)

 def test_release_install_console_script_survives_activation(self):
  with tempfile.TemporaryDirectory() as tmp:
   tmp=Path(tmp);wheel_dir=tmp/'wheel';receipt=tmp/'wheel.json';install_root=tmp/'install'
   built=subprocess.run(['python3',str(self.root/'scripts/build_wheel.py'),'--root',str(self.root),'--output-dir',str(wheel_dir),'--receipt',str(receipt)],cwd=self.root,text=True,stdout=subprocess.PIPE,stderr=subprocess.PIPE)
   self.assertEqual(built.returncode,0,built.stderr)
   wheel=next(wheel_dir.glob('*.whl'))
   env=os.environ.copy();env['SIGNAL_LATTICE_INSTALL_ROOT']=str(install_root);env['PYTHONPATH']=str(self.root/'src')
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
 def test_required_schemas_and_northstar_fixtures(self):
  for name in ('skill_signal.schema.json','market_snapshot.schema.json','recommendation_snapshot.schema.json','public_release_receipt.schema.json','delivery_result.schema.json'):
   json.loads((self.root/'schemas'/name).read_text())
  for name in ('market_snapshot.json','commercial_signal.json','bottleneck_signal.json'):
   json.loads((self.root/'fixtures/northstar'/name).read_text())
