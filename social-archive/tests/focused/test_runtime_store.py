import sqlite3

from social_archive.db import RuntimeStore
from social_archive.models import CaptureRequest

def test_job_claim_and_finish(store):
    jid=store.enqueue_job('download_l3',{'content_id':'c','page_url':'https://www.wikipedia.org','media_urls':[]},'generic')
    row=store.claim_job('tester');assert row and row['id']==jid
    store.finish_job(jid,success=True);assert store.get_job(jid)['status']=='done'

def test_complete_scan_requires_two_absences(service,store):
    r=service.capture(CaptureRequest(platform='reddit',url='https://reddit.com/r/a/comments/1',relation_type='saved',requested_levels=['L0','L1']))
    store.apply_complete_scan('reddit',set(),relation_type='saved');assert store.get_content(r.content_id)['relations'][0]['status']=='active'
    store.apply_complete_scan('reddit',set(),relation_type='saved');assert store.get_content(r.content_id)['relations'][0]['status']=='closed'


def test_account_mirror_schema_migrates_a_legacy_source_account(tmp_path):
    path = tmp_path / "legacy.sqlite3"
    with sqlite3.connect(path) as con:
        con.execute("""CREATE TABLE source_account (
            id TEXT PRIMARY KEY, platform TEXT NOT NULL, external_account_id TEXT,
            display_name TEXT, auth_ref TEXT, created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL, UNIQUE(platform, external_account_id)
        )""")
    RuntimeStore(path).initialize()
    with sqlite3.connect(path) as con:
        columns = {row[1] for row in con.execute("PRAGMA table_info(source_account)")}
        tables = {row[0] for row in con.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    assert {"connection_state", "auth_handle_ref", "last_sync_at", "metadata_json"} <= columns
    assert {"sync_run", "sync_checkpoint", "sync_seen_relation", "sync_run_scope"} <= tables


def test_table_schema_migrates_legacy_relation_before_indexes(tmp_path):
    path = tmp_path / "legacy-table.sqlite3"
    with sqlite3.connect(path) as con:
        con.execute("""CREATE TABLE source_account (
            id TEXT PRIMARY KEY, platform TEXT NOT NULL, external_account_id TEXT,
            display_name TEXT, auth_ref TEXT, created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL, UNIQUE(platform, external_account_id)
        )""")
        con.execute("""CREATE TABLE content (
            id TEXT PRIMARY KEY, platform TEXT NOT NULL, external_content_id TEXT,
            canonical_url TEXT NOT NULL, content_type TEXT NOT NULL DEFAULT 'unknown',
            title TEXT, author_name TEXT, published_at TEXT, first_observed_at TEXT NOT NULL,
            last_observed_at TEXT NOT NULL, availability TEXT NOT NULL DEFAULT 'observed',
            metadata_json TEXT NOT NULL DEFAULT '{}', UNIQUE(platform, external_content_id),
            UNIQUE(platform, canonical_url)
        )""")
        con.execute("""CREATE TABLE user_relation (
            id TEXT PRIMARY KEY, source_account_id TEXT, content_id TEXT NOT NULL,
            relation_type TEXT NOT NULL, collection_key TEXT NOT NULL DEFAULT '',
            status TEXT NOT NULL DEFAULT 'active', first_observed_at TEXT NOT NULL,
            last_observed_at TEXT NOT NULL, missing_complete_scan_count INTEGER NOT NULL DEFAULT 0,
            closed_at TEXT, UNIQUE(source_account_id, content_id, relation_type, collection_key)
        )""")
        con.execute(
            "INSERT INTO content VALUES(?,?,?,?,?,?,?,?,?,?,?,?)",
            ("c1", "generic-web", "one", "https://example.com/one", "unknown", "one", None, None,
             "2026-08-01T00:00:00Z", "2026-08-01T00:00:00Z", "observed", "{}"),
        )
        con.execute(
            "INSERT INTO user_relation VALUES(?,?,?,?,?,?,?,?,?,?)",
            ("r1", None, "c1", "bookmark", "", "active", "2026-08-01T00:00:00Z",
             "2026-08-01T00:00:00Z", 0, None),
        )
    RuntimeStore(path).initialize()
    with sqlite3.connect(path) as con:
        relation_columns = {row[1] for row in con.execute("PRAGMA table_info(user_relation)")}
        content_columns = {row[1] for row in con.execute("PRAGMA table_info(content)")}
        relation_time = con.execute("SELECT relation_observed_at FROM user_relation WHERE id='r1'").fetchone()[0]
    assert {"relation_observed_at", "external_relation_id", "last_sync_run_id"} <= relation_columns
    assert {"summary", "language", "media_count", "last_synced_at"} <= content_columns
    assert relation_time == "2026-08-01T00:00:00Z"
