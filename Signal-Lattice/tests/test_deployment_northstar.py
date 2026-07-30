import json,subprocess,unittest
from pathlib import Path

class DeploymentNorthStarTests(unittest.TestCase):
 @classmethod
 def setUpClass(cls):cls.root=Path(__file__).resolve().parents[1]
 def test_shell_syntax_and_completion_contract(self):
  scripts=['deploy_northstar.sh','install_cloudflare_tunnel.sh','status_closure.sh','install_release.sh','provision_runtime.sh']
  for name in scripts:
   r=subprocess.run(['bash','-n',str(self.root/'scripts'/name)],text=True,stdout=subprocess.PIPE,stderr=subprocess.PIPE);self.assertEqual(r.returncode,0,name+':'+r.stderr)
  deploy=(self.root/'scripts/deploy_northstar.sh').read_text();self.assertIn('verify_public_release.py',deploy);self.assertIn('DELIVERY_RESULT.json',deploy);self.assertIn('status_closure.sh',deploy);self.assertIn('verify_northstar_repair_authorization.py',deploy);self.assertIn('ingest_api_token',deploy)
 def test_cloudflare_script_does_not_replace_active_shared_service(self):
  text=(self.root/'scripts/install_cloudflare_tunnel.sh').read_text();self.assertIn('EXISTING_CLOUDFLARED_SERVICE_ACTIVE_NO_REPLACEMENT',text);self.assertNotIn('service uninstall',text)
 def test_required_schemas_and_northstar_fixtures(self):
  for name in ('skill_signal.schema.json','market_snapshot.schema.json','recommendation_snapshot.schema.json','public_release_receipt.schema.json','delivery_result.schema.json'):
   json.loads((self.root/'schemas'/name).read_text())
  for name in ('market_snapshot.json','commercial_signal.json','bottleneck_signal.json'):
   json.loads((self.root/'fixtures/northstar'/name).read_text())
