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
