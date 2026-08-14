"""不齐三份可验证的副本，就不许说「完整」（v0.0.0.4 起，v0.0.0.7 按行为重写）。

## 为什么重写

原来这条钉的是 apps/browser-extension/options.js 里两句 UI 文案：
「归档完成 3/3」和「未齐三张收据不会显示完成」。
v0.0.0.6 的 SA-003 overlay（40d833bf）把那套界面换掉了，两句话都不在了，
判据于是红着——**而它要守的不变量一直被守着，只是换了地方守。**

现在钉行为，钉在真正决定「完整」的那一层：

    三个 store 的副本都在（r2 / oci / github）
    三份 verified_sha256 完全一致且非空
    三份 original_sha256 一致
    三份 encryption 算法一致
        ↓
    artifact.status = 'complete'
        ↓
    资料库的「归档状态」列才显示「完整」

比原来那条字符串判据**更严**：它还要求三份收据对内容哈希彼此一致，
不只是「有三张」。
"""

from __future__ import annotations

from pathlib import Path

import pytest

from social_archive.db import RuntimeStore

STORES = ("r2", "oci", "github")
CIPHER = "c" * 64
ORIGINAL = "a" * 64


@pytest.fixture
def store(tmp_path: Path) -> RuntimeStore:
    db = RuntimeStore(tmp_path / "runtime.sqlite3")
    db.initialize()
    with db.connection() as con:
        con.execute(
            "INSERT INTO content(id,platform,external_content_id,canonical_url,content_type,"
            "first_observed_at,last_observed_at,availability) VALUES('cnt_a','generic-web','a',"
            "'https://example.com/a','link','2026-01-01T00:00:00Z','2026-01-01T00:00:00Z','available')"
        )
    db.add_artifact(content_id="cnt_a", archive_level="L1", artifact_type="metadata_json",
                    sha256=ORIGINAL, byte_size=10, media_type="application/json",
                    local_path="/tmp/a.json")
    return db


def _artifact_id(store: RuntimeStore) -> str:
    with store.connection() as con:
        return str(con.execute("SELECT id FROM artifact LIMIT 1").fetchone()["id"])


def _status(store: RuntimeStore) -> str:
    with store.connection() as con:
        return str(con.execute("SELECT status FROM artifact LIMIT 1").fetchone()["status"])


def test_storage_completion_contract_requires_three_receipts(store: RuntimeStore) -> None:
    completion = store.replication_completion()
    assert completion["required_replicas"] == 3
    assert {"total_artifacts", "all_three_verified", "pending"} <= completion.keys()


def test_completion_is_not_claimed_until_the_third_receipt_lands(store: RuntimeStore) -> None:
    """一份、两份都不算完整。**只有第三份落地才翻牌。**"""
    artifact_id = _artifact_id(store)
    for index, store_id in enumerate(STORES, start=1):
        store.upsert_object_replica(
            artifact_id=artifact_id, store_id=store_id, object_key=f"obj/{store_id}",
            status="verified", etag="e", verified_sha256=CIPHER,
            original_sha256=ORIGINAL, encryption="age-x25519",
        )
        expected = "complete" if index == 3 else "staged"
        assert _status(store) == expected, (
            f"{index} 份收据时状态是 {_status(store)!r}，应为 {expected!r}"
            "——不齐三份就说完整，等于对用户谎报耐久性"
        )


def test_three_receipts_that_disagree_do_not_count(store: RuntimeStore) -> None:
    """三份都在，但哈希对不上——**不算完整**。

    这比原来那条字符串判据严：有三张收据不等于三份内容是同一个东西。
    """
    artifact_id = _artifact_id(store)
    for index, store_id in enumerate(STORES):
        store.upsert_object_replica(
            artifact_id=artifact_id, store_id=store_id, object_key=f"obj/{store_id}",
            status="verified", etag="e",
            # 第三份的密文哈希不一样
            verified_sha256=CIPHER if index < 2 else "d" * 64,
            original_sha256=ORIGINAL, encryption="age-x25519",
        )
    assert _status(store) == "staged", "三份收据互相矛盾时仍被判成完整"


def test_library_only_shows_complete_when_the_artifact_is_complete(store: RuntimeStore) -> None:
    """界面上那句「完整」必须由上面这条链决定，不能是别的来源。"""
    with store.connection() as con:
        con.execute(
            "INSERT INTO user_relation(id,content_id,relation_type,collection_key,status,"
            "first_observed_at,last_observed_at) VALUES('rel_a','cnt_a','bookmark','','active',"
            "'2026-01-01T00:00:00Z','2026-01-01T00:00:00Z')"
        )
    before = store.list_library_table(limit=1)["items"][0]["archive_status"]
    assert before != "完整", f"还没有任何副本就显示了 {before!r}"

    artifact_id = _artifact_id(store)
    for store_id in STORES:
        store.upsert_object_replica(
            artifact_id=artifact_id, store_id=store_id, object_key=f"obj/{store_id}",
            status="verified", etag="e", verified_sha256=CIPHER,
            original_sha256=ORIGINAL, encryption="age-x25519",
        )
    after = store.list_library_table(limit=1)["items"][0]["archive_status"]
    assert after == "完整", f"三份齐了却显示 {after!r}"
