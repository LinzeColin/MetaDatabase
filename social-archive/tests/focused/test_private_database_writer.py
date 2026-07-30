import pytest

from social_archive.repository import PrivateDatabasePolicyError, PrivateDatabaseWriter


def test_legacy_local_writer_is_fail_closed_and_leaves_no_private_copy(tmp_path):
    writer = PrivateDatabaseWriter(tmp_path)

    with pytest.raises(PrivateDatabasePolicyError, match="已禁用"):
        writer.write_content_bundle(
            content={"id": "c1", "platform": "x"},
            relations=[],
            artifacts=[{"sha256": "a", "local_path": "/secret/path"}],
        )

    assert list(tmp_path.iterdir()) == []
