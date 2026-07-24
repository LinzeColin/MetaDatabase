"""Deterministic synthetic Gmail RAW, metadata, MIME and abuse fixtures."""

from __future__ import annotations

import base64
from dataclasses import dataclass
from email import policy
from email.message import EmailMessage

from .models import AuthenticationResults, CandidateMetadata, SyntheticMessage

SYNTHETIC_INTERNAL_DATE_MS = 1_767_225_600_000


def _address(local: str, domain: str) -> str:
    """Construct reserved synthetic addresses without persisting an address literal."""

    return local + chr(64) + domain


def verified_synthetic_sender() -> str:
    return _address("statements", "synthetic.invalid")


def _raw_message(*, sender: str, source_id: str, include_attachments: bool = True) -> bytes:
    message = EmailMessage(policy=policy.SMTP)
    message["From"] = sender
    message["To"] = _address("archive-owner", "synthetic.invalid")
    message["Subject"] = "Synthetic daily archive fixture"
    message["Date"] = "Thu, 01 Jan 2026 00:00:00 +0000"
    message["Message-ID"] = "<" + source_id + chr(64) + "synthetic.invalid>"
    message.set_content("Synthetic fixture only. No account, balance, or production identifier.")
    if include_attachments:
        message.add_attachment(
            b"%PDF-1.7\nsynthetic-document\n%%EOF\n",
            maintype="application",
            subtype="octet-stream",
            filename="synthetic-statement.pdf",
        )
        message.add_attachment(
            b"PK\x03\x04synthetic-xlsx-container",
            maintype="application",
            subtype="vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            filename="synthetic-table.xlsx",
        )
        message.set_boundary("=_MMAU_STAGE1_FIXED_BOUNDARY_001")
    return message.as_bytes(policy=policy.SMTP.clone(linesep="\r\n", max_line_length=78))


@dataclass(frozen=True, slots=True)
class AttachmentFixture:
    name: str
    content: bytes
    declared_size: int
    expected_disposition: str


@dataclass(frozen=True, slots=True)
class FixtureSet:
    verified: SyntheticMessage
    unrelated: SyntheticMessage
    spoofed: SyntheticMessage
    abuse_attachments: tuple[AttachmentFixture, ...]


def build_fixture_set() -> FixtureSet:
    verified_id = "synthetic-source-000001"
    unrelated_id = "synthetic-source-000002"
    spoofed_id = "synthetic-source-000003"
    verified = SyntheticMessage(
        metadata=CandidateMetadata(
            source_id=verified_id,
            sender=verified_synthetic_sender(),
            internal_date_ms=SYNTHETIC_INTERNAL_DATE_MS,
            labels=("INBOX", "SYNTHETIC"),
            authentication=AuthenticationResults("PASS", "PASS", "PASS"),
            synthetic_origin=True,
        ),
        raw=_raw_message(sender=verified_synthetic_sender(), source_id=verified_id),
    )
    unrelated_sender = _address("newsletter", "unrelated.invalid")
    unrelated = SyntheticMessage(
        metadata=CandidateMetadata(
            source_id=unrelated_id,
            sender=unrelated_sender,
            internal_date_ms=SYNTHETIC_INTERNAL_DATE_MS + 1_000,
            labels=("INBOX",),
            authentication=AuthenticationResults("PASS", "PASS", "PASS"),
            synthetic_origin=True,
        ),
        raw=_raw_message(
            sender=unrelated_sender,
            source_id=unrelated_id,
            include_attachments=False,
        ),
    )
    spoofed_sender = _address("statements", "synthetic-lookalike.invalid")
    spoofed = SyntheticMessage(
        metadata=CandidateMetadata(
            source_id=spoofed_id,
            sender=spoofed_sender,
            internal_date_ms=SYNTHETIC_INTERNAL_DATE_MS + 2_000,
            labels=("SPAM", "SYNTHETIC"),
            authentication=AuthenticationResults("FAIL", "FAIL", "FAIL"),
            synthetic_origin=True,
        ),
        raw=_raw_message(sender=spoofed_sender, source_id=spoofed_id),
    )
    abuse = (
        AttachmentFixture(
            "synthetic-octet-stream.pdf",
            b"%PDF-1.7\nsynthetic\n%%EOF\n",
            29,
            "PDF",
        ),
        AttachmentFixture("../../escape.txt", b"synthetic", 9, "QUARANTINED"),
        AttachmentFixture(
            "synthetic-polyglot.pdf",
            b"%PDF-1.7\n<script>synthetic</script>\n%%EOF\n",
            48,
            "QUARANTINED",
        ),
        AttachmentFixture("synthetic-corrupt.xlsx", b"not-a-zip", 9, "QUARANTINED"),
        AttachmentFixture("synthetic-large.bin", b"small-placeholder", 100_000_001, "QUARANTINED"),
        AttachmentFixture("synthetic-formula.csv", b"=1+1\n", 5, "UNSUPPORTED"),
    )
    return FixtureSet(verified, unrelated, spoofed, abuse)


def gmail_raw_base64url(message: SyntheticMessage) -> str:
    return base64.urlsafe_b64encode(message.raw).rstrip(b"=").decode("ascii")


def decode_gmail_raw(value: str) -> bytes:
    padding = "=" * (-len(value) % 4)
    return base64.urlsafe_b64decode(value + padding)
