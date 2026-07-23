from __future__ import annotations

import hashlib
import io
import zipfile
from dataclasses import dataclass
from datetime import UTC, datetime

from stage3_support import make_raw_message
from stage3_support import synthetic_pdf as _synthetic_pdf

from moomooau_archive.canonical_raw import CanonicalRaw
from moomooau_archive.gmail_discovery import (
    DiscoveryResult,
    FilterAudit,
    HeaderSnapshot,
    HistoryExpired,
    MessageListPage,
    MessageRef,
    MinimalMessage,
)
from moomooau_archive.public_inventory import (
    DatasetAvailability,
    PrivateDatasetObservation,
    PublicConclusion,
    PublicInventoryDocument,
    PublicNextAction,
    PublicRunConclusion,
    PublicRunState,
    StrictPublicInventoryPublisher,
)
from moomooau_archive.secret_values import SecretBytes


def synthetic_pdf() -> bytes:
    return _synthetic_pdf()


def public_document(state: PublicRunState) -> PublicInventoryDocument:
    action = {
        PublicRunState.HEALTHY: PublicNextAction.NONE,
        PublicRunState.DEGRADED_RAW_ONLY: PublicNextAction.RETRY,
        PublicRunState.WAITING_PASSWORD: PublicNextAction.REPROCESS_WITH_PROTECTED_SECRET,
        PublicRunState.M3_FAILED: PublicNextAction.REPAIR_M3,
        PublicRunState.TIMELINE_FAILED: PublicNextAction.REPAIR_TIMELINE,
        PublicRunState.FAILED: PublicNextAction.INVESTIGATE,
        PublicRunState.NOT_RUN: PublicNextAction.RUN_PRODUCTION_ACCEPTANCE,
    }[state]
    if state is PublicRunState.HEALTHY:
        test = recovery = PublicConclusion.PASS
    elif state is PublicRunState.NOT_RUN:
        test = recovery = PublicConclusion.NOT_RUN
    else:
        test = PublicConclusion.FAIL
        recovery = PublicConclusion.FAIL
    conclusion = PublicRunConclusion(state, test, recovery, action)
    observation = PrivateDatasetObservation(
        dataset_name="statements",
        schema_version="1.0.0",
        parser_versions=("1.0.0",),
        availability=DatasetAvailability.AVAILABLE,
        exact_count=17,
        latest_recorded_at_utc=datetime(2026, 7, 20, tzinfo=UTC),
        private_snapshot_root="a" * 64,
    )
    key = SecretBytes(b"synthetic-stage6-public-root-key-material")
    try:
        return StrictPublicInventoryPublisher().render(
            (observation,),
            conclusion,
            now_utc=datetime(2026, 7, 20, 1, tzinfo=UTC),
            opaque_root_key=key,
        )
    finally:
        key.destroy()


def canonical_with_attachments(
    attachments: tuple[tuple[str, str, str, bytes], ...],
    *,
    suffix: str = "stage6",
) -> CanonicalRaw:
    raw = make_raw_message(message_id=f"synthetic-{suffix}", attachments=attachments)
    return CanonicalRaw(
        message_id=f"synthetic-{suffix}",
        thread_id=f"thread-synthetic-{suffix}",
        internal_date_ms=1_767_225_600_000,
        label_ids=("INBOX",),
        plaintext_sha256=hashlib.sha256(raw).hexdigest(),
        byte_count=len(raw),
        data=raw,
    )


def synthetic_xlsx(*, macro: bool = False, bomb_bytes: int = 0) -> bytes:
    sink = io.BytesIO()
    with zipfile.ZipFile(sink, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("[Content_Types].xml", "<Types/>")
        archive.writestr("xl/workbook.xml", "<workbook/>")
        archive.writestr("xl/worksheets/sheet1.xml", "<sheet/>")
        if macro:
            archive.writestr("xl/vbaProject.bin", b"synthetic-active-content")
        if bomb_bytes:
            archive.writestr("xl/sharedStrings.xml", "A" * bomb_bytes)
    return sink.getvalue()


class GeneratedMailboxClient:
    """Generate page contents on demand so the load fixture itself stays bounded."""

    def __init__(
        self,
        *,
        pages: int,
        refs_per_page: int,
        fail_at_page: int | None = None,
    ) -> None:
        self.pages = pages
        self.refs_per_page = refs_per_page
        self.fail_at_page = fail_at_page
        self.calls = 0

    def list_message_page(
        self,
        *,
        label_id: str | None,
        page_token: str | None,
    ) -> MessageListPage:
        self.calls += 1
        if label_id is not None:
            return MessageListPage((), None)
        page = int(page_token.removeprefix("page-")) if page_token is not None else 0
        if self.fail_at_page is not None and page == self.fail_at_page:
            raise ConnectionError("synthetic page interruption")
        if not 0 <= page < self.pages:
            raise AssertionError("generated page is outside the fixture")
        start = page * self.refs_per_page
        refs = tuple(
            MessageRef(f"msg-{index:06d}", f"thread-{index:06d}")
            for index in range(start, start + self.refs_per_page)
        )
        token = f"page-{page + 1}" if page + 1 < self.pages else None
        return MessageListPage(refs, token)

    def list_filters(self) -> FilterAudit:
        return FilterAudit(0, 0, 0)


@dataclass
class StaticDiscoverer:
    refs: tuple[MessageRef, ...]

    def scan(self) -> DiscoveryResult:
        all_ids = frozenset(item.message_id for item in self.refs)
        return DiscoveryResult(
            refs=self.refs,
            scope_ids=(
                ("ALL_MAIL", all_ids),
                ("INBOX", all_ids),
                ("SPAM", frozenset()),
                ("TRASH", frozenset()),
            ),
            filter_audit=FilterAudit(0, 0, 0),
            watermark_message_id=self.refs[0].message_id if self.refs else None,
            pages_read=4,
        )


class ExpiredHistoryClient:
    def __init__(self, refs: tuple[MessageRef, ...]) -> None:
        self.refs = refs

    def list_history_page(self, start_history_id: str, *, page_token: str | None):  # type: ignore[no-untyped-def]
        raise HistoryExpired("synthetic expired watermark")

    def get_metadata(
        self,
        message_id: str,
        *,
        header_names: tuple[str, ...],
    ) -> MinimalMessage:
        ref = next(item for item in self.refs if item.message_id == message_id)
        return MinimalMessage(
            ref=ref,
            history_id="9001",
            internal_date_ms=1_767_225_600_000,
            label_ids=("INBOX",),
            headers=HeaderSnapshot((("From", "synthetic source"),)),
        )
