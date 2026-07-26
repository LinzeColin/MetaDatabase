#!/usr/bin/env python3
from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import time
import unittest
import urllib.request
from pathlib import Path


KIT = Path(__file__).resolve().parents[1]
SCRIPTS = KIT / "scripts"
SIMULATORS = KIT / "simulators"
sys.path.insert(0, str(SCRIPTS))

from scope_policy import ScopeViolation, load_policy, validate_attestation  # noqa: E402
from secret_scan import scan  # noqa: E402


class ExternalAdapterTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.policy_path = KIT / "config/identity-scope.policy.json"
        cls.policy = load_policy(cls.policy_path)
        cls.server = subprocess.Popen(
            [
                sys.executable,
                str(SIMULATORS / "provider-api-simulator.py"),
                "--port",
                "0",
            ],
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        assert cls.server.stdout is not None
        ready = json.loads(cls.server.stdout.readline())
        cls.base_url = f"http://127.0.0.1:{ready['port']}"

    @classmethod
    def tearDownClass(cls) -> None:
        cls.server.terminate()
        try:
            cls.server.wait(timeout=5)
        except subprocess.TimeoutExpired:
            cls.server.kill()
            cls.server.wait(timeout=5)

    def run_adapter(self, *arguments: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [
                sys.executable,
                str(SCRIPTS / "cloudflare_adapter.py"),
                "--policy",
                str(self.policy_path),
                *arguments,
            ],
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
        )

    def state(self) -> dict[str, object]:
        with urllib.request.urlopen(self.base_url + "/__state", timeout=5) as response:
            return json.loads(response.read())["result"]

    def test_cloudflare_plan_access_first_dns_last(self) -> None:
        result = self.run_adapter("plan")
        self.assertEqual(result.returncode, 0, result.stderr)
        plan = json.loads(result.stdout)
        steps = [item["id"] for item in plan["steps"]]
        self.assertEqual(
            steps,
            ["access_application", "access_policy", "r2_bucket", "analytics", "dns"],
        )
        self.assertTrue(plan["steps"][-1]["proxied"])
        self.assertEqual(
            plan["steps"][-1]["requires_completed"],
            ["access_application", "access_policy"],
        )
        self.assertEqual(plan["steps"][3]["status"], "activation_pending")

    def test_cloudflare_mock_apply_is_idempotent(self) -> None:
        results = []
        for _ in range(2):
            result = self.run_adapter(
                "apply", "--transport", "mock", "--api-base-url", self.base_url
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            results.append(json.loads(result.stdout))
        self.assertTrue(all(item["status"] == "simulator_verified" for item in results))
        self.assertTrue(all(item["real_write"] is False for item in results))
        state = self.state()
        self.assertEqual(len(state["apps"]), 1)
        self.assertEqual(len(state["buckets"]), 1)
        self.assertEqual(len(state["dns_records"]), 1)
        app = state["apps"][0]
        self.assertEqual(app["domain"], "cyberboss.linzezhang.com")
        self.assertEqual(app["policies"][1]["decision"], "non_identity")
        self.assertEqual(
            set(app["policies"][1]["include"][0]),
            {"service_token"},
        )
        self.assertNotIn("bypass", json.dumps(app).lower())
        self.assertNotIn("everyone", json.dumps(app).lower())
        log = state["operation_log"]
        dns_positions = [index for index, value in enumerate(log) if value == "dns"]
        access_positions = [
            index for index, value in enumerate(log) if value == "access_policy"
        ]
        self.assertEqual(len(dns_positions), 2)
        self.assertEqual(len(access_positions), 2)
        self.assertTrue(all(access < dns for access, dns in zip(access_positions, dns_positions)))

    def test_broad_or_wrong_attestations_are_rejected(self) -> None:
        good = {
            "schema_version": 1,
            "provider": "cloudflare",
            "resource": "dns",
            "resource_scope": "zone:linzezhang.com",
            "permissions": ["DNS Write"],
            "broad_account_write": False,
            "unrelated_write_permissions": [],
        }
        validate_attestation(
            self.policy, good, "cloudflare", "dns", "zone:linzezhang.com"
        )
        for mutation in (
            {"broad_account_write": True},
            {"resource_scope": "account:*"},
            {"permissions": ["DNS Write", "Access: Apps and Policies Write"]},
            {"unrelated_write_permissions": ["Workers Scripts Write"]},
        ):
            candidate = dict(good)
            candidate.update(mutation)
            with self.assertRaises(ScopeViolation):
                validate_attestation(
                    self.policy,
                    candidate,
                    "cloudflare",
                    "dns",
                    "zone:linzezhang.com",
                )

    def test_missing_real_slots_are_activation_pending_not_global_wait(self) -> None:
        example = KIT / "config/provider-activation.example.json"
        result = self.run_adapter(
            "apply", "--transport", "real", "--activation-config", str(example)
        )
        self.assertEqual(result.returncode, 2)
        self.assertIn("activation_pending:missing_slot", result.stderr)
        self.assertNotIn("waiting", result.stderr.lower())

    def test_oci_mock_is_prefix_locked_immutable_and_idempotent(self) -> None:
        adapter = SCRIPTS / "oci_object_adapter.py"
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source = root / "snapshot.bin"
            source.write_bytes(b"fixture-snapshot-v1")
            base = [
                sys.executable,
                str(adapter),
                "--policy",
                str(self.policy_path),
                "--backend",
                "mock",
                "--bucket",
                "fixture-private-bucket",
                "--configured-bucket",
                "fixture-private-bucket",
                "--mock-root",
                str(root / "store"),
            ]
            key = "cyberboss-cold-backup/ovh-singapore-vps-1/snapshot.bin"
            first = subprocess.run(
                [*base, "put", key, str(source)],
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                check=False,
            )
            second = subprocess.run(
                [*base, "put", key, str(source)],
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                check=False,
            )
            self.assertEqual(first.returncode, 0, first.stderr)
            self.assertEqual(second.returncode, 0, second.stderr)
            self.assertEqual(json.loads(first.stdout)["action"], "created")
            self.assertEqual(json.loads(second.stdout)["action"], "already_present")
            wrong_bucket = subprocess.run(
                [
                    sys.executable,
                    str(adapter),
                    "--policy",
                    str(self.policy_path),
                    "--backend",
                    "mock",
                    "--bucket",
                    "other",
                    "--configured-bucket",
                    "fixture-private-bucket",
                    "--mock-root",
                    str(root / "store"),
                    "put",
                    key,
                    str(source),
                ],
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                check=False,
            )
            wrong_prefix = subprocess.run(
                [*base, "put", "other/snapshot.bin", str(source)],
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                check=False,
            )
            self.assertEqual(wrong_bucket.returncode, 2)
            self.assertEqual(wrong_prefix.returncode, 2)

    def test_secret_scanner_detects_fixture_and_accepts_clean_content(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            bad = root / "bad.txt"
            clean = root / "clean.txt"
            hostile_fixtures = {
                "private_key": "-----BEGIN " + "PRIVATE KEY-----\n",
                "github_token": "gh" + "p_" + ("A" * 24) + "\n",
                "openai_key": "sk-" + "proj-" + ("a" * 24) + "\n",
                "aws_access_key": "AK" + "IA" + ("A" * 16) + "\n",
                "jwt": (
                    "eyJ"
                    + ("a" * 12)
                    + "."
                    + "eyJ"
                    + ("b" * 12)
                    + "."
                    + ("c" * 12)
                    + "\n"
                ),
                "bearer": (
                    "Author"
                    + "ization: Bear"
                    + "er "
                    + ("fixturevalue" * 4)
                    + "\n"
                ),
                "wechat_id": "wx" + "id_" + ("fixture" * 4) + "\n",
            }
            for pattern_name, fixture in hostile_fixtures.items():
                with self.subTest(pattern_name=pattern_name):
                    bad.write_text(fixture, encoding="utf-8")
                    result = scan([bad], [])
                    self.assertEqual(
                        result["pattern_hit_counts"][pattern_name],
                        1,
                        result,
                    )
                    self.assertEqual(result["forbidden_pattern_hits"], 1, result)
            clean.write_text("slot=/etc/cyberboss/credentials/example\\n", encoding="utf-8")
            self.assertEqual(scan([clean], [])["p0_findings"], 0)


if __name__ == "__main__":
    unittest.main(verbosity=2)
