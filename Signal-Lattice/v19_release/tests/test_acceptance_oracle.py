from __future__ import annotations

import importlib.util
import threading
import unittest
from datetime import datetime, timezone
from http.server import ThreadingHTTPServer
from pathlib import Path

from signal_lattice_v19.api import handler
from signal_lattice_v19.engine import V19Engine
from signal_lattice_v19.storage import RuntimeStorage

from common import fixture_settings

ROOT = Path(__file__).resolve().parents[1]


def acceptance_module():
    path = ROOT / "scripts" / "run_acceptance.py"
    spec = importlib.util.spec_from_file_location("signal_lattice_v19_acceptance", path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


class AcceptanceOracleTests(unittest.TestCase):
    def _serve(self, settings, storage):
        server = ThreadingHTTPServer(("127.0.0.1", 0), handler(settings, storage))
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        return server, thread, f"http://127.0.0.1:{server.server_port}"

    def test_blocked_report_fails_the_structural_oracle(self):
        with fixture_settings(ROOT) as (settings, state_dir):
            storage = RuntimeStorage(state_dir)
            storage.bootstrap(settings.canonical_state)
            V19Engine(settings).publish_failure(datetime.now(timezone.utc), RuntimeError("forced"))
            server, thread, base = self._serve(settings, storage)
            try:
                with self.assertRaisesRegex(AssertionError, "STRUCTURAL_ORACLE_FAILED"):
                    acceptance_module().run(base, verify_cadence=False, skip_stream=True)
            finally:
                server.shutdown()
                server.server_close()
                thread.join(timeout=5)

    def test_complete_fixture_report_is_structural_only_and_rejected_for_live_acceptance(self):
        with fixture_settings(ROOT) as (settings, state_dir):
            storage = RuntimeStorage(state_dir)
            storage.bootstrap(settings.canonical_state)
            V19Engine(settings).run_once(datetime.now(timezone.utc))
            server, thread, base = self._serve(settings, storage)
            try:
                result = acceptance_module().run(base, verify_cadence=False, skip_stream=True)
                self.assertEqual(result["state"], "STRUCTURAL_PASS")
                self.assertEqual(result["input_provenance"], "FIXTURE_DATA")
                self.assertEqual(result["acceptance_scope"], "STRUCTURAL_FIXTURE_ONLY")
                with self.assertRaisesRegex(AssertionError, "LIVE_PROVIDER_REQUIRED"):
                    acceptance_module().run(base, verify_cadence=False, skip_stream=True, require_live_provider=True)
            finally:
                server.shutdown()
                server.server_close()
                thread.join(timeout=5)
