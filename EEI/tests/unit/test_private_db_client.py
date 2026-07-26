"""The authoritative-store client's two contracts: red lines, and "no new
facts => no commit".

The second one is the one that bites quietly. An already-present object does
not mean the call was a no-op: appending a ledger line is a commit too. These
tests pin both halves so a re-ingest of unchanged facts stays completely silent.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from scripts.private_db_client import (
    MAX_FILE_BYTES,
    PrivateDbError,
    _manifest_has,
    check_red_lines,
    ingest,
    manifest_identity,
    object_path,
    sha256_hex,
)

NAME = "eei_facts_2026-07-26.ndjson.gz"


def _entry(
    digest: str = "a" * 64,
    *,
    domain: str = "EEI",
    ingested_at: str = "2026-07-26T12:00:00+00:00",
) -> dict:
    return {
        "sha256": digest,
        "original_name": NAME,
        "size_bytes": 1227266,
        "domain": domain,
        "batch": "EEI-20260726-initial",
        "object_path": f"Private-MetaDatabase/{object_path(digest, NAME)}",
        "ingested_at": ingested_at,
    }


def _line(entry: dict) -> bytes:
    return (json.dumps(entry, ensure_ascii=False, sort_keys=True) + "\n").encode("utf-8")


# --- "no new facts => no commit" -------------------------------------------

def test_manifest_identity_ignores_run_metadata_not_the_fact() -> None:
    later = _entry(ingested_at="2026-07-26T12:00:01+00:00")
    later["batch"] = "EEI-20260727-daily"
    assert manifest_identity(_entry()) == manifest_identity(later)


def test_reingest_one_second_later_is_not_a_new_ledger_line() -> None:
    """Whole-line comparison would call this new: `ingested_at` moved by a
    second. That would append a duplicate and manufacture a commit for facts
    that did not change."""
    current = _line(_entry())
    assert _manifest_has(current, _entry(ingested_at="2026-07-26T12:00:01+00:00"))


def test_genuinely_new_facts_are_still_appended() -> None:
    current = _line(_entry())
    assert not _manifest_has(current, _entry(digest="b" * 64))
    assert not _manifest_has(current, _entry(domain="Alpha"))
    assert not _manifest_has(b"", _entry())


def test_hand_edited_garbage_line_does_not_block_an_honest_append() -> None:
    current = b"not json at all\n" + _line(_entry())
    assert _manifest_has(current, _entry())
    assert not _manifest_has(b"not json at all\n", _entry())


def test_ingest_reports_object_and_ledger_writes_separately(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """The object being present is not proof the call was silent — the ledger
    append is a commit of its own, so `created_commit` must cover both."""
    source = tmp_path / "eei_facts_2026-07-26.ndjson.gz"
    source.write_bytes(b"fact-bytes")

    import scripts.private_db_client as client

    seen: dict[str, object] = {}

    def fake_blob_sha(zone: str, path: str) -> str | None:
        seen["object_path"] = path
        return "existing-blob-sha"  # object already there

    def fail_put(*args: object, **kwargs: object) -> None:  # pragma: no cover
        raise AssertionError("must not re-upload an object that already exists")

    monkeypatch.setattr(client, "blob_sha", fake_blob_sha)
    monkeypatch.setattr(client, "put_file", fail_put)
    monkeypatch.setattr(client, "append_manifest", lambda zone, entry: True)

    out = ingest("Private-MetaDatabase", source, domain="EEI", batch="b")

    assert out["uploaded_object"] is False
    assert out["skipped_upload"] is True
    assert out["appended_manifest"] is True
    assert out["created_commit"] is True, "a ledger append is still a commit"
    assert out["sha256"] == sha256_hex(b"fact-bytes")
    assert seen["object_path"] == object_path(out["sha256"], source.name)


def test_ingest_is_completely_silent_when_nothing_changed(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    source = tmp_path / "eei_facts_2026-07-26.ndjson.gz"
    source.write_bytes(b"fact-bytes")

    import scripts.private_db_client as client

    monkeypatch.setattr(client, "blob_sha", lambda zone, path: "existing-blob-sha")
    monkeypatch.setattr(client, "append_manifest", lambda zone, entry: False)

    out = ingest("Private-MetaDatabase", source, domain="EEI", batch="b")

    assert out["created_commit"] is False


def test_ingest_reports_a_first_upload_as_a_commit(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    source = tmp_path / "eei_facts_2026-07-26.ndjson.gz"
    source.write_bytes(b"fact-bytes")

    import scripts.private_db_client as client

    uploads: list[str] = []
    monkeypatch.setattr(client, "blob_sha", lambda zone, path: None)
    monkeypatch.setattr(
        client,
        "put_file",
        lambda zone, path, payload, *, message: uploads.append(path) or {},
    )
    monkeypatch.setattr(client, "append_manifest", lambda zone, entry: True)

    out = ingest("Private-MetaDatabase", source, domain="EEI", batch="b")

    assert uploads == [object_path(out["sha256"], source.name)]
    assert out["uploaded_object"] is True
    assert out["skipped_upload"] is False
    assert out["created_commit"] is True


# --- red lines --------------------------------------------------------------

def test_red_lines_refuse_databases_key_material_and_credentials() -> None:
    # Assembled, not written out: the repo's own secret scanner reads this file,
    # and a literal PEM header here would (correctly) trip it.
    pem_header = b"-----BEGIN OPENSSH " + b"PRIVATE KEY-----"
    with pytest.raises(PrivateDbError, match="refused by suffix"):
        check_red_lines("runtime.sqlite", b"anything")
    with pytest.raises(PrivateDbError, match="refused by suffix"):
        check_red_lines("deploy.pem", b"anything")
    with pytest.raises(PrivateDbError, match="looks like a credential"):
        check_red_lines("service.env", b"anything")
    with pytest.raises(PrivateDbError, match="credential signature"):
        check_red_lines("facts.ndjson", pem_header)
    with pytest.raises(PrivateDbError, match="exceeds"):
        check_red_lines("facts.ndjson", b"x" * (MAX_FILE_BYTES + 1))


def test_red_lines_pass_an_ordinary_fact_partition() -> None:
    check_red_lines("eei_facts_2026-07-26.ndjson.gz", b'{"_meta": {"day": "2026-07-26"}}')


def test_object_path_is_content_addressed() -> None:
    digest = sha256_hex(b"fact-bytes")
    expected = f"objects/{digest[:2]}/{digest}_facts.ndjson.gz"
    assert object_path(digest, "a/b/facts.ndjson.gz") == expected
