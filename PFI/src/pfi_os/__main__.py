"""PFI 命令行入口：python -m pfi_os {report,ledger,app,pull}。"""
from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
from pathlib import Path

from pfi_os.classify import classify_all, load_user_rules
from pfi_os.importers import load_data_dir
from pfi_os.report import monthly_summary, render_markdown, write_ledger_csv

APP_FILE = Path(__file__).with_name("ui.py")
PRIVATE_ZONE = "Private-MetaDatabase"
# 私有仓里 domain=LinzeDatabase-alipay 的 4 份支付宝原始账单，对象名形如
# objects/2c/<sha256>_alipay_20220605-20230605_24779d7bb0f9.csv；processed 汇总表不拉，避免重复计数。
RAW_ALIPAY_OBJECT = re.compile(r"objects/[0-9a-f]{2}/[0-9a-f]{64}_(alipay_\d{8}-\d{8}_[0-9a-f]+\.csv)$")


def data_dir_from(args: argparse.Namespace) -> Path:
    value = args.data_dir or os.environ.get("PFI_DATA_DIR")
    if not value:
        raise SystemExit("缺少数据目录：请设置环境变量 PFI_DATA_DIR，或传 --data-dir <目录>")
    return Path(value).expanduser()


def build(data_dir: Path):
    loaded = load_data_dir(data_dir)
    rows = classify_all(loaded.transactions, load_user_rules(data_dir))
    return loaded, rows


def cmd_report(args: argparse.Namespace) -> int:
    data_dir = data_dir_from(args)
    loaded, rows = build(data_dir)
    if not rows:
        raise SystemExit(f"{data_dir} 下没有读到任何流水（支持支付宝 CSV/ZIP、CBA CSV）")
    text = render_markdown(monthly_summary(rows), loaded, rows)
    if args.out:
        Path(args.out).write_text(text, encoding="utf-8")
        print(f"报告已写入 {args.out}")
    else:
        print(text)
    return 0


def cmd_ledger(args: argparse.Namespace) -> int:
    _, rows = build(data_dir_from(args))
    write_ledger_csv(rows, Path(args.out))
    print(f"已导出 {len(rows)} 条分类流水到 {args.out}")
    return 0


def cmd_app(args: argparse.Namespace) -> int:
    env = dict(os.environ, PFI_DATA_DIR=str(data_dir_from(args)))
    command = [sys.executable, "-m", "streamlit", "run", str(APP_FILE), "--server.address", "127.0.0.1",
               "--server.port", str(args.port), "--browser.gatherUsageStats", "false"]
    return subprocess.call(command, env=env)


def cmd_pull(args: argparse.Namespace) -> int:
    client = Path(args.client).expanduser()
    if not client.is_file():
        raise SystemExit(f"找不到 private_db_client.py：{client}")
    target = data_dir_from(args) / "alipay"
    target.mkdir(parents=True, exist_ok=True)
    listing = subprocess.run([sys.executable, str(client), "list", PRIVATE_ZONE, "--prefix", "objects/"],
                             capture_output=True, text=True)
    if listing.returncode != 0:
        raise SystemExit(f"private_db_client list 失败（退出码 {listing.returncode}）：{listing.stderr.strip()}")
    pulled = 0
    for line in listing.stdout.splitlines():
        path = json.loads(line)["path"].removeprefix(f"{PRIVATE_ZONE}/")
        match = RAW_ALIPAY_OBJECT.fullmatch(path)
        if not match:
            continue
        dest = target / match.group(1)
        subprocess.run([sys.executable, str(client), "get", PRIVATE_ZONE, path, str(dest)], check=True)
        pulled += 1
    if pulled == 0:
        raise SystemExit(f"{PRIVATE_ZONE} 里没有匹配 alipay_YYYYMMDD-YYYYMMDD_*.csv 的原始账单对象")
    print(f"已拉取 {pulled} 份支付宝原始账单到 {target}")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m pfi_os", description="PFI：个人流水导入、分类、月度收支报告")
    parser.add_argument("--data-dir", help="流水目录（默认读环境变量 PFI_DATA_DIR）")
    sub = parser.add_subparsers(dest="command", required=True)
    p = sub.add_parser("report", help="输出月度收支 Markdown 报告")
    p.add_argument("--out", help="写入文件而不是打印")
    p.set_defaults(func=cmd_report)
    p = sub.add_parser("ledger", help="导出分类后的全部流水 CSV")
    p.add_argument("--out", required=True)
    p.set_defaults(func=cmd_ledger)
    p = sub.add_parser("app", help="启动本地 Streamlit 界面")
    p.add_argument("--port", type=int, default=8501)
    p.set_defaults(func=cmd_app)
    p = sub.add_parser("pull", help="从 Private-Database 拉取支付宝原始账单到 $PFI_DATA_DIR/alipay/")
    p.add_argument("--client", required=True, help="private_db_client.py 的路径（需要本机 gh 已登录）")
    p.set_defaults(func=cmd_pull)
    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
