"""流水导入：支付宝账单（CSV / ZIP）与 CBA NetBank CSV → 统一的 Transaction。

金额符号约定：负数 = 钱流出，正数 = 钱流入。支付宝“不计收支”行金额取绝对值，
方向由分类器决定（通常是自有账户搬运或理财）。
"""
from __future__ import annotations

import csv
import io
import re
import sys
import zipfile
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal, InvalidOperation
from pathlib import Path

MAX_ZIP_CSV_BYTES = 100 * 1024 * 1024


class ImportFormatError(ValueError):
    """文件内容不符合预期格式；消息里写明文件、行号与原因。"""


@dataclass(frozen=True)
class Transaction:
    source: str  # "alipay" | "cba"
    occurred_at: datetime
    amount: Decimal  # 负数流出，正数流入
    currency: str
    direction: str  # 支付宝原始“收/支”；CBA 由金额符号推出“支出/收入”
    counterparty: str
    description: str
    source_category: str  # 支付宝“交易分类”；CBA 为空
    status: str
    order_id: str
    source_file: str

    @property
    def month(self) -> str:
        return self.occurred_at.strftime("%Y-%m")


def _decode(content: bytes, name: str) -> str:
    for encoding in ("utf-8-sig", "gb18030"):
        try:
            return content.decode(encoding)
        except UnicodeDecodeError:
            continue
    raise ImportFormatError(f"{name}: 既不是 UTF-8 也不是 GB18030 编码，无法读取")


def _money(text: str, where: str) -> Decimal:
    cleaned = text.strip().replace(",", "")
    for token in ("¥", "￥", "$", "元", "AUD", "CNY", " "):
        cleaned = cleaned.replace(token, "")
    negative = cleaned.startswith("(") and cleaned.endswith(")")
    cleaned = cleaned.strip("()")
    try:
        value = Decimal(cleaned)
    except InvalidOperation as exc:
        raise ImportFormatError(f"{where}: 金额 {text!r} 不是数字") from exc
    if not value.is_finite():
        raise ImportFormatError(f"{where}: 金额 {text!r} 不是有限数")
    return -value if negative else value


def _datetime(text: str, formats: tuple[str, ...], where: str) -> datetime:
    value = text.strip()
    for fmt in formats:
        try:
            return datetime.strptime(value, fmt)
        except ValueError:
            continue
    raise ImportFormatError(f"{where}: 日期 {text!r} 无法识别（支持 {', '.join(formats)}）")


# ---------------------------------------------------------------- 支付宝

ALIPAY_REQUIRED = ("交易时间", "收/支", "金额")
ALIPAY_TIME_FORMATS = ("%Y-%m-%d %H:%M:%S", "%Y/%m/%d %H:%M:%S", "%Y-%m-%d %H:%M", "%Y/%m/%d %H:%M", "%Y-%m-%d")


def _alipay_header_index(lines: list[str]) -> int | None:
    for index, line in enumerate(lines):
        if "交易时间" not in line:
            continue
        cells = {cell.strip() for cell in next(csv.reader([line]))}
        if all(name in cells for name in ALIPAY_REQUIRED):
            return index
    return None


def _zip_csv(content: bytes, name: str) -> bytes:
    with zipfile.ZipFile(io.BytesIO(content)) as archive:
        members = [info for info in archive.infolist() if info.filename.lower().endswith(".csv")]
        if len(members) != 1:
            raise ImportFormatError(f"{name}: ZIP 内应恰好有 1 个 CSV，实际 {len(members)} 个")
        if members[0].flag_bits & 0x1:
            raise ImportFormatError(f"{name}: ZIP 已加密，请先用支付宝给的解压密码解压后再放入数据目录")
        if members[0].file_size > MAX_ZIP_CSV_BYTES:
            raise ImportFormatError(f"{name}: ZIP 内 CSV 超过 100MB，拒绝展开")
        return archive.read(members[0])


def parse_alipay(content: bytes, source_file: str = "<alipay>") -> list[Transaction]:
    if zipfile.is_zipfile(io.BytesIO(content)):
        content = _zip_csv(content, source_file)
    lines = _decode(content, source_file).splitlines()
    header = _alipay_header_index(lines)
    if header is None:
        raise ImportFormatError(f"{source_file}: 找不到支付宝表头（需要列 {', '.join(ALIPAY_REQUIRED)}）")
    rows: list[Transaction] = []
    reader = csv.DictReader(lines[header:])
    for line_no, raw in enumerate(reader, start=header + 2):
        row = {str(k).strip(): (v or "").strip() for k, v in raw.items() if k is not None and str(k).strip()}
        when = row.get("交易时间", "")
        if not when or not row.get("金额"):
            continue  # 表尾说明行、空行
        where = f"{source_file} 第 {line_no} 行"
        amount = abs(_money(row["金额"], where))
        direction = row.get("收/支", "")
        if direction == "支出":
            amount = -amount
        rows.append(
            Transaction(
                source="alipay",
                occurred_at=_datetime(when, ALIPAY_TIME_FORMATS, where),
                amount=amount,
                currency="CNY",
                direction=direction,
                counterparty=row.get("交易对方", ""),
                description=row.get("商品说明", "") or row.get("商品名称", ""),
                source_category=row.get("交易分类", "") or row.get("交易类型", ""),
                status=row.get("交易状态", ""),
                order_id=row.get("交易订单号", ""),
                source_file=source_file,
            )
        )
    return rows


# ---------------------------------------------------------------- CBA

