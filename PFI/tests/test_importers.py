from __future__ import annotations

import io
import zipfile
from decimal import Decimal
from pathlib import Path

import pytest

from pfi_os.importers import ImportFormatError, detect_source, load_data_dir, parse_alipay, parse_cba

ALIPAY_EXPORT = """导出信息：
姓名：示例
共2笔记录
交易时间,交易分类,交易对方,对方账号,商品说明,收/支,金额,收/付款方式,交易状态,交易订单号,商家订单号,备注,
2026-06-01 08:15:00,餐饮美食,早餐店,,早餐,支出,12.50,余额,交易成功,O1,,,
2026-06-02 09:00:00,退款,早餐店,,退款,收入,"1,002.50",余额,退款成功,O2,,,
导出时间：[2026-06-03 10:00:00]
"""


def test_alipay_export_skips_preamble_footer_and_signs_amounts() -> None:
    rows = parse_alipay(ALIPAY_EXPORT.encode("utf-8"), "a.csv")
    assert [(r.order_id, r.amount, r.currency, r.month) for r in rows] == [
        ("O1", Decimal("-12.50"), "CNY", "2026-06"),
        ("O2", Decimal("1002.50"), "CNY", "2026-06"),
    ]
    assert rows[0].source_category == "餐饮美食"
    assert rows[0].counterparty == "早餐店"


def test_alipay_real_exports_are_gb18030_encoded() -> None:
    rows = parse_alipay(ALIPAY_EXPORT.encode("gb18030"), "gbk.csv")
    assert len(rows) == 2
    assert rows[0].description == "早餐"


def test_alipay_zip_is_read_through() -> None:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        archive.writestr("alipay_record.csv", ALIPAY_EXPORT.encode("gb18030"))
    assert len(parse_alipay(buffer.getvalue(), "alipay.zip")) == 2


def test_alipay_without_header_names_the_missing_columns() -> None:
    with pytest.raises(ImportFormatError, match="找不到支付宝表头"):
        parse_alipay("a,b,c\n1,2,3\n".encode(), "bad.csv")


def test_alipay_bad_amount_reports_file_and_line() -> None:
    text = "交易时间,收/支,金额\n2026-06-01 08:00:00,支出,abc\n"
    with pytest.raises(ImportFormatError, match="bad.csv 第 2 行: 金额 'abc' 不是数字"):
        parse_alipay(text.encode(), "bad.csv")


def test_cba_netbank_headerless_export() -> None:
    text = '01/06/2026,"-12.50","WOOLWORTHS SYDNEY","+100.00"\n02/06/2026,"+50.00","Salary","+150.00"\n'
    rows = parse_cba(text.encode(), "cba.csv")
    assert [(r.occurred_at.date().isoformat(), r.amount, r.direction, r.currency) for r in rows] == [
        ("2026-06-01", Decimal("-12.50"), "支出", "AUD"),
        ("2026-06-02", Decimal("50.00"), "收入", "AUD"),
    ]


def test_cba_headered_debit_credit_export() -> None:
    text = "Date,Description,Debit,Credit\n27/06/2026,Salary,,3200.00\n28/06/2026,Coles,45.10,\n"
    rows = parse_cba(text.encode(), "cba.csv")
    assert [r.amount for r in rows] == [Decimal("3200.00"), Decimal("-45.10")]


def test_cba_unrecognised_header_is_rejected_with_reason() -> None:
    with pytest.raises(ImportFormatError, match="不是可识别的 CBA CSV"):
        parse_cba(b"foo,bar\n1,2\n", "cba.csv")


def test_detect_source_by_content_and_name(tmp_path: Path) -> None:
    assert detect_source(Path("x.csv"), ALIPAY_EXPORT.encode("gb18030")) == "alipay"
    assert detect_source(Path("x.csv"), b'01/06/2026,"-1.00","A","+1.00"\n') == "cba"
    assert detect_source(Path("notes.csv"), b"a,b\n1,2\n") is None


def test_load_data_dir_dedupes_across_files_but_keeps_same_day_repeats(tmp_path: Path) -> None:
    (tmp_path / "a.csv").write_text(ALIPAY_EXPORT, encoding="utf-8")
    (tmp_path / "sub").mkdir()
    (tmp_path / "sub" / "a_copy.csv").write_text(ALIPAY_EXPORT, encoding="utf-8")
    coffee = '01/06/2026,"-4.50","CAFE","+10.00"\n01/06/2026,"-4.50","CAFE","+5.50"\n'
    (tmp_path / "cba1.csv").write_text(coffee, encoding="utf-8")
    (tmp_path / "cba2.csv").write_text(coffee, encoding="utf-8")
    (tmp_path / "unrelated.csv").write_text("a,b\n1,2\n", encoding="utf-8")

    loaded = load_data_dir(tmp_path)

    assert len(loaded.transactions) == 4  # 2 支付宝 + 同日两杯咖啡
    assert loaded.duplicates_dropped == 4
    assert loaded.skipped_files == ["unrelated.csv"]


def test_load_data_dir_missing_dir_says_how_to_fix(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError, match="PFI_DATA_DIR"):
        load_data_dir(tmp_path / "nope")
