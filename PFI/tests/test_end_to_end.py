"""样例数据端到端：导入 → 分类 → 月报，数字逐项手算核对（见 examples/data）。"""
from __future__ import annotations

import csv
import subprocess
import sys
from decimal import Decimal
from pathlib import Path

import pytest

from pfi_os.__main__ import main
from pfi_os.classify import classify_all
from pfi_os.importers import load_data_dir
from pfi_os.report import monthly_summary

PFI_ROOT = Path(__file__).resolve().parents[1]
SAMPLE = PFI_ROOT / "examples" / "data"
D = Decimal


def summaries():
    loaded = load_data_dir(SAMPLE)
    return loaded, {(s.month, s.currency): s for s in monthly_summary(classify_all(loaded.transactions))}


def test_sample_import_counts() -> None:
    loaded, _ = summaries()
    assert len(loaded.files) == 3
    assert loaded.duplicates_dropped == 1  # SAMPLE_A010 在两份支付宝账单里各出现一次
    assert len(loaded.transactions) == 22


@pytest.mark.parametrize(
    ("key", "income", "expense", "refund", "net", "investment_net", "count", "review"),
    [
        (("2026-04", "CNY"), "3000.00", "336.50", "20.00", "2683.50", "0", 9, 0),
        (("2026-05", "CNY"), "0", "195.50", "0", "-195.50", "-1000.00", 4, 1),
        (("2026-04", "AUD"), "4500.00", "94.40", "0", "4405.60", "-2000.00", 6, 0),
        (("2026-05", "AUD"), "0", "680.00", "12.30", "-667.70", "0", 3, 1),
    ],
)
def test_sample_monthly_numbers(key, income, expense, refund, net, investment_net, count, review) -> None:
    s = summaries()[1][key]
    assert (s.income, s.expense, s.refund, s.net, s.investment_net) == (D(income), D(expense), D(refund), D(net), D(investment_net))
    assert (s.transactions, s.needs_review) == (count, review)


def test_sample_category_breakdown() -> None:
    s = summaries()[1][("2026-04", "CNY")]
    assert s.categories == {"餐饮美食": D("12.50"), "交通出行": D("4.00"), "日用百货": D("120.00"), "转账红包": D("200.00")}


def test_cli_report_from_env(monkeypatch, capsys) -> None:
    monkeypatch.setenv("PFI_DATA_DIR", str(SAMPLE))
    assert main(["report"]) == 0
    text = capsys.readouterr().out
    assert "| 2026-04 | 3,000.00 | 336.50 | 20.00 | 316.50 | 2,683.50 | — | 0.00 | 9 |" in text
    assert "| 2026-05 | 0.00 | 680.00 | 12.30 | 667.70 | -667.70 | +607.3% | 0.00 | 3 |" in text
    assert "2026-04：转账红包 200.00，日用百货 120.00，餐饮美食 12.50，交通出行 4.00" in text


def test_cli_ledger_export(tmp_path: Path) -> None:
    out = tmp_path / "ledger.csv"
    assert main(["--data-dir", str(SAMPLE), "ledger", "--out", str(out)]) == 0
    rows = list(csv.DictReader(out.open(encoding="utf-8-sig")))
    assert len(rows) == 22
    assert {r["kind"] for r in rows} == {"expense", "income", "refund", "transfer", "investment", "excluded"}


def test_cli_without_data_dir_explains(monkeypatch) -> None:
    monkeypatch.delenv("PFI_DATA_DIR", raising=False)
    with pytest.raises(SystemExit, match="PFI_DATA_DIR"):
        main(["report"])


def test_python_dash_m_entry_point() -> None:
    result = subprocess.run(
        [sys.executable, "-m", "pfi_os", "--data-dir", str(SAMPLE), "report"],
        capture_output=True, text=True, env={"PYTHONPATH": str(PFI_ROOT / "src"), "PATH": ""},
    )
    assert result.returncode == 0, result.stderr
    assert result.stdout.startswith("# PFI 月度收支报告")
