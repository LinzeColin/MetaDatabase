"""交易账本定时备份(每日一次,由 alpha-backup.timer 驱动)。

保护对象:交易域库(订单意图 / 券商单 / 成交 / 幂等键 / 风控裁决 / 发件箱 / 影子订单簿)——
这是"系统到底下过什么单、成没成、有没有重复"的唯一真相。一旦库损坏或被误清,没有备份就无法对账。

做法:
- SQLite(影子盘):sqlite3 在线备份接口拷到临时文件,integrity_check 得到 ok 后才 gzip 成
  alpha_ledger_<UTC时间戳>.sqlite.gz,按文件名轮转保留 KEEP 份。备份期间 worker 照常读写,不停服。
  成功不发信(每日摘要会汇报最近备份时间),失败经告警状态簿只发一封,下次成功发一封「已恢复」。
- PostgreSQL:pg_dump 压缩落盘,行为保持原样(成功/失败都发 LEDGER_BACKUP 邮件)。
诚实边界:这是**本机备份**,防的是"库损坏/误删",不防"整台机器毁灭"——真正异地容灾需要
第二个存放点(owner 提供目的地后再加)。备份只留在服务器本机,不进 git。
事实文件写到 truth.facts_dir()/backup_status.json。
"""

from __future__ import annotations

import gzip
import json
import os
import re
import shutil
import sqlite3
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

ALERT_KEY = "backup"


def _backup_dir() -> Path:
    from backend.app import truth
    return Path(os.environ.get("ALPHA_BACKUP_DIR") or truth.runtime_dir() / "backups")


def _keep() -> int:
    return int(os.environ.get("ALPHA_BACKUP_KEEP", "14"))


def _rotate(backup_dir: Path, keep: int) -> None:
    """按名字(含时间戳)排序,只留最近 keep 份;只认已完整落盘的 .sqlite.gz。"""
    dumps = sorted(backup_dir.glob("alpha_ledger_*.sqlite.gz"))
    for old in dumps[:-keep]:
        old.unlink(missing_ok=True)


def backup_sqlite(src: str, backup_dir: Path, keep: int, now: datetime) -> tuple[Path, int]:
    """在线备份 SQLite 账本;完整性校验通过后才压缩落盘。返回(备份文件, 字节数)。"""
    if not src or src == ":memory:" or not Path(src).is_file():
        raise RuntimeError(f"账本库文件不存在或不是文件: {src or '(空)'}")
    backup_dir.mkdir(parents=True, exist_ok=True)
    stamp = f"{now:%Y%m%dT%H%M%SZ}"
    tmp = backup_dir / f".alpha_ledger_{stamp}.tmp.sqlite"
    part = backup_dir / f".alpha_ledger_{stamp}.part"
    out = backup_dir / f"alpha_ledger_{stamp}.sqlite.gz"
    try:
        # 只读打开源库:备份绝不会在源路径上凭空建出一个空库
        source = sqlite3.connect(f"file:{src}?mode=ro", uri=True, timeout=30)
        dest = sqlite3.connect(tmp)
        try:
            source.backup(dest)
            verdict = dest.execute("PRAGMA integrity_check").fetchone()[0]
        finally:
            dest.close()
            source.close()
        if verdict != "ok":
            raise RuntimeError(f"备份副本完整性校验未通过: {str(verdict)[:120]}")
        with open(tmp, "rb") as fin, gzip.open(part, "wb") as fout:
            shutil.copyfileobj(fin, fout)
        os.replace(part, out)
    finally:
        tmp.unlink(missing_ok=True)
        part.unlink(missing_ok=True)
    _rotate(backup_dir, keep)
    return out, out.stat().st_size


def backup_postgres(libpq_url: str, backup_dir: Path, keep: int, now: datetime) -> tuple[Path, int]:
    backup_dir.mkdir(parents=True, exist_ok=True)
    out = backup_dir / f"alpha_ledger_{now:%Y%m%dT%H%M%SZ}.sql.gz"
    # pg_dump 从 URL 连接;stdout 压缩落盘
    proc = subprocess.run(["pg_dump", "--no-owner", "--no-privileges", libpq_url],
                          capture_output=True, timeout=180)
    if proc.returncode != 0:
        raise RuntimeError(f"pg_dump 失败:{proc.stderr.decode('utf-8', 'ignore')[:200]}")
    with gzip.open(out, "wb") as f:
        f.write(proc.stdout)
    dumps = sorted(backup_dir.glob("alpha_ledger_*.sql.gz"))
    for old in dumps[:-keep]:
        old.unlink(missing_ok=True)
    return out, out.stat().st_size


def main(*, now: Optional[datetime] = None) -> int:
    from sqlalchemy.engine import make_url

    from backend.app import truth

    now = now or datetime.now(timezone.utc)
    keep = _keep()
    backup_dir = _backup_dir()
    url = os.environ.get("ALPHA_DATABASE_URL", "")
    # SQLAlchemy 用 postgresql+psycopg://,pg_dump 只认 libpq 的 postgresql://——去掉 +驱动。
    libpq_url = re.sub(r"^postgresql\+\w+://", "postgresql://",
                       re.sub(r"^postgres\+\w+://", "postgresql://", url))
    is_pg = libpq_url.startswith(("postgres://", "postgresql://"))
    ok, detail, path, size = False, "", "", 0
    try:
        if is_pg:
            out, size = backup_postgres(libpq_url, backup_dir, keep, now)
        elif url.startswith("sqlite"):
            out, size = backup_sqlite(make_url(url).database or "", backup_dir, keep, now)
        else:
            raise RuntimeError("仅支持 SQLite / PostgreSQL,或未配置 ALPHA_DATABASE_URL,跳过备份")
        path = str(out)
        ok = size > 0
        detail = f"{size} 字节 → {out.name}"
    except Exception as exc:
        detail = f"{type(exc).__name__}: {exc}"[:220]

    facts = truth.facts_dir() / "backup_status.json"
    try:
        facts.parent.mkdir(parents=True, exist_ok=True)
        facts.write_text(json.dumps({
            "at": now.isoformat(), "ok": ok, "path": path, "size": size,
            "keep": keep, "detail": detail}, ensure_ascii=False))
    except Exception as exc:
        print("备份事实文件写入失败:", exc)

    try:
        from backend.app.notify.outbox import AlertBook, Outbox
        from backend.app.store.db import create_session_factory, init_engine
        factory = create_session_factory(init_engine())
        if is_pg:
            text = (f"✅ 交易账本已备份:{detail}(本机保留最近 {keep} 份)。" if ok
                    else f"❌ 交易账本备份失败:{detail}。请尽快处理——没有备份时若库损坏将无法对账。")
            Outbox(factory).enqueue(event_type="LEDGER_BACKUP", payload={"text": text})
        else:
            AlertBook(factory).observe(ALERT_KEY, not ok, payload={
                "title": "交易账本备份失败",
                "detail": f"每日账本备份失败:{detail}。交易与风控不受影响,但库若损坏将没有最新备份可恢复。",
                "action": "需要代理排查备份目录与磁盘空间;不用你动手。"})
    except Exception as exc:
        print("备份告警入队失败:", exc)

    print(detail)
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
