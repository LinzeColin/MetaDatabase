import sqlite3
from pathlib import Path

def test_legacy_source_is_read_only_and_runtime_schema_is_idempotent(tmp_path):
    legacy=tmp_path/'legacy.sqlite';con=sqlite3.connect(legacy);con.execute('create table items(id text primary key,url text)');con.execute('insert into items values(?,?)',('1','https://www.wikipedia.org/1'));con.commit();con.close()
    before=legacy.read_bytes()
    schema=(Path(__file__).resolve().parents[2]/'src/social_archive/sql/runtime_schema.sql').read_text(encoding='utf-8')
    target=sqlite3.connect(tmp_path/'new.sqlite');target.executescript(schema);target.executescript(schema);target.close()
    assert legacy.read_bytes()==before