CBA_DATE_FORMATS = ("%d/%m/%Y", "%d/%m/%y", "%Y-%m-%d", "%d %b %Y")
_CBA_DATE_RE = re.compile(r"^\d{1,2}/\d{1,2}/\d{2,4}$")


def _cba_row(date: str, amount: Decimal, description: str, where: str, source_file: str) -> Transaction:
    return Transaction(
        source="cba",
        occurred_at=_datetime(date, CBA_DATE_FORMATS, where),
        amount=amount,
        currency="AUD",
        direction="支出" if amount < 0 else "收入",
        counterparty="",
        description=description,
        source_category="",
        status="",
        order_id="",
        source_file=source_file,
    )


def parse_cba(content: bytes, source_file: str = "<cba>") -> list[Transaction]:
    """CBA NetBank 导出：默认无表头 `日期,金额,描述,余额`；也接受带 Date/Amount 或 Debit/Credit 表头的 CSV。"""
    records = [row for row in csv.reader(io.StringIO(_decode(content, source_file))) if any(cell.strip() for cell in row)]
    if not records:
        return []
    rows: list[Transaction] = []
    if _CBA_DATE_RE.match(records[0][0].strip()):
        for line_no, cells in enumerate(records, start=1):
            where = f"{source_file} 第 {line_no} 行"
            if len(cells) < 3:
                raise ImportFormatError(f"{where}: CBA 无表头格式需要至少 3 列（日期,金额,描述），实际 {len(cells)} 列")
            rows.append(_cba_row(cells[0], _money(cells[1], where), cells[2].strip(), where, source_file))
        return rows

    header = [cell.strip().lower() for cell in records[0]]

    def col(*names: str) -> int | None:
        for name in names:
            if name in header:
                return header.index(name)
        return None

    date_i = col("date", "transaction date")
    desc_i = col("description", "transaction description", "narrative")
    amount_i = col("amount")
    debit_i, credit_i = col("debit", "withdrawal"), col("credit", "deposit")
    if date_i is None or desc_i is None or (amount_i is None and debit_i is None and credit_i is None):
        raise ImportFormatError(
            f"{source_file}: 不是可识别的 CBA CSV（第 1 行既不是日期，也没有 Date/Description/Amount 表头）"
        )
    for line_no, cells in enumerate(records[1:], start=2):
        where = f"{source_file} 第 {line_no} 行"
        cell = lambda i: cells[i].strip() if i is not None and i < len(cells) else ""  # noqa: E731
        if amount_i is not None:
            amount = _money(cell(amount_i), where)
        else:
            debit = abs(_money(cell(debit_i), where)) if cell(debit_i) else Decimal(0)
            credit = abs(_money(cell(credit_i), where)) if cell(credit_i) else Decimal(0)
            amount = credit - debit
        rows.append(_cba_row(cell(date_i), amount, cell(desc_i), where, source_file))
    return rows


# ---------------------------------------------------------------- 数据目录

def detect_source(path: Path, content: bytes) -> str | None:
    """按内容判断来源；无法识别返回 None。"""
    name = path.name.lower()
    if zipfile.is_zipfile(io.BytesIO(content)):
        return "alipay" if ("alipay" in name or "支付宝" in path.name) else None
    head = content[:8192]
    for encoding in ("utf-8-sig", "gb18030"):
        try:
            text = head.decode(encoding)
            break
        except UnicodeDecodeError:
            text = ""
    if all(marker in text for marker in ALIPAY_REQUIRED) or "支付宝" in text:
        return "alipay"
    first = text.splitlines()[0].split(",")[0].strip().strip('"') if text.strip() else ""
    if "cba" in name or "commbank" in name or _CBA_DATE_RE.match(first):
        return "cba"
    return None


@dataclass(frozen=True)
class LoadResult:
    transactions: list[Transaction]
    files: list[str]
    skipped_files: list[str]
    duplicates_dropped: int


def _dedupe_key(tx: Transaction, occurrence: int) -> tuple:
    if tx.order_id:
        return (tx.source, tx.order_id)
    return (tx.source, tx.occurred_at, tx.amount, tx.description, tx.counterparty, occurrence)


def load_data_dir(data_dir: Path) -> LoadResult:
    """递归读取数据目录下所有支付宝/CBA 账单；跨文件去重（支付宝按交易订单号）。"""
    data_dir = Path(data_dir).expanduser()
    if not data_dir.is_dir():
        raise FileNotFoundError(f"数据目录不存在：{data_dir}（请设置 PFI_DATA_DIR 或传 --data-dir）")
    seen: set[tuple] = set()
    kept: list[Transaction] = []
    files: list[str] = []
    skipped: list[str] = []
    dropped = 0
    for path in sorted(p for p in data_dir.rglob("*") if p.is_file() and p.suffix.lower() in {".csv", ".zip"}):
        content = path.read_bytes()
        source = detect_source(path, content)
        rel = str(path.relative_to(data_dir))
        if source is None:
            skipped.append(rel)
            print(f"[pfi] 跳过无法识别的文件：{rel}", file=sys.stderr)
            continue
        parsed = parse_alipay(content, rel) if source == "alipay" else parse_cba(content, rel)
        files.append(rel)
        occurrences: dict[tuple, int] = {}
        for tx in parsed:
            base = (tx.source, tx.occurred_at, tx.amount, tx.description, tx.counterparty)
            occurrences[base] = occurrences.get(base, 0) + 1
            key = _dedupe_key(tx, occurrences[base])
            if key in seen:
                dropped += 1
                continue
            seen.add(key)
            kept.append(tx)
    kept.sort(key=lambda tx: tx.occurred_at)
    return LoadResult(kept, files, skipped, dropped)
