import os
import subprocess
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

class CloudDeploymentTests(unittest.TestCase):
    def test_cloudflared_unit_uses_token_file_and_loopback_api_dependency(self):
        text=(ROOT/'deploy/systemd/signal-lattice-cloudflared.service').read_text()
        self.assertIn('--token-file /etc/signal-lattice/credentials/cloudflare_tunnel_token', text)
        self.assertIn('Requires=signal-lattice-api.service', text)
        self.assertIn('User=cloudflared', text)

    def test_deploy_northstar_has_public_url_completion_gate(self):
        text=(ROOT/'scripts/deploy_northstar.sh').read_text()
        for token in ('verify_public_release.py','status_closure.sh','verify_deployment_claim.py','NORTH_STAR_DEPLOYED_AND_PUBLICLY_VERIFIED','CLOUDFLARE_TUNNEL_TOKEN_OR_API_CREDENTIALS_REQUIRED','verify_moomoo_opend.py','signal-lattice-cycle.service'):
            self.assertIn(token,text)
        self.assertNotIn('LIVE_ACTION=1',text)

    def test_cloudflare_configurator_rejects_unapproved_host(self):
        import importlib.util
        spec=importlib.util.spec_from_file_location('cf',ROOT/'scripts/configure_cloudflare_tunnel.py')
        mod=importlib.util.module_from_spec(spec);spec.loader.exec_module(mod)
        with self.assertRaises(mod.CloudflareError):
            mod.configure(account_id='a',zone_id='z',hostname='evil.example',origin='http://127.0.0.1:8787',tunnel_name='x',token_file=Path('/tmp/x'),api_token='t')

    def test_shell_syntax(self):
        for name in ('deploy_northstar.sh','install_cloudflared_binary.sh','ensure_cloudflared.sh','install_systemd.sh'):
            subprocess.run(['bash','-n',str(ROOT/'scripts'/name)],check=True)

if __name__=='__main__': unittest.main()
