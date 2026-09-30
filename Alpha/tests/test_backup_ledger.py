"""I3:账本在线备份(SQLite backup + 完整性校验 + 轮转 + 失败只告警一次)。全程离线。"""

import gzip
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

from sqlalchemy import select

import scripts.backup_ledger as bl


def _make_ledger(path: Path) -> None:
    """用 WAL 模式造一个有数据的库(与生产一致,备份期间可以有 -wal 文件)。"""
    con = sqlite3.connect(path)
    con.execute("PRAGMA journal_mode=WAL")
    con.execute("CREATE TABLE executions (id INTEGER PRIMARY KEY, symbol TEXT, qty INTEGER)")
    con.execute("CREATE TABLE fills (id INTEGER PRIMARY KEY, note TEXT)")
    con.executemany("INSERT INTO executions (symbol, qty) VALUES (?, ?)",
                    [("QQQ", 3), ("BIL", 10), ("SPY", 1)])
    con.executemany("INSERT INTO fills (note) VALUES (?)", [("a",), ("b",)])
    con.commit()
    con.close()


def _env(monkeypatch, tmp_path: Path, db: Path, *, backup_dir: Path | None = None, keep: int = 14) -> Path:
    bdir = backup_dir or tmp_path / "backups"
    monkeypatch.setenv("ALPHA_DATABASE_URL", f"sqlite:///{db}")
    monkeypatch.setenv("ALPHA_RUNTIME_DIR", str(tmp_path / "rt"))
    monkeypatch.setenv("ALPHA_BACKUP_DIR", str(bdir))
    monkeypatch.setenv("ALPHA_BACKUP_KEEP", str(keep))
    return bdir


def _outbox_types(db: Path) -> list[str]:
    from backend.app.domain.models import OutboxEvent
    from backend.app.store.db import create_session_factory, init_engine

    engine = init_engine(f"sqlite:///{db}")
    with create_session_factory(engine)() as s:
        rows = s.execute(select(OutboxEvent.event_type).order_by(OutboxEvent.created_at)).scalars().all()
    engine.dispose()
    return list(rows)


def test_sqlite_online_backup_roundtrip(monkeypatch, tmp_path):
    db = tmp_path / "alpha.sqlite"
    _make_ledger(db)
    bdir = _env(monkeypatch, tmp_path, db)
    now = datetime(2026, 9, 30, 21, 10, tzinfo=timezone.utc)
    assert bl.main(now=now) == 0
    backups = list(bdir.glob("alpha_ledger_*.sqlite.gz"))
    assert [b.name for b in backups] == ["alpha_ledger_20260930T211000Z.sqlite.gz"]
    # 不留临时文件
    assert sorted(p.name for p in bdir.iterdir()) == [backups[0].name]
    restored = tmp_path / "restored.sqlite"
    restored.write_bytes(gzip.decompress(backups[0].read_bytes()))
    con = sqlite3.connect(restored)
    assert con.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
    assert con.execute("SELECT COUNT(*) FROM executions").fetchone()[0] == 3
    assert con.execute("SELECT COUNT(*) FROM fills").fetchone()[0] == 2
    con.close()
    import json
    st = json.loads((tmp_path / "rt" / "facts" / "backup_status.json").read_text())
    assert st["ok"] is True and st["keep"] == 14 and st["path"] == str(backups[0])


def test_rotation_keeps_14(monkeypatch, tmp_path):
    db = tmp_path / "alpha.sqlite"
    _make_ledger(db)
    bdir = _env(monkeypatch, tmp_path, db)
    bdir.mkdir()
    old = [f"alpha_ledger_202609{d:02d}T211000Z.sqlite.gz" for d in range(1, 21)]
    for name in old:
        (bdir / name).write_bytes(b"x")
    assert bl.main(now=datetime(2026, 9, 30, 21, 10, tzinfo=timezone.utc)) == 0
    left = sorted(p.name for p in bdir.glob("alpha_ledger_*.sqlite.gz"))
    assert len(left) == 14
    # 留下的是最新的 14 份:新备份 + 预置里最晚的 13 份
    assert left == sorted(old[-13:] + ["alpha_ledger_20260930T211000Z.sqlite.gz"])


def test_failure_alerts_once_success_silent(monkeypatch, tmp_path):
    db = tmp_path / "alpha.sqlite"
    _make_ledger(db)
    # 备份目录建在一个普通文件之下 => 建目录失败,模拟备份落盘失败
    blocker = tmp_path / "blocker"
    blocker.write_text("x")
    bad_dir = blocker / "backups"
    _env(monkeypatch, tmp_path, db, backup_dir=bad_dir)
    t0 = datetime(2026, 9, 30, 21, 10, tzinfo=timezone.utc)
    assert bl.main(now=t0) == 1
    assert bl.main(now=t0.replace(day=29)) == 1
    types = _outbox_types(db)
    assert types.count("ALERT_RAISED") == 1, types          # 连续失败只发一封
    assert "LEDGER_BACKUP" not in types
    # 修好后成功:不发成功信,只发一封「已恢复」
    good_dir = tmp_path / "good"
    monkeypatch.setenv("ALPHA_BACKUP_DIR", str(good_dir))
    assert bl.main(now=t0.replace(day=30, hour=22)) == 0
    types = _outbox_types(db)
    assert types.count("ALERT_RAISED") == 1 and types.count("ALERT_RECOVERED") == 1
    assert "LEDGER_BACKUP" not in types
    # 再成功一次:什么信都不再发
    assert bl.main(now=t0.replace(day=30, hour=23)) == 0
    assert _outbox_types(db) == types


def test_missing_source_db_fails_without_fake_backup(monkeypatch, tmp_path):
    """源库不存在:如实失败,不产出任何"备份"文件(绝不把凭空建的空库当成备份)。"""
    db = tmp_path / "nothere.sqlite"
    bdir = _env(monkeypatch, tmp_path, db)
    assert bl.main(now=datetime(2026, 9, 30, tzinfo=timezone.utc)) == 1
    assert not list(bdir.glob("alpha_ledger_*"))
    import json
    st = json.loads((tmp_path / "rt" / "facts" / "backup_status.json").read_text())
    assert st["ok"] is False
