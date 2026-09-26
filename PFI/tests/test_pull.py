"""pull 只拉支付宝原始账单；用一个假的 private_db_client.py 代替 GitHub。"""
from __future__ import annotations

from pathlib import Path

import pytest

from pfi_os.__main__ import main

SHA = "ab" * 32
FAKE_CLIENT = f'''
import json, sys
from pathlib import Path
cmd = sys.argv[1]
if cmd == "list":
    for name in ["objects/ab/{SHA}_alipay_20220605-20230605_24779d7bb0f9.csv",
                 "objects/ab/{SHA}_alipay_transactions.csv",
                 "objects/ab/{SHA}_other_project.xlsx"]:
        print(json.dumps({{"path": "Private-MetaDatabase/" + name, "size": 1, "sha": "x"}}))
elif cmd == "get":
    Path(sys.argv[4]).write_text("交易时间,收/支,金额\\n2026-06-01 08:00:00,支出,1.00\\n", encoding="utf-8")
'''


def test_pull_fetches_only_raw_alipay_bills(tmp_path: Path) -> None:
    client = tmp_path / "private_db_client.py"
    client.write_text(FAKE_CLIENT, encoding="utf-8")
    data = tmp_path / "data"

    assert main(["--data-dir", str(data), "pull", "--client", str(client)]) == 0

    assert sorted(p.name for p in (data / "alipay").iterdir()) == ["alipay_20220605-20230605_24779d7bb0f9.csv"]


def test_pull_with_missing_client_explains(tmp_path: Path) -> None:
    with pytest.raises(SystemExit, match="找不到 private_db_client.py"):
        main(["--data-dir", str(tmp_path), "pull", "--client", str(tmp_path / "nope.py")])
