"""并发读写同一 SQLite:文件库必须开 WAL 与 busy_timeout(否则 database is locked 打崩 worker)。"""

from sqlalchemy import text

from backend.app.store.db import init_engine


def test_sqlite_file_db_uses_wal(tmp_path):
    engine = init_engine(f"sqlite:///{tmp_path / 'wal.sqlite'}")
    with engine.connect() as conn:
        assert conn.execute(text("PRAGMA journal_mode")).scalar() == "wal"
        assert conn.execute(text("PRAGMA busy_timeout")).scalar() == 5000
        assert conn.execute(text("PRAGMA foreign_keys")).scalar() == 1
