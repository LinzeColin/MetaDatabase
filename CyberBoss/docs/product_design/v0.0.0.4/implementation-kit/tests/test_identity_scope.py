#!/usr/bin/env python3
from __future__ import annotations

import json
import hashlib
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


KIT = Path(__file__).resolve().parents[1]
SCRIPTS = KIT / "scripts"
SIMULATORS = KIT / "simulators"
sys.path.insert(0, str(SCRIPTS))

from scope_policy import (  # noqa: E402
    ScopeViolation,
    load_policy,
    validate_code_scope,
    validate_data_scope,
    validate_object_scope,
)


class IdentityScopeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.policy_path = KIT / "config/identity-scope.policy.json"
        cls.policy = load_policy(cls.policy_path)

    def assert_scope_rejected(self, callback) -> None:
        with self.assertRaises(ScopeViolation):
            callback()

    def test_canonical_code_scope(self) -> None:
        validate_code_scope(
            self.policy,
            "LinzeColin/MetaDatabase",
            "CyberBoss",
            "cyberboss",
            ["CyberBoss", "CyberBoss/app/src/index.js"],
        )

    def test_code_scope_negative_matrix(self) -> None:
        cases = [
            ("Other/Repo", "CyberBoss", "cyberboss", ["CyberBoss/a"]),
            ("LinzeColin/MetaDatabase", "Other", "cyberboss", ["CyberBoss/a"]),
            ("LinzeColin/MetaDatabase", "CyberBoss", "root", ["CyberBoss/a"]),
            ("LinzeColin/MetaDatabase", "CyberBoss", "cyberboss", [".github/a"]),
            ("LinzeColin/MetaDatabase", "CyberBoss", "cyberboss", ["CyberBoss/../README.md"]),
            ("LinzeColin/MetaDatabase", "CyberBoss", "cyberboss", ["/CyberBoss/a"]),
        ]
        for repository, subpath, alias, paths in cases:
            with self.subTest(repository=repository, subpath=subpath, alias=alias, paths=paths):
                self.assert_scope_rejected(
                    lambda: validate_code_scope(
                        self.policy, repository, subpath, alias, paths
                    )
                )

    def test_private_database_scope_and_operations(self) -> None:
        self.assertEqual(self.policy["code"]["execution_identity"], "cyberboss")
        self.assertEqual(
            self.policy["data"]["execution_identity"], "cyberboss-data"
        )
        self.assertFalse(
            self.policy["identity_separation"][
                "code_identity_can_execute_data_client"
            ]
        )
        self.assertFalse(
            self.policy["identity_separation"][
                "data_identity_can_modify_code_workspace"
            ]
        )
        for operation in ("ingest", "get", "list", "verify"):
            validate_data_scope(
                self.policy,
                "LinzeColin/Private-Database",
                "main",
                "Private-MetaDatabase",
                "CyberBoss",
                operation,
            )

    def test_private_database_negative_matrix(self) -> None:
        cases = [
            ("LinzeColin/Other", "main", "Private-MetaDatabase", "CyberBoss", "get"),
            ("LinzeColin/Private-Database", "dev", "Private-MetaDatabase", "CyberBoss", "get"),
            ("LinzeColin/Private-Database", "main", "Private-AgentDatabase", "CyberBoss", "get"),
            ("LinzeColin/Private-Database", "main", "Private-MetaDatabase", "Other", "get"),
            ("LinzeColin/Private-Database", "main", "Private-MetaDatabase", "CyberBoss", "put"),
            ("LinzeColin/Private-Database", "main", "Private-MetaDatabase", "CyberBoss", "delete"),
            ("LinzeColin/Private-Database", "main", "Private-MetaDatabase", "CyberBoss", "clone"),
        ]
        for case in cases:
            with self.subTest(case=case):
                self.assert_scope_rejected(
                    lambda case=case: validate_data_scope(self.policy, *case)
                )

    def test_object_scope_negative_matrix(self) -> None:
        validate_object_scope(
            self.policy,
            "r2",
            "cyberboss-cold",
            "ovh-singapore-vps-1/snapshots/release.tar.zst",
        )
        validate_object_scope(
            self.policy,
            "oci",
            "fixture-private-bucket",
            "cyberboss-cold-backup/ovh-singapore-vps-1/release.tar.zst",
            "fixture-private-bucket",
        )
        cases = [
            ("r2", "other", "ovh-singapore-vps-1/a", None),
            ("r2", "cyberboss-cold", "other/a", None),
            ("r2", "cyberboss-cold", "../ovh-singapore-vps-1/a", None),
            ("oci", "other", "cyberboss-cold-backup/ovh-singapore-vps-1/a", "expected"),
            ("oci", "expected", "other/a", "expected"),
            ("oci", "expected", "cyberboss-cold-backup/ovh-singapore-vps-1/a", None),
        ]
        for provider, bucket, key, configured in cases:
            with self.subTest(provider=provider, bucket=bucket, key=key):
                self.assert_scope_rejected(
                    lambda provider=provider, bucket=bucket, key=key, configured=configured: validate_object_scope(
                        self.policy, provider, bucket, key, configured
                    )
                )

    def test_credential_inventory_has_slots_not_values(self) -> None:
        inventory = json.loads(
            (KIT / "config/credential-slots.json").read_text(encoding="utf-8")
        )
        self.assertFalse(inventory["rules"]["values_in_repository"])
        self.assertFalse(inventory["rules"]["values_in_environment"])
        identifiers = {item["id"] for item in inventory["slots"]}
        required = {
            "private-db-gh-login",
            "cloudflare-access-api-token",
            "cloudflare-dns-api-token",
            "cloudflare-r2-api-token",
            "r2-access-key-id",
            "r2-secret-access-key",
            "oci-config",
            "oci-private-key",
            "oci-bucket-name",
        }
        self.assertTrue(required <= identifiers)
        self.assertTrue(
            all(item["activation_status"] == "activation_pending" for item in inventory["slots"])
        )
        private_db = next(
            item for item in inventory["slots"] if item["id"] == "private-db-gh-login"
        )
        self.assertEqual(private_db["execution_identity"], "cyberboss-data")
        self.assertEqual(
            private_db["path"], "/var/lib/cyberboss-data/.config/gh/hosts.yml"
        )
        serialized = json.dumps(inventory)
        self.assertNotIn("BEGIN PRIVATE KEY", serialized)
        self.assertNotRegex(serialized, r"gh[pousr]_[A-Za-z0-9]{20,}")

    def test_private_db_wrapper_validates_client_without_execution(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            client = root / "private_db_client.py"
            client.write_text(
                "REPO='LinzeColin/Private-Database'\n"
                "BRANCH='main'\n"
                "AREAS={'Private-MetaDatabase'}\n"
                "def fixture():\n"
                "    sub.add_parser(\"ingest\")\n"
                "    sub.add_parser(\"get\")\n"
                "    sub.add_parser(\"list\")\n"
                "    sub.add_parser(\"verify\")\n",
                encoding="utf-8",
            )
            versions = root / "versions.json"
            versions.write_text(
                json.dumps(
                    {
                        "schema_version": 1,
                        "task_id": "CB-120",
                        "private_db_client": {
                            "access_mode": "no_clone_client",
                            "sha256": hashlib.sha256(client.read_bytes()).hexdigest(),
                        },
                    }
                ),
                encoding="utf-8",
            )
            result = subprocess.run(
                [
                    sys.executable,
                    str(SCRIPTS / "private_db_client_safe.py"),
                    "--policy",
                    str(self.policy_path),
                    "--versions",
                    str(versions),
                    "--client",
                    str(client),
                    "--domain",
                    "CyberBoss",
                    "list",
                    "Private-MetaDatabase",
                ],
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                check=False,
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            plan = json.loads(result.stdout)
            self.assertEqual(plan["status"], "plan_only")
            self.assertFalse(plan["real_data_operation"])
            self.assertTrue(plan["no_clone"])

    def test_simulators_reject_wrong_domain_bucket_and_prefix(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source = root / "event.json"
            source.write_text('{"fixture":true}\n', encoding="utf-8")
            db = SIMULATORS / "private-db-simulator.sh"
            init = subprocess.run([str(db), str(root / "db"), "init"], check=False)
            self.assertEqual(init.returncode, 0)
            wrong_domain = subprocess.run(
                [
                    str(db),
                    str(root / "db"),
                    "ingest",
                    "Private-MetaDatabase",
                    str(source),
                    "--domain",
                    "Other",
                ],
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                check=False,
            )
            self.assertEqual(wrong_domain.returncode, 2)
            self.assertIn("unsupported_domain", wrong_domain.stdout)

            store = SIMULATORS / "object-store-simulator.sh"
            env = dict(os.environ, SIM_OBJECT_STORE_ROOT=str(root / "objects"))
            wrong_key = subprocess.run(
                [str(store), "put", "other/a", str(source)],
                env=env,
                stdout=subprocess.PIPE,
                text=True,
                check=False,
            )
            self.assertEqual(wrong_key.returncode, 2)
            wrong_bucket = subprocess.run(
                [str(store), "put", "ovh-singapore-vps-1/a", str(source)],
                env=dict(env, SIM_OBJECT_STORE_REQUEST_BUCKET="other"),
                stdout=subprocess.PIPE,
                text=True,
                check=False,
            )
            self.assertEqual(wrong_bucket.returncode, 2)


if __name__ == "__main__":
    unittest.main(verbosity=2)
