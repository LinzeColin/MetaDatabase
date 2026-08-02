from social_archive.models import CaptureRequest


def test_table_supports_required_columns_and_server_sort(store, service):
    service.capture(CaptureRequest(
        platform="bilibili", url="https://www.bilibili.com/video/BV1A", external_content_id="BV1A",
        relation_type="watch_later", source_account_id="b1", relation_observed_at="2026-08-01T10:00:00Z",
        title="Alpha", text="财务现金流", author_name="作者A", topic="学习研究", keywords=["现金流"],
    ))
    service.capture(CaptureRequest(
        platform="bilibili", url="https://www.bilibili.com/video/BV1B", external_content_id="BV1B",
        relation_type="favorite", source_account_id="b1", relation_observed_at="2026-08-02T10:00:00Z",
        title="Beta", text="回转窑测量", author_name="作者B", topic="机械制造", keywords=["回转窑", "测量"],
    ))
    result = store.list_library_table(platform="bilibili", sort_by="content", sort_dir="asc")
    assert [item["title"] for item in result["items"]] == ["Alpha", "Beta"]
    required = {"platform", "relation_time", "topic", "keywords", "title", "canonical_url"}
    assert required.issubset(result["items"][0])
    topic = store.list_library_table(topic="机械制造")
    assert topic["total"] == 1
    assert topic["items"][0]["title"] == "Beta"
