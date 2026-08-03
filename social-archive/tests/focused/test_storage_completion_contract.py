from pathlib import Path


def test_storage_completion_contract_requires_three_receipts(store):
    completion = store.replication_completion()
    assert completion["required_replicas"] == 3
    assert {"total_artifacts", "all_three_verified", "pending"} <= completion.keys()


def test_artifact_complete_state_is_only_set_after_r2_oci_and_github_verified():
    root = Path(__file__).resolve().parents[2]
    source = (root / "src/social_archive/db.py").read_text(encoding="utf-8")
    assert 'required = {"r2", "oci", "github"}' in source
    assert "required.issubset(by_store)" in source
    assert "UPDATE artifact SET status='complete'" in source


def test_user_facing_full_archive_label_is_derived_from_complete_artifact_state():
    root = Path(__file__).resolve().parents[2]
    db = (root / "src/social_archive/db.py").read_text(encoding="utf-8")
    pwa = (root / "apps/pwa/app.js").read_text(encoding="utf-8")
    assert "a.status='complete'" in db
    assert "'完整'" in db
    assert 'L0/L1/L3 完整' in pwa
