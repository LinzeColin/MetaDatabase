from social_archive.models import CaptureRequest


def _relation(store, content_id):
    return store.get_content(content_id)["relations"][0]


def test_complete_scan_is_exact_to_relation_collection_and_account(service, store):
    bookmark_a = service.capture(CaptureRequest(
        platform="x", url="https://x.com/u/status/1", relation_type="bookmark",
        collection_key="a", source_account_id="owner-1", requested_levels=["L0","L1"],
    ))
    like_a = service.capture(CaptureRequest(
        platform="x", url="https://x.com/u/status/2", relation_type="like",
        collection_key="a", source_account_id="owner-1", requested_levels=["L0","L1"],
    ))
    bookmark_b = service.capture(CaptureRequest(
        platform="x", url="https://x.com/u/status/3", relation_type="bookmark",
        collection_key="b", source_account_id="owner-1", requested_levels=["L0","L1"],
    ))
    other_account = service.capture(CaptureRequest(
        platform="x", url="https://x.com/u/status/4", relation_type="bookmark",
        collection_key="a", source_account_id="owner-2", requested_levels=["L0","L1"],
    ))
    for _ in range(2):
        store.apply_complete_scan(
            "x", set(), relation_type="bookmark", collection_key="a", source_account_id="owner-1",
        )
    assert _relation(store, bookmark_a.content_id)["status"] == "closed"
    assert _relation(store, like_a.content_id)["status"] == "active"
    assert _relation(store, bookmark_b.content_id)["status"] == "active"
    assert _relation(store, other_account.content_id)["status"] == "active"


def test_partial_or_item_receipt_is_recorded_but_does_not_imply_closure(service, store):
    item = service.capture(CaptureRequest(
        platform="reddit", url="https://www.reddit.com/r/example/comments/1/a/",
        relation_type="saved", source_account_id="owner", requested_levels=["L0","L1"],
    ))
    receipt_id = store.record_scan_receipt(
        "reddit", "run-partial", {"completeness":"partial","scope":"account_relation","item_count":0},
        source_account_id="owner", relation_type="saved",
    )
    assert receipt_id
    assert _relation(store, item.content_id)["status"] == "active"


def test_relation_history_closes_only_after_two_complete_scope_absences(service, store):
    item = service.capture(CaptureRequest(
        platform="x", url="https://x.com/u/status/history", relation_type="bookmark",
        collection_key="research", source_account_id="owner", requested_levels=["L0", "L1"],
    ))
    store.record_scan_receipt(
        "x", "run-partial-history", {"completeness": "partial", "scope": "account_relation", "item_count": 0},
        source_account_id="owner", relation_type="bookmark",
    )
    relation = _relation(store, item.content_id)
    assert relation["status"] == "active"
    assert relation["missing_complete_scan_count"] == 0

    assert store.apply_complete_scan("x", set(), relation_type="bookmark", collection_key="research", source_account_id="owner") == 1
    relation = _relation(store, item.content_id)
    assert relation["status"] == "active"
    assert relation["missing_complete_scan_count"] == 1
    assert relation["closed_at"] is None

    assert store.apply_complete_scan("x", set(), relation_type="bookmark", collection_key="research", source_account_id="owner") == 1
    relation = _relation(store, item.content_id)
    assert relation["status"] == "closed"
    assert relation["missing_complete_scan_count"] == 2
    assert relation["closed_at"]


def test_bilibili_rate_limited_receipt_never_closes_existing_relation(service, store):
    item = service.capture(CaptureRequest(
        platform="bilibili", url="https://www.bilibili.com/video/BV1fixture", relation_type="favorite",
        source_account_id="owner", requested_levels=["L0", "L1"],
    ))
    receipt_id = store.record_scan_receipt(
        "bilibili",
        "run-rate-limited",
        {"completeness": "unknown", "scope": "account_relation", "item_count": 0, "failure_code": "BILI_RATE_LIMITED"},
        source_account_id="owner",
        relation_type="favorite",
    )

    assert receipt_id
    relation = _relation(store, item.content_id)
    assert relation["status"] == "active"
    assert relation["missing_complete_scan_count"] == 0
