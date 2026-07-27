from __future__ import annotations

import json
import shutil
import sys
import tempfile
import unittest
from unittest import mock
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from gela.analysis import analyze
from gela.io import file_sha256, load_config, load_sessions
from gela.render import REQUIRED_OUTPUTS, render_outputs
from gela.validation import verify_output


class PipelineTests(unittest.TestCase):
    def test_known_correlation_direction_and_offline_output(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            target = Path(temp)
            source_config = json.loads((ROOT / "examples" / "config.selftest.json").read_text(encoding="utf-8"))
            shutil.copy2(ROOT / "examples" / source_config["input_csv"], target / "input.csv")
            source_config["input_csv"] = "input.csv"
            source_config["output_dir"] = "out"
            config_path = target / "config.json"
            config_path.write_text(json.dumps(source_config), encoding="utf-8")
            config = load_config(config_path)
            markets, warnings = load_sessions(config.input_csv)
            result = analyze(markets, config)
            render_outputs(result, config, file_sha256(config.input_csv), file_sha256(config_path), warnings)
            self.assertEqual(verify_output(config.output_dir)["status"], "PASS")
            self.assertTrue(all((config.output_dir / name).is_file() for name in REQUIRED_OUTPUTS))

            # A complete prior GELA output may be replaced through a staged rollback-safe swap; stale content must not survive.
            stale_summary = config.output_dir / "summary.md"
            stale_summary.write_text("STALE-MARKER", encoding="utf-8")
            render_outputs(result, config, file_sha256(config.input_csv), file_sha256(config_path), warnings)
            self.assertEqual(verify_output(config.output_dir)["status"], "PASS")
            self.assertNotIn("STALE-MARKER", stale_summary.read_text(encoding="utf-8"))

            correlations = result["confirmed_co_movements"]
            self.assertTrue(
                any(
                    item["market_a"] == "SYN_A"
                    and item["market_b"] == "SYN_B"
                    and item["horizon"] == 1
                    for item in correlations
                )
            )
            self.assertTrue(all(item["market_a"] < item["market_b"] for item in result["co_movement"]))

            edges = result["confirmed_edges"]
            self.assertTrue(
                any(
                    edge["source_market"] == "SYN_A"
                    and edge["target_market"] == "SYN_B"
                    and edge["horizon"] == 1
                    for edge in edges
                )
            )
            self.assertFalse(
                any(
                    edge["source_market"] == "SYN_B"
                    and edge["target_market"] == "SYN_A"
                    and edge["horizon"] == 1
                    for edge in edges
                )
            )
            expected_co = 3 * len(config.horizons)
            expected_lead = 6 * len(config.horizons) * len(config.source_lags)
            self.assertEqual(result["counts"]["co_movement_hypotheses"], expected_co)
            self.assertEqual(result["counts"]["lead_lag_hypotheses"], expected_lead)

    def test_output_tamper_and_directory_pollution_detected(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            target = Path(temp)
            source_config = json.loads((ROOT / "examples" / "config.selftest.json").read_text(encoding="utf-8"))
            shutil.copy2(ROOT / "examples" / source_config["input_csv"], target / "input.csv")
            source_config["input_csv"] = "input.csv"
            source_config["output_dir"] = "out"
            config_path = target / "config.json"
            config_path.write_text(json.dumps(source_config), encoding="utf-8")
            config = load_config(config_path)
            markets, warnings = load_sessions(config.input_csv)
            result = analyze(markets, config)
            render_outputs(result, config, file_sha256(config.input_csv), file_sha256(config_path), warnings)

            html_path = config.output_dir / "atlas.html"
            html_path.write_text(html_path.read_text(encoding="utf-8").replace(
                '"analysis_id": "synthetic-selftest"', '"analysis_id": "tampered"', 1
            ), encoding="utf-8")
            self.assertEqual(verify_output(config.output_dir)["status"], "FAIL")

            shutil.rmtree(config.output_dir)
            config.output_dir.mkdir()
            (config.output_dir / "foreign.txt").write_text("do not overwrite", encoding="utf-8")
            with self.assertRaises(ValueError):
                render_outputs(result, config, file_sha256(config.input_csv), file_sha256(config_path), warnings)

    def test_output_cutover_failure_restores_previous_complete_output(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            target = Path(temp)
            source_config = json.loads((ROOT / "examples" / "config.selftest.json").read_text(encoding="utf-8"))
            shutil.copy2(ROOT / "examples" / source_config["input_csv"], target / "input.csv")
            source_config["input_csv"] = "input.csv"
            source_config["output_dir"] = "out"
            config_path = target / "config.json"
            config_path.write_text(json.dumps(source_config), encoding="utf-8")
            config = load_config(config_path)
            markets, warnings = load_sessions(config.input_csv)
            result = analyze(markets, config)
            render_outputs(result, config, file_sha256(config.input_csv), file_sha256(config_path), warnings)
            previous = (config.output_dir / "analysis.json").read_bytes()

            concrete_path_type = type(config.output_dir)
            original_replace = concrete_path_type.replace

            def fail_new_directory_cutover(self: Path, target_path: Path) -> Path:
                if self.name.startswith(f".{config.output_dir.name}.gela-stage-") and Path(target_path) == config.output_dir:
                    raise OSError("injected cutover failure")
                return original_replace(self, target_path)

            with mock.patch.object(concrete_path_type, "replace", new=fail_new_directory_cutover):
                with self.assertRaisesRegex(OSError, "injected cutover failure"):
                    render_outputs(result, config, file_sha256(config.input_csv), file_sha256(config_path), warnings)

            self.assertTrue(config.output_dir.is_dir())
            self.assertEqual((config.output_dir / "analysis.json").read_bytes(), previous)
            self.assertEqual(verify_output(config.output_dir)["status"], "PASS")
            self.assertFalse(list(config.output_dir.parent.glob(f".{config.output_dir.name}.gela-backup-*")))


    def test_output_symlink_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            target = Path(temp)
            real_output = target / "real-out"
            real_output.mkdir()
            linked_output = target / "linked-out"
            try:
                linked_output.symlink_to(real_output, target_is_directory=True)
            except (OSError, NotImplementedError):
                self.skipTest("当前平台不支持创建目录符号链接")
            report = verify_output(linked_output)
            self.assertEqual(report["status"], "FAIL")
            self.assertTrue(any("符号链接" in item for item in report["errors"]))



if __name__ == "__main__":
    unittest.main()
