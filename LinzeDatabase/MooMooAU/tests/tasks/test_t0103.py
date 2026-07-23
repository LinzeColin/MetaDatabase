from __future__ import annotations

from email import policy
from email.parser import BytesParser

from moomooau_archive.fixtures import (
    build_fixture_set,
    decode_gmail_raw,
    gmail_raw_base64url,
)
from moomooau_archive.security import inspect_attachment


def test_t0103_fixture_factory_is_deterministic_and_raw_canonical() -> None:
    first = build_fixture_set()
    second = build_fixture_set()
    assert first == second
    assert decode_gmail_raw(gmail_raw_base64url(first.verified)) == first.verified.raw
    parsed = BytesParser(policy=policy.default).parsebytes(first.verified.raw)
    attachments = list(parsed.iter_attachments())
    assert len(attachments) == 2
    assert {item.get_filename() for item in attachments} == {
        "synthetic-statement.pdf",
        "synthetic-table.xlsx",
    }
    assert first.verified.metadata.internal_date_ms > 0
    assert first.verified.metadata.labels == ("INBOX", "SYNTHETIC")
    assert first.verified.metadata.authentication.all_pass


def test_t0103_spoof_unrelated_and_abuse_fixtures_are_fail_closed() -> None:
    fixtures = build_fixture_set()
    assert fixtures.unrelated.metadata.sender != fixtures.verified.metadata.sender
    assert not fixtures.spoofed.metadata.authentication.all_pass
    observed = {
        item.name: inspect_attachment(
            item.name,
            item.content,
            declared_size=item.declared_size,
        ).disposition
        for item in fixtures.abuse_attachments
    }
    assert observed == {item.name: item.expected_disposition for item in fixtures.abuse_attachments}
