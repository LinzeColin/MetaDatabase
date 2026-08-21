from __future__ import annotations

import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


class SourceContractTests(unittest.TestCase):
    def test_no_trade_context_or_order_path(self):
        text = "\n".join(path.read_text(encoding="utf-8") for path in (ROOT / "src").rglob("*.py"))
        forbidden = (
            "OpenSecTradeContext", "OpenHKTradeContext", "OpenUSTradeContext",
            "place_order(", "modify_order(", "cancel_all_order(", "unlock_trade(",
        )
        for token in forbidden:
            self.assertNotIn(token, text)

    def test_six_skills_run_before_central_decision(self):
        text = (ROOT / "src" / "signal_lattice_v19" / "engine.py").read_text(encoding="utf-8")
        self.assertLess(text.index("run_six_skills("), text.index("outcome = decide("))

    def test_fifteen_second_front_and_backend_contract(self):
        init_text = (ROOT / "src" / "signal_lattice_v19" / "__init__.py").read_text(encoding="utf-8")
        web_text = (ROOT / "web" / "app.js").read_text(encoding="utf-8")
        self.assertIn("REFRESH_SECONDS = 15", init_text)
        self.assertIn("15000", web_text)
        self.assertIn("1000", web_text)
        self.assertIn("/api/v1/heartbeat", web_text)
        tunnel = (ROOT / "deploy" / "systemd" / "signal-lattice-v19-cloudflared.service").read_text(encoding="utf-8")
        installer = (ROOT / "deploy" / "install_and_switch.sh").read_text(encoding="utf-8")
        rollback = (ROOT / "deploy" / "rollback.sh").read_text(encoding="utf-8")
        self.assertIn("Requires=signal-lattice-v19-api.service", tunnel)
        self.assertIn("signal-lattice-v19-cloudflared.service", installer)
        self.assertLess(installer.index("trap failure ERR"), installer.index("systemctl stop signal-lattice-api.service"))
        self.assertIn("signal-lattice-cloudflared.service", rollback)
        roots = [ROOT / "src", ROOT / "config", ROOT / "web", ROOT / "deploy"]
        text = "\n".join(
            path.read_text(encoding="utf-8")
            for base in roots
            for path in base.rglob("*")
            if path.is_file() and path.suffix in {".py", ".json", ".html", ".js", ".css", ".sh", ".service"}
        )
        self.assertNotIn("v0.0.0." + "20", text)

    def test_moomoo_history_export_is_quote_context_only(self):
        exporter = (ROOT / "scripts" / "export_moomoo_history.py").read_text(encoding="utf-8")
        self.assertIn("OpenQuoteContext", exporter)
        self.assertIn("request_history_kline", exporter)
        for token in ("OpenSecTradeContext", "OpenHKTradeContext", "OpenUSTradeContext", "place_order("):
            self.assertNotIn(token, exporter)

    def test_whitebox_separates_observation_and_decision_episode(self):
        source = (ROOT / "src" / "signal_lattice_v19" / "whitebox.py").read_text(encoding="utf-8")
        self.assertIn("observation_tick", source)
        self.assertIn("decision_episode", source)
        self.assertIn("material_signature", source)
        self.assertIn("SHADOW_ONLY", source)


if __name__ == "__main__":
    unittest.main()
