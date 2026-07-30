from __future__ import annotations

import csv
import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from gela.io import REQUIRED_COLUMNS, load_config, load_sessions, parse_utc


def write_config(root: Path, **overrides: object) -> Path:
    config: dict[str, object] = {
        "analysis_id": "x",
        "input_csv": "input.csv",
        "output_dir": "out",
        "license_acknowledgement": True,
    }
    config.update(overrides)
    path = root / "config.json"
    path.write_text(json.dumps(config), encoding="utf-8")
    return path


def base_row(market_id: str = "A", return_type: str = "price") -> dict[str, str]:
    return {
        "market_id": market_id,
        "country_iso3": "AAA" if market_id == "A" else "BBB",
        "country_name_zh": f"市场{market_id}",
        "index_name": f"指数{market_id}",
        "instrument_type": "cash_index",
        "return_type": return_type,
        "currency": "AAA" if market_id == "A" else "BBB",
        "timezone": "Etc/UTC",
        "latitude": "0",
        "longitude": "0",
        "session_date": "2026-01-02",
        "open_ts_utc": "2026-01-02T01:00:00Z",
        "close_ts_utc": "2026-01-02T06:00:00Z",
        "close": "100",
        "source": "fixture",
        "source_symbol": market_id,
        "source_retrieved_at": "2026-01-03T00:00:00Z",
    }


def write_rows(path: Path, rows: list[dict[str, str]], extra_field: str | None = None) -> None:
    fields = list(REQUIRED_COLUMNS)
    if extra_field:
        fields.append(extra_field)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


class ValidationTests(unittest.TestCase):
    def test_non_utc_rejected(self) -> None:
        with self.assertRaises(ValueError):
            parse_utc("2026-01-01T10:00:00+10:00", "time")

    def test_causal_claims_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            with self.assertRaises(ValueError):
                load_config(write_config(Path(temp), causal_claims=True))

    def test_unknown_config_field_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            with self.assertRaises(ValueError):
                load_config(write_config(Path(temp), unexpected_field=1))

    def test_unsafe_threshold_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            with self.assertRaises(ValueError):
                load_config(write_config(Path(temp), bootstrap_repetitions=3))

    def test_duplicate_or_unsorted_horizon_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            for horizons in ([1, 1, 5], [5, 1]):
                with self.subTest(horizons=horizons), self.assertRaises(ValueError):
                    load_config(write_config(root, horizons=horizons))

    def test_generated_at_must_be_utc(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            with self.assertRaises(ValueError):
                load_config(write_config(Path(temp), generated_at="2026-01-01T10:00:00+10:00"))

    def test_output_directory_must_be_dedicated(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            with self.assertRaises(ValueError):
                load_config(write_config(Path(temp), output_dir="."))

    def test_etf_proxy_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            row = base_row()
            row["instrument_type"] = "etf"
            write_rows(root / "input.csv", [row])
            with self.assertRaisesRegex(ValueError, "cash_index"):
                load_sessions(root / "input.csv")

    def test_retrieval_before_close_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            row = base_row()
            row["source_retrieved_at"] = "2026-01-02T05:00:00Z"
            write_rows(root / "input.csv", [row])
            with self.assertRaisesRegex(ValueError, "不得早于"):
                load_sessions(root / "input.csv")

    def test_mixed_return_type_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            write_rows(root / "input.csv", [base_row("A", "price"), base_row("B", "total_return")])
            with self.assertRaisesRegex(ValueError, "不得混用"):
                load_sessions(root / "input.csv")

    def test_extra_csv_column_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            row = base_row()
            row["hidden"] = "pollution"
            write_rows(root / "input.csv", [row], extra_field="hidden")
            with self.assertRaisesRegex(ValueError, "未声明列"):
                load_sessions(root / "input.csv")


if __name__ == "__main__":
    unittest.main()
