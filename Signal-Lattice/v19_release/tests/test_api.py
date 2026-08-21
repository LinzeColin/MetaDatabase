from __future__ import annotations

import json
import threading
import unittest
import urllib.error
import urllib.request
from dataclasses import replace
from datetime import datetime, timezone
from http.server import ThreadingHTTPServer
from pathlib import Path

from signal_lattice_v19.api import handler
from signal_lattice_v19.engine import V19Engine
from signal_lattice_v19.storage import RuntimeStorage

from common import fixture_settings

ROOT = Path(__file__).resolve().parents[1]


class ApiTests(unittest.TestCase):
    def test_read_only_api_and_metadata(self):
        with fixture_settings(ROOT) as (settings, state_dir):
            storage = RuntimeStorage(state_dir)
            storage.bootstrap(settings.canonical_state)
            V19Engine(settings).run_once(datetime.now(timezone.utc))
            server = ThreadingHTTPServer(("127.0.0.1", 0), handler(settings, storage))
            thread = threading.Thread(target=server.serve_forever, daemon=True)
            thread.start()
            base = f"http://127.0.0.1:{server.server_port}"
            try:
                with urllib.request.urlopen(base + "/api/v1/metadata", timeout=5) as response:
                    payload = json.loads(response.read())
                self.assertEqual(payload["version"], "0.0.0.1.43")
                self.assertEqual(payload["refresh_seconds"], 15)
                self.assertEqual(payload["ui_heartbeat_seconds"], 1)
                self.assertFalse(payload["automatic_trading"])
                with urllib.request.urlopen(base + "/api/v1/heartbeat", timeout=5) as response:
                    heartbeat = json.loads(response.read())
                self.assertEqual(heartbeat["api_state"], "通")
                self.assertEqual(heartbeat["quote_observation_seconds"], 15)
                self.assertEqual(heartbeat["ui_heartbeat_seconds"], 1)
                self.assertEqual(heartbeat["profitability_status"], "NOT_ISSUED")
                self.assertGreaterEqual(heartbeat["decision_count"], 1)
                with urllib.request.urlopen(base + "/api/v1/whitebox/skills", timeout=5) as response:
                    skills = json.loads(response.read())
                self.assertEqual(skills["mode"], "SHADOW_ONLY")
                self.assertEqual(len(skills["items"]), 6)
                request = urllib.request.Request(base + "/api/v1/report/latest", method="POST", data=b"{}")
                with self.assertRaises(urllib.error.HTTPError) as context:
                    urllib.request.urlopen(request, timeout=5)
                self.assertEqual(context.exception.code, 405)
            finally:
                server.shutdown()
                server.server_close()
                thread.join(timeout=5)


if __name__ == "__main__":
    unittest.main()
