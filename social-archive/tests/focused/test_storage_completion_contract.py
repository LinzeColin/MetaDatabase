from pathlib import Path


def test_storage_completion_contract_requires_three_receipts(store):
    completion = store.replication_completion()
    assert completion["required_replicas"] == 3
    assert {"total_artifacts", "all_three_verified", "pending"} <= completion.keys()


def test_extension_never_claims_completion_without_three_receipts():
    root = Path(__file__).resolve().parents[2]
    source = (root / "apps/browser-extension/options.js").read_text(encoding="utf-8")
    assert "归档完成 3/3" in source
    assert "未齐三张收据不会显示完成" in source
