from __future__ import annotations

import importlib.util
import base64
import json
import os
import sqlite3
import subprocess
import sys
import tempfile
import unittest
from contextlib import contextmanager
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


INSTALLER = load_module("wrp_platform_installer", ROOT / "service/install_platform.py")
OPS = load_module("wrp_platform_ops", ROOT / "service/scripts/platform_ops.py")
PREFLIGHT = load_module("wrp_platform_preflight", ROOT / "service/scripts/platform_preflight.py")


@contextmanager
def environment(values: dict[str, str]):
    before = os.environ.copy()
    os.environ.update(values)
    try:
        yield
    finally:
        os.environ.clear()
        os.environ.update(before)


class PlatformOperationsTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.database = self.root / "state/platform.sqlite3"
        self.database.parent.mkdir(parents=True)
        schema = (ROOT / "service/schema.sql").read_text(encoding="utf-8")
        with sqlite3.connect(self.database) as connection:
            connection.executescript(schema)

    def tearDown(self):
        self.temp.cleanup()

    def test_installer_prepares_versioned_release_without_generating_secrets(self):
        completed = subprocess.run(
            [sys.executable, str(ROOT / "service/install_platform.py"), "--root", str(self.root / "install")],
            cwd=ROOT, text=True, capture_output=True, check=True,
        )
        result = json.loads(completed.stdout)
        self.assertEqual(result["status"], "PREPARED")
        self.assertEqual(result["version"], "v0.0.0.1.8")
        release = self.root / "install/opt/weread-port/releases/0.0.0.1.8"
        current = self.root / "install/opt/weread-port/current"
        env_file = self.root / "install/etc/weread-port/platform.env"
        self.assertTrue((release / "service/server.mjs").is_file())
        self.assertTrue(current.is_symlink())
        self.assertEqual(current.resolve(), release.resolve())
        self.assertEqual(env_file.stat().st_mode & 0o777, 0o600)
        text = env_file.read_text(encoding="utf-8")
        for key in ("WRP_SESSION_PEPPER", "WRP_CREDENTIAL_PEPPER", "WRP_KEYRING_JSON", "WRP_INTERNAL_PROXY_SECRET"):
            self.assertIn(f"{key}=\n", text)
        self.assertNotIn("wrk-", text)
        self.assertIn("WRP_R2_SECRET_ACCESS_KEY", result["missingDeploymentInputs"])
        self.assertTrue((self.root / "install/etc/systemd/system/weread-port-platform.service").is_file())

    def test_preflight_is_secret_safe_and_closes_all_last_mile_inputs(self):
        private_db = self.root / "Private-Database"
        (private_db / ".git").mkdir(parents=True)
        secret = base64.b64encode(b"x" * 32).decode("ascii")
        values = {
            "NODE_ENV": "production",
            "WRP_PUBLIC_BASE_URL": "https://weread-port.linzezhang35.chatgpt.site",
            "WRP_SERVICE_HOST": "127.0.0.1",
            "WRP_SERVICE_PORT": "8788",
            "WRP_DATABASE_PATH": str(self.root / "state/platform.sqlite3"),
            "WRP_OBJECT_STORE_MODE": "r2",
            "WRP_SESSION_PEPPER": secret,
            "WRP_CREDENTIAL_PEPPER": secret,
            "WRP_KEYRING_JSON": json.dumps({"k1": secret}),
            "WRP_ACTIVE_KEY_ID": "k1",
            "WRP_INTERNAL_PROXY_SECRET": "p" * 48,
            "WRP_R2_ENDPOINT": "https://example.r2.cloudflarestorage.com",
            "WRP_R2_BUCKET": "weread-port-private",
            "WRP_R2_ACCESS_KEY_ID": "access-key-not-secret-value",
            "WRP_R2_SECRET_ACCESS_KEY": "r" * 40,
            "WRP_GOOGLE_CLIENT_ID": "google-client-id",
            "WRP_GOOGLE_CLIENT_SECRET": "g" * 32,
            "WRP_GITHUB_CLIENT_ID": "github-app-client-id",
            "WRP_GITHUB_CLIENT_SECRET": "h" * 32,
            "WRP_NOTION_CLIENT_ID": "notion-client-id",
            "WRP_NOTION_CLIENT_SECRET": "n" * 32,
            "WRP_PRIVATE_DATABASE_WORKTREE": str(private_db),
            "WRP_UPSTREAM_TIMEOUT_MS": "15000",
            "WRP_UPSTREAM_RETRY_ATTEMPTS": "2",
            "WRP_AUTH_FAILURE_LIMIT": "8",
            "WRP_AUTH_LOCK_SECONDS": "900",
            "WRP_IMPORT_LEASE_SECONDS": "300",
            "WRP_WORKER_STALE_SECONDS": "30",
        }
        result = PREFLIGHT.check_environment(values, require_paths=True)
        self.assertEqual(result["status"], "PASS")
        self.assertFalse(result["secretValuesPrinted"])
        self.assertEqual(result["oauthCallbackUrls"]["github"], "https://weread-port.linzezhang35.chatgpt.site/api/platform/v1/oauth/github/callback")
        encoded = json.dumps(result, ensure_ascii=False)
        self.assertNotIn(secret, encoded)
        self.assertNotIn("r" * 40, encoded)

    def test_preflight_rejects_placeholders_public_bind_and_missing_private_database(self):
        result = PREFLIGHT.check_environment({
            "NODE_ENV": "development",
            "WRP_PUBLIC_BASE_URL": "http://example.invalid/path",
            "WRP_SERVICE_HOST": "0.0.0.0",
            "WRP_SERVICE_PORT": "8788",
            "WRP_DATABASE_PATH": "relative.sqlite3",
            "WRP_OBJECT_STORE_MODE": "file",
        }, require_paths=True)
        self.assertEqual(result["status"], "BLOCKED")
        codes = {item["code"] for item in result["blockers"]}
        self.assertTrue({"MISSING", "NODE_ENV", "PUBLIC_URL", "BIND_ADDRESS", "DATABASE_PATH", "OBJECT_MODE"}.issubset(codes))

    def test_backup_restore_check_and_fact_snapshot_are_deterministic_and_private(self):
        with sqlite3.connect(self.database) as connection:
            connection.execute("INSERT INTO accounts(id,email,display_name,created_at,updated_at) VALUES(?,?,?,?,?)", ("acct_private", "private@example.com", "私人姓名", 1, 1))
            connection.execute("INSERT INTO account_keys(account_id,wrapped_dek,key_id,updated_at) VALUES(?,?,?,?)", ("acct_private", "v1.k1.a.b.c", "k1", 1))
            connection.execute("INSERT INTO consents(account_id,behavior_analytics,recommendation_personalization,updated_at) VALUES(?,?,?,?)", ("acct_private", 0, 0, 1))
            connection.execute("INSERT INTO weread_sync_state(account_id,updated_at) VALUES(?,?)", ("acct_private", 1))
        with environment({"WRP_DATABASE_PATH": str(self.database)}):
            manifest = OPS.backup()
            snapshot = self.database.parent / "snapshots" / manifest["snapshot"]
            self.assertTrue(snapshot.is_file())
            self.assertTrue(OPS.verify_snapshot(snapshot)["ok"])
            facts = OPS.fact_snapshot()
        encoded = json.dumps(facts, ensure_ascii=False)
        self.assertEqual(facts["counts"]["accounts"], 1)
        self.assertFalse(facts["dataBoundary"]["containsUserContent"])
        self.assertNotIn("private@example.com", encoded)
        self.assertNotIn("私人姓名", encoded)
        self.assertNotIn("acct_private", encoded)
        self.assertNotIn("wrapped_dek", encoded)

    def test_restore_check_refuses_corruption_without_touching_live_database(self):
        corrupt = self.root / "corrupt.sqlite3"
        corrupt.write_bytes(b"not sqlite")
        with environment({"WRP_DATABASE_PATH": str(self.database)}):
            before = OPS.sha256(self.database)
            with self.assertRaises(sqlite3.DatabaseError):
                OPS.verify_snapshot(corrupt)
            self.assertEqual(OPS.sha256(self.database), before)
            self.assertEqual(OPS.integrity(self.database), "ok")

    def test_runtime_contract_has_no_launchd_agent_or_model_dependency(self):
        executable_suffixes = {".js", ".mjs", ".py", ".service", ".timer"}
        files = [
            path for path in ROOT.rglob("*")
            if path.is_file()
            and path.suffix in executable_suffixes
            and "node_modules" not in path.parts
            and "__pycache__" not in path.parts
            and "tests" not in path.parts
        ]
        runtime_text = "\n".join(path.read_text(encoding="utf-8", errors="ignore") for path in files)
        self.assertNotIn("Library/LaunchAgents", runtime_text)
        self.assertNotIn("launchctl", runtime_text)
        self.assertTrue(any("systemd" in str(path) or path.suffix in {".service", ".timer"} for path in files))
        readme = (ROOT / "README.md").read_text(encoding="utf-8")
        self.assertIn("运行期不调用模型", readme)
        self.assertIn("Agent 与 Token 依赖均为零", readme)
        self.assertIn("127.0.0.1", (ROOT / "service/env/weread-port-platform.env.example").read_text(encoding="utf-8"))

    def test_caddy_reference_keeps_service_private_and_https_only(self):
        config = (ROOT / "service/reverse-proxy/caddy.reference.conf").read_text(encoding="utf-8")
        self.assertIn("reverse_proxy 127.0.0.1:8788", config)
        self.assertNotIn("http://", config)
        self.assertIn("max_size 50MB", config)


if __name__ == "__main__":
    unittest.main()
