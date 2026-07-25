"""交易账本定时备份(每日一次,由 alpha-backup.timer 驱动)。

保护对象:交易域库(订单意图 / 券商单 / 成交 / 幂等键 / 风控裁决 / 发件箱)——这是"系统
到底下过什么单、成没成、有没有重复"的唯一真相。一旦库损坏或被误清,没有备份就无法对账。

做法:pg_dump 压缩落盘到 /opt/alpha/backups,按 KEEP 份轮转;成功/失败都发一封邮件留痕。
诚实边界:这是**本机备份**,防的是"库损坏/误删",不防"整台机器毁灭"——真正异地容灾需要
第二个存放点(owner 提供目的地后再加 scp/对象存储)。写 machine/facts/backup_status.json。
"""

from __future__ import annotations

import gzip
import json
import os
import re
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

BACKUP_DIR = Path(os.environ.get("ALPHA_BACKUP_DIR", "/opt/alpha/backups"))
KEEP = int(os.environ.get("ALPHA_BACKUP_KEEP", "14"))
FACTS = Path("machine/facts/backup_status.json")


def main() -> int:
    now = datetime.now(timezone.utc)
    url = os.environ.get("ALPHA_DATABASE_URL", "")
    # SQLAlchemy 用 postgresql+psycopg://,pg_dump 只认 libpq 的 postgresql://——去掉 +驱动。
    libpq_url = re.sub(r"^postgresql\+\w+://", "postgresql://",
                       re.sub(r"^postgres\+\w+://", "postgresql://", url))
    ok, detail, path, size = False, "", "", 0
    try:
        if not libpq_url.startswith(("postgres://", "postgresql://")):
            raise RuntimeError("非 PostgreSQL 或未配置 ALPHA_DATABASE_URL,跳过备份")
        BACKUP_DIR.mkdir(parents=True, exist_ok=True)
        out = BACKUP_DIR / f"alpha_ledger_{now:%Y%m%dT%H%M%SZ}.sql.gz"
        # pg_dump 从 URL 连接;stdout 压缩落盘
        proc = subprocess.run(["pg_dump", "--no-owner", "--no-privileges", libpq_url],
                              capture_output=True, timeout=180)
        if proc.returncode != 0:
            raise RuntimeError(f"pg_dump 失败:{proc.stderr.decode('utf-8', 'ignore')[:200]}")
        with gzip.open(out, "wb") as f:
            f.write(proc.stdout)
        size = out.stat().st_size
        path = str(out)
        ok = size > 0
        detail = f"{size} 字节 → {out.name}"
        # 轮转:按名字(含时间戳)排序,只留最近 KEEP 份
        dumps = sorted(BACKUP_DIR.glob("alpha_ledger_*.sql.gz"))
        for old in dumps[:-KEEP]:
            old.unlink(missing_ok=True)
    except Exception as exc:
        detail = f"{type(exc).__name__}: {exc}"[:220]

    FACTS.parent.mkdir(parents=True, exist_ok=True)
    FACTS.write_text(json.dumps({
        "at": now.isoformat(), "ok": ok, "path": path, "size": size,
        "keep": KEEP, "detail": detail}, ensure_ascii=False))

    try:
        from backend.app.store.db import create_session_factory, init_engine
        from backend.app.notify.outbox import Outbox
        text = (f"✅ 交易账本已备份:{detail}(本机保留最近 {KEEP} 份)。" if ok
                else f"❌ 交易账本备份失败:{detail}。请尽快处理——没有备份时若库损坏将无法对账。")
        Outbox(create_session_factory(init_engine())).enqueue(
            event_type="LEDGER_BACKUP", payload={"text": text})
    except Exception as exc:
        print("备份邮件入队失败:", exc)

    print(detail)
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
