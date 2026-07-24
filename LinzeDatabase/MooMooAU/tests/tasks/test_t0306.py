from __future__ import annotations

import hashlib
import io
import zipfile

from stage3_support import make_raw_message, synthetic_pdf

from moomooau_archive.attachment_inspector import (
    AttachmentDecision,
    AttachmentInspector,
    AttachmentKind,
    AttachmentLimits,
)
from moomooau_archive.canonical_raw import CanonicalRaw


def _xlsx(*, bomb: bool = False, macro: bool = False) -> bytes:
    sink = io.BytesIO()
    with zipfile.ZipFile(sink, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("[Content_Types].xml", "<Types/>")
        archive.writestr("xl/workbook.xml", "<workbook/>")
        archive.writestr("xl/worksheets/sheet1.xml", "<sheet/>")
        if bomb:
            archive.writestr("xl/sharedStrings.xml", "A" * 1_000_000)
        if macro:
            archive.writestr("xl/vbaProject.bin", b"synthetic-macro")
    return sink.getvalue()


def _canonical(attachments: tuple[tuple[str, str, str, bytes], ...]) -> CanonicalRaw:
    raw = make_raw_message(message_id="synthetic-attachments-1", attachments=attachments)
    return CanonicalRaw(
        message_id="synthetic-attachments-1",
        thread_id="thread-synthetic-attachments-1",
        internal_date_ms=1_767_225_600_000,
        label_ids=("INBOX",),
        plaintext_sha256=hashlib.sha256(raw).hexdigest(),
        byte_count=len(raw),
        data=raw,
    )


def test_t0306_magic_bytes_override_octet_stream_and_unsafe_formats_quarantine() -> None:
    canonical = _canonical(
        (
            ("synthetic.pdf", "application", "octet-stream", synthetic_pdf()),
            (
                "synthetic.xlsx",
                "application",
                "vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                _xlsx(),
            ),
            ("synthetic.csv", "text", "csv", b"kind,value\nsynthetic,1\n"),
            ("../../escape.txt", "text", "plain", b"synthetic"),
            (
                "active.pdf",
                "application",
                "pdf",
                b"%PDF-1.7\n/OpenAction /JavaScript\n%%EOF\n",
            ),
            ("corrupt.xlsx", "application", "octet-stream", b"not-a-zip"),
            ("formula.csv", "text", "csv", b"kind,value\nsynthetic,=1+1\n"),
            (
                "unicode-formula.csv",
                "text",
                "csv",
                "kind,value\nsynthetic,＝1+1\n".encode(),
            ),
            ("macro.xlsx", "application", "octet-stream", _xlsx(macro=True)),
            ("bomb.xlsx", "application", "octet-stream", _xlsx(bomb=True)),
        )
    )
    report = AttachmentInspector().inspect(canonical)
    observed = {
        item.filename: (item.decision, item.kind, item.reason_code) for item in report.attachments
    }

    assert observed["synthetic.pdf"][:2] == (AttachmentDecision.SAFE, AttachmentKind.PDF)
    assert observed["synthetic.xlsx"][:2] == (AttachmentDecision.SAFE, AttachmentKind.XLSX)
    assert observed["synthetic.csv"][:2] == (AttachmentDecision.SAFE, AttachmentKind.CSV)
    assert observed["../../escape.txt"][0] is AttachmentDecision.QUARANTINED
    assert observed["active.pdf"][2] == "ACTIVE_OR_POLYGLOT_PDF"
    assert observed["corrupt.xlsx"][2] == "XLSX_MAGIC_MISMATCH"
    assert observed["formula.csv"][2] == "CSV_FORMULA"
    assert observed["unicode-formula.csv"][2] == "CSV_FORMULA"
    assert observed["macro.xlsx"][2] == "ACTIVE_XLSX_CONTENT"
    assert observed["bomb.xlsx"][2] == "ZIP_BOMB_LIMIT"
    assert not report.message_quarantined
    assert all(
        item.content is not None or item.reason_code == "UNSAFE_FILENAME"
        for item in report.attachments
    )

    nested_raw = (
        b"MIME-Version: 1.0\r\n"
        b"Content-Type: multipart/mixed; boundary=outer\r\n\r\n"
        b"--outer\r\n"
        b"Content-Type: message/rfc822\r\n"
        b"Content-Disposition: attachment; filename=nested.eml\r\n\r\n"
        b"From: synthetic-source\r\nSubject: nested\r\n\r\nbody\r\n"
        b"--outer--\r\n"
    )
    nested = CanonicalRaw(
        message_id="synthetic-nested-1",
        thread_id="thread-synthetic-nested-1",
        internal_date_ms=1_767_225_600_000,
        label_ids=("INBOX",),
        plaintext_sha256=hashlib.sha256(nested_raw).hexdigest(),
        byte_count=len(nested_raw),
        data=nested_raw,
    )
    nested_report = AttachmentInspector().inspect(nested)
    assert len(nested_report.attachments) == 1
    assert nested_report.attachments[0].reason_code == "NESTED_MESSAGE"
    assert nested_report.attachments[0].content is None


def test_t0306_size_and_timeout_limits_fail_closed_without_execution() -> None:
    oversized = _canonical((("large.bin", "application", "octet-stream", b"X" * 4096),))
    size_limits = AttachmentLimits(
        maximum_attachment_bytes=1024,
        maximum_total_decoded_bytes=2048,
    )
    size_report = AttachmentInspector(size_limits).inspect(oversized)
    assert len(size_report.attachments) == 1
    assert size_report.attachments[0].decision is AttachmentDecision.QUARANTINED
    assert size_report.attachments[0].reason_code in {
        "ENCODED_SIZE_LIMIT",
        "DECODED_SIZE_LIMIT",
    }
    assert size_report.attachments[0].content is None

    ticks = iter((0.0, 10.0, 10.0))
    timeout_report = AttachmentInspector(
        AttachmentLimits(timeout_seconds=1.0),
        clock=lambda: next(ticks),
    ).inspect(_canonical(()))
    assert timeout_report.message_quarantined
    assert timeout_report.message_reason_code == "INSPECTION_TIMEOUT"
    assert timeout_report.attachments == ()
