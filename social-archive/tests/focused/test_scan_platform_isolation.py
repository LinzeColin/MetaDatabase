from social_archive.models import CaptureRequest


def test_complete_scan_only_changes_the_scanned_platform(service, store):
    x_item = service.capture(CaptureRequest(
        platform="x", url="https://x.com/example/status/100", relation_type="bookmark",
        requested_levels=["L0", "L1"],
    ))
    reddit_item = service.capture(CaptureRequest(
        platform="reddit", url="https://www.reddit.com/r/example/comments/100/item/", relation_type="saved",
        requested_levels=["L0", "L1"],
    ))
    store.apply_complete_scan("x", set(), relation_type="bookmark")
    store.apply_complete_scan("x", set(), relation_type="bookmark")
    x_relation = store.get_content(x_item.content_id)["relations"][0]
    reddit_relation = store.get_content(reddit_item.content_id)["relations"][0]
    assert x_relation["status"] == "closed"
    assert x_relation["missing_complete_scan_count"] == 2
    assert reddit_relation["status"] == "active"
    assert reddit_relation["missing_complete_scan_count"] == 0


def test_kuaishou_complete_scan_never_changes_another_platform(service, store):
    kuaishou_item = service.capture(CaptureRequest(
        platform="kuaishou", url="https://www.kuaishou.com/short-video/100", relation_type="favorite",
        requested_levels=["L0", "L1"],
    ))
    x_item = service.capture(CaptureRequest(
        platform="x", url="https://x.com/example/status/101", relation_type="bookmark",
        requested_levels=["L0", "L1"],
    ))

    store.apply_complete_scan("kuaishou", set(), relation_type="favorite")
    store.apply_complete_scan("kuaishou", set(), relation_type="favorite")

    kuaishou_relation = store.get_content(kuaishou_item.content_id)["relations"][0]
    x_relation = store.get_content(x_item.content_id)["relations"][0]
    assert kuaishou_relation["status"] == "closed"
    assert kuaishou_relation["missing_complete_scan_count"] == 2
    assert x_relation["status"] == "active"
    assert x_relation["missing_complete_scan_count"] == 0
