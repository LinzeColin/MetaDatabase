from social_archive.models import CaptureRequest
from social_archive.exports import StandardExporter


def test_canonical_exports_and_ordered_replication_can_rebuild(service, store, settings, tmp_path):
    response = service.capture(CaptureRequest(
        platform="reddit", url="https://reddit.com/r/x/1", relation_type="saved",
        title="R", requested_levels=["L0","L1"],
    ))
    # Long-lived Private-Database persistence is deliberately fail-closed until
    # SA-504 supplies the no-clone API transport.  Capturing must not create a
    # second local business-data copy in the meantime.
    assert not list(settings.private_database_root.rglob("*.json"))
    assert StandardExporter(store, tmp_path / "exports").export_all()["item_count"] == 1
    artifact = store.get_content(response.content_id)["artifacts"][0]
    assert store.list_artifacts_for_replication("oci", requires_verified_store="r2") == []
    store.upsert_object_replica(
        artifact_id=artifact["id"], store_id="r2", object_key="primary-objects/test",
        status="verified", verified_sha256=artifact["sha256"],
    )
    assert store.list_artifacts_for_replication("oci", requires_verified_store="r2")
