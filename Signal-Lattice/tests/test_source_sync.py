import hashlib
import hmac
import unittest

from signal_lattice.source_sync import validate_upstream_url, verify_webhook


class T(unittest.TestCase):
    def test_hmac(self):
        body = b"{}"
        secret = b"secret"
        signature = "sha256=" + hmac.new(secret, body, hashlib.sha256).hexdigest()
        self.assertTrue(verify_webhook(secret, body, signature))
        self.assertFalse(verify_webhook(secret, body, "sha256=bad"))
        self.assertFalse(verify_webhook(b"", body, signature))

    def test_upstream_url_allowlist(self):
        self.assertEqual(
            validate_upstream_url(
                "https://raw.githubusercontent.com/LinzeColin/AgentDatabase/abc/CodexSkills/index.json"
            ),
            "https://raw.githubusercontent.com/LinzeColin/AgentDatabase/abc/CodexSkills/index.json",
        )
        self.assertEqual(
            validate_upstream_url("https://api.github.com/repos/LinzeColin/AgentDatabase"),
            "https://api.github.com/repos/LinzeColin/AgentDatabase",
        )

    def test_upstream_url_rejects_ssrf_shapes(self):
        invalid = [
            "http://raw.githubusercontent.com/a/b",
            "https://127.0.0.1/private",
            "https://localhost/private",
            "https://user:pass@github.com/a/b",
            "https://github.com:444/a/b",
            "https://github.com/a/../private",
            "https://github.com/a/%2e%2e/private",
            "https://github.com/a/b#fragment",
            "file:///etc/passwd",
        ]
        for url in invalid:
            with self.subTest(url=url), self.assertRaises(ValueError):
                validate_upstream_url(url)
