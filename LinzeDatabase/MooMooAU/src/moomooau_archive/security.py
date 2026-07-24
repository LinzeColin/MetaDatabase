"""Non-executing magic-byte triage for Stage 1 abuse fixtures."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import PurePosixPath


@dataclass(frozen=True, slots=True)
class AttachmentDisposition:
    disposition: str
    reason_code: str


def inspect_attachment(
    filename: str,
    content: bytes,
    *,
    declared_size: int | None = None,
    maximum_size: int = 100_000_000,
) -> AttachmentDisposition:
    path = PurePosixPath(filename.replace("\\", "/"))
    if path.name != filename or ".." in path.parts or path.is_absolute():
        return AttachmentDisposition("QUARANTINED", "PATH_TRAVERSAL")
    if (declared_size if declared_size is not None else len(content)) > maximum_size:
        return AttachmentDisposition("QUARANTINED", "SIZE_LIMIT")
    lowered = content.lower()
    if content.startswith(b"%PDF-"):
        if (
            b"<script" in lowered
            or b"/javascript" in lowered
            or not content.rstrip().endswith(b"%%EOF")
        ):
            return AttachmentDisposition("QUARANTINED", "UNSAFE_OR_MALFORMED_PDF")
        return AttachmentDisposition("PDF", "PDF_MAGIC")
    if filename.casefold().endswith(".xlsx"):
        if not content.startswith(b"PK\x03\x04"):
            return AttachmentDisposition("QUARANTINED", "MALFORMED_XLSX")
        return AttachmentDisposition("XLSX", "ZIP_MAGIC")
    return AttachmentDisposition("UNSUPPORTED", "NO_SAFE_PARSER")
