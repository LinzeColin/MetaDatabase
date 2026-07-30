from social_archive.models import CaptureRequest


def test_artifact_completes_only_after_three_identical_cipher_receipts(service, store):
    response = service.capture(CaptureRequest(platform="generic-web", url="https://www.wikipedia.org/all3", requested_levels=["L0", "L1"]))
    artifact = store.get_content(response.content_id)["artifacts"][0]
    for store_id in ("r2", "oci"):
        store.upsert_object_replica(
            artifact_id=artifact["id"], store_id=store_id, object_key=f"{store_id}://object",
            status="verified", verified_sha256="d" * 64,
            original_sha256=artifact["sha256"], encryption="age-x25519",
        )
    assert store.get_content(response.content_id)["artifacts"][0]["status"] != "complete"
    store.upsert_object_replica(
        artifact_id=artifact["id"], store_id="github", object_key="gh-release://private/object",
        status="verified", verified_sha256="d" * 64,
        original_sha256=artifact["sha256"], encryption="age-x25519",
    )
    assert store.get_content(response.content_id)["artifacts"][0]["status"] == "complete"


def test_mismatched_cipher_receipt_never_completes(service, store):
    response = service.capture(CaptureRequest(platform="generic-web", url="https://www.wikipedia.org/mismatch", requested_levels=["L0", "L1"]))
    artifact = store.get_content(response.content_id)["artifacts"][0]
    for index, store_id in enumerate(("r2", "oci", "github")):
        store.upsert_object_replica(
            artifact_id=artifact["id"], store_id=store_id, object_key=f"{store_id}://object",
            status="verified", verified_sha256=(str(index) * 64),
            original_sha256=artifact["sha256"], encryption="age-x25519",
        )
    assert store.get_content(response.content_id)["artifacts"][0]["status"] != "complete"
