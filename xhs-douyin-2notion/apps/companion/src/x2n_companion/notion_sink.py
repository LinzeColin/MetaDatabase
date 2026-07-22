"""Credential-free Notion projection contract, mock transport and Outbox worker."""

from __future__ import annotations

import hashlib
import json
import re
import threading
import uuid
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any, Protocol, TypeVar

from x2n_contracts import ErrorCode, SinkReceipt, build_sink_key, canonical_json_sha256

from .canonical_store import CanonicalStore, OutboxClaim, WriteDisposition
from .runtime import X2NRuntimeError
from .sink_projection import SinkProjection, validate_persistable_text


NOTION_API_VERSION = "2026-03-11"
NOTION_SINK_SCHEMA_VERSION = "1.0.0"
NOTION_DEFAULT_REQUESTS_PER_SECOND = 2
NOTION_MAX_ATTEMPTS = 4
TRANSITION_AFTER_NOTION_SUCCESS = "after_notion_success_before_local_receipt"
_MOCK_NAMESPACE = uuid.UUID("73864ebf-09d3-4c36-8adc-e85c1b1863f2")
_NOTION_ERROR_CODE = re.compile(r"^[a-z][a-z0-9_]{0,63}$")
T = TypeVar("T")


@dataclass(frozen=True)
class NotionPropertySpec:
    type_name: str
    request: dict[str, Any]


@dataclass(frozen=True)
class NotionProjection:
    content_key: str
    desired_projection_hash: str
    properties: dict[str, Any] = field(repr=False)
    children: tuple[dict[str, Any], ...] = field(repr=False)

    def output_hash(self) -> str:
        return canonical_json_sha256({"children": list(self.children), "properties": self.properties})


@dataclass(frozen=True)
class NotionPage:
    page_ref: str = field(repr=False)
    content_key: str
    projection_hash: str
    output_hash: str
    properties: dict[str, Any] = field(repr=False)
    children: tuple[dict[str, Any], ...] = field(repr=False)


@dataclass(frozen=True)
class NotionDelivery:
    event_id: str
    state: str
    disposition: WriteDisposition
    attempt_count: int
    remote_write: str

    def safe_dict(self) -> dict[str, Any]:
        return {
            "attempt_count": self.attempt_count,
            "disposition": self.disposition.value,
            "event_id": self.event_id,
            "remote_write": self.remote_write,
            "state": self.state,
        }


class NotionTransportError(RuntimeError):
    def __init__(self, *, status: int, code: str, retry_after_seconds: int | None = None) -> None:
        super().__init__(code)
        if (
            not isinstance(status, int)
            or isinstance(status, bool)
            or status < 100
            or status > 599
            or not isinstance(code, str)
            or _NOTION_ERROR_CODE.fullmatch(code) is None
            or retry_after_seconds is not None
            and (
                not isinstance(retry_after_seconds, int)
                or isinstance(retry_after_seconds, bool)
                or retry_after_seconds < 0
                or retry_after_seconds > 86_400
            )
        ):
            raise ValueError("Notion transport error is invalid")
        self.status = status
        self.code = code
        self.retry_after_seconds = retry_after_seconds


class NotionSchemaConflict(RuntimeError):
    pass


class NotionDuplicatePage(RuntimeError):
    pass


class NotionTransport(Protocol):
    items_data_source_id: str
    categories_data_source_id: str

    def retrieve_schema(self, data_source: str) -> Mapping[str, Mapping[str, Any]]: ...

    def patch_schema(self, data_source: str, additions: Mapping[str, Mapping[str, Any]]) -> None: ...

    def find_pages(self, content_key: str) -> tuple[NotionPage, ...]: ...

    def retrieve_page(self, page_ref: str) -> NotionPage | None: ...

    def create_page(self, projection: NotionProjection) -> NotionPage: ...

    def update_page(self, page_ref: str, projection: NotionProjection) -> NotionPage: ...


def category_schema_specs() -> dict[str, NotionPropertySpec]:
    return {
        "Category ID": NotionPropertySpec("rich_text", {"rich_text": {}}),
        "Name": NotionPropertySpec("title", {"title": {}}),
        "Slug": NotionPropertySpec("rich_text", {"rich_text": {}}),
    }


def item_schema_specs(categories_data_source_id: str) -> dict[str, NotionPropertySpec]:
    try:
        category_id = str(uuid.UUID(categories_data_source_id))
    except (ValueError, TypeError, AttributeError):
        raise X2NRuntimeError(ErrorCode.INVALID_INPUT, "Notion Categories Data Source identity is invalid") from None
    return {
        "Captured At": NotionPropertySpec("date", {"date": {}}),
        "Category": NotionPropertySpec(
            "relation",
            {"relation": {"data_source_id": category_id, "single_property": {}}},
        ),
        "Content Key": NotionPropertySpec("rich_text", {"rich_text": {}}),
        "Name": NotionPropertySpec("title", {"title": {}}),
        "Platform": NotionPropertySpec("select", {"select": {}}),
        "Projection Hash": NotionPropertySpec("rich_text", {"rich_text": {}}),
        "Relations": NotionPropertySpec("multi_select", {"multi_select": {}}),
        "Review Status": NotionPropertySpec("select", {"select": {}}),
        "Source URL": NotionPropertySpec("url", {"url": {}}),
    }


def plan_additive_schema(
    existing: Mapping[str, Mapping[str, Any]],
    required: Mapping[str, NotionPropertySpec],
) -> dict[str, dict[str, Any]]:
    additions: dict[str, dict[str, Any]] = {}
    for name, spec in required.items():
        current = existing.get(name)
        if current is None:
            additions[name] = json.loads(json.dumps(spec.request, sort_keys=True))
            continue
        if current.get("type") != spec.type_name:
            raise NotionSchemaConflict(f"required property type conflicts: {name}")
        if spec.type_name == "relation":
            current_target = current.get("relation", {}).get("data_source_id")
            required_target = spec.request["relation"]["data_source_id"]
            if current_target != required_target:
                raise NotionSchemaConflict(f"required relation target conflicts: {name}")
    return additions


def _rich_text(value: str) -> list[dict[str, Any]]:
    return [{"type": "text", "text": {"content": value}}]


def _paragraph_chunks(value: str) -> list[dict[str, Any]]:
    if not value:
        return []
    chunks: list[dict[str, Any]] = []
    for offset in range(0, len(value), 2_000):
        chunks.append(
            {
                "object": "block",
                "paragraph": {"rich_text": _rich_text(value[offset : offset + 2_000])},
                "type": "paragraph",
            }
        )
    return chunks


def build_notion_projection(
    projection: SinkProjection,
    *,
    category_page_ref: str | None = None,
) -> NotionProjection:
    content = projection.canonical.content
    observation = projection.canonical.observation
    category_relation: list[dict[str, str]] = []
    if projection.category_id is not None:
        if category_page_ref is None:
            raise X2NRuntimeError(ErrorCode.POLICY_BLOCKED, "Owner category lacks a Notion mapping")
        try:
            category_relation = [{"id": str(uuid.UUID(category_page_ref))}]
        except (ValueError, TypeError, AttributeError):
            raise X2NRuntimeError(ErrorCode.DATA_INTEGRITY_FAILED, "Notion Category page identity is invalid") from None
    properties: dict[str, Any] = {
        "Captured At": {
            "date": {"start": observation.observed_at.isoformat().replace("+00:00", "Z")},
            "type": "date",
        },
        "Category": {"relation": category_relation, "type": "relation"},
        "Content Key": {"rich_text": _rich_text(content.content_key), "type": "rich_text"},
        "Name": {"title": _rich_text(projection.title[:2_000]), "type": "title"},
        "Platform": {"select": {"name": content.platform.value}, "type": "select"},
        "Projection Hash": {
            "rich_text": _rich_text(projection.desired_projection_hash),
            "type": "rich_text",
        },
        "Relations": {
            "multi_select": [{"name": value} for value in projection.canonical.relations],
            "type": "multi_select",
        },
        "Review Status": {"select": {"name": projection.review_status}, "type": "select"},
        "Source URL": {"type": "url", "url": content.canonical_source_url},
    }
    children: list[dict[str, Any]] = []
    for heading, value in (
        ("Original text", projection.text.original_text),
        ("Summary", projection.text.summary),
        ("Transcript", projection.text.transcript),
        ("OCR", projection.text.ocr),
        ("Vision", projection.text.vision),
        ("Classification rationale", projection.text.classification_reason),
    ):
        if not value:
            continue
        children.append(
            {
                "heading_2": {"rich_text": _rich_text(heading)},
                "object": "block",
                "type": "heading_2",
            }
        )
        children.extend(_paragraph_chunks(value))
    provenance = json.dumps(
        {
            "adapter_name": observation.adapter_name,
            "adapter_version": observation.adapter_version,
            "artifact_ids": [item.artifact_id for item in projection.canonical.artifacts],
            "observation_id": observation.observation_id,
            "raw_text_hash": observation.raw_text_hash,
            "run_id": observation.run_id,
        },
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    )
    children.append(
        {
            "heading_2": {"rich_text": _rich_text("Provenance")},
            "object": "block",
            "type": "heading_2",
        }
    )
    children.extend(_paragraph_chunks(provenance))
    if len(children) > 100:
        raise X2NRuntimeError(ErrorCode.POLICY_BLOCKED, "Notion projection exceeds the request block limit")
    rendered = json.dumps(
        {"children": children, "properties": properties},
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")
    if len(rendered) > 500_000:
        raise X2NRuntimeError(ErrorCode.POLICY_BLOCKED, "Notion projection exceeds the request size limit")
    validate_persistable_text(rendered.decode("utf-8"))
    return NotionProjection(
        content_key=content.content_key,
        desired_projection_hash=projection.desired_projection_hash,
        properties=properties,
        children=tuple(children),
    )


class RequestRateGate:
    """Serialized monotonic gate; default interval is exactly 0.5 seconds."""

    def __init__(
        self,
        *,
        requests_per_second: int = NOTION_DEFAULT_REQUESTS_PER_SECOND,
        monotonic: Callable[[], float],
        sleeper: Callable[[float], None],
    ) -> None:
        if (
            not isinstance(requests_per_second, int)
            or isinstance(requests_per_second, bool)
            or requests_per_second < 1
            or requests_per_second > NOTION_DEFAULT_REQUESTS_PER_SECOND
        ):
            raise X2NRuntimeError(ErrorCode.POLICY_BLOCKED, "Notion request rate exceeds local policy")
        self.interval = 1.0 / requests_per_second
        self.monotonic = monotonic
        self.sleeper = sleeper
        self._last_request: float | None = None
        self._lock = threading.Lock()

    def acquire(self) -> None:
        with self._lock:
            current = self.monotonic()
            if self._last_request is not None:
                remaining = self.interval - (current - self._last_request)
                if remaining > 0:
                    self.sleeper(remaining)
                    current = self.monotonic()
            self._last_request = current


class RateLimitedNotionClient:
    def __init__(self, transport: NotionTransport, gate: RequestRateGate) -> None:
        self.transport = transport
        self.gate = gate
        self.items_data_source_id = transport.items_data_source_id
        self.categories_data_source_id = transport.categories_data_source_id

    def _call(self, function: Callable[..., T], *args: Any) -> T:
        self.gate.acquire()
        return function(*args)

    def retrieve_schema(self, data_source: str) -> Mapping[str, Mapping[str, Any]]:
        return self._call(self.transport.retrieve_schema, data_source)

    def patch_schema(self, data_source: str, additions: Mapping[str, Mapping[str, Any]]) -> None:
        self._call(self.transport.patch_schema, data_source, additions)

    def find_pages(self, content_key: str) -> tuple[NotionPage, ...]:
        return self._call(self.transport.find_pages, content_key)

    def retrieve_page(self, page_ref: str) -> NotionPage | None:
        return self._call(self.transport.retrieve_page, page_ref)

    def create_page(self, projection: NotionProjection) -> NotionPage:
        return self._call(self.transport.create_page, projection)

    def update_page(self, page_ref: str, projection: NotionProjection) -> NotionPage:
        return self._call(self.transport.update_page, page_ref, projection)


@dataclass(frozen=True)
class MockFault:
    operation: str
    error: BaseException = field(repr=False)


class NotionMockServer:
    """In-process deterministic Notion semantic double; opens no socket."""

    def __init__(self, *, monotonic: Callable[[], float]) -> None:
        self.monotonic = monotonic
        self.items_data_source_id = str(uuid.uuid5(_MOCK_NAMESPACE, "items-data-source"))
        self.categories_data_source_id = str(uuid.uuid5(_MOCK_NAMESPACE, "categories-data-source"))
        self.schemas: dict[str, dict[str, dict[str, Any]]] = {
            "categories": {
                "Owner Notes": {
                    "id": "owner-notes",
                    "name": "Owner Notes",
                    "rich_text": {},
                    "type": "rich_text",
                }
            },
            "items": {
                "Owner Notes": {
                    "id": "owner-notes",
                    "name": "Owner Notes",
                    "rich_text": {},
                    "type": "rich_text",
                }
            },
        }
        self.pages: dict[str, NotionPage] = {}
        self.timeline: list[dict[str, Any]] = []
        self.faults: list[MockFault] = []
        self.schema_write_count = 0
        self.page_create_count = 0
        self.page_update_count = 0

    def queue_fault(self, operation: str, error: BaseException) -> None:
        self.faults.append(MockFault(operation, error))

    def _request(self, operation: str) -> None:
        self.timeline.append({"operation": operation, "time": self.monotonic()})
        if self.faults and self.faults[0].operation in {operation, "*"}:
            fault = self.faults.pop(0)
            raise fault.error

    def retrieve_schema(self, data_source: str) -> Mapping[str, Mapping[str, Any]]:
        self._request(f"retrieve_schema:{data_source}")
        if data_source not in self.schemas:
            raise NotionTransportError(status=404, code="object_not_found")
        return json.loads(json.dumps(self.schemas[data_source], sort_keys=True))

    def patch_schema(self, data_source: str, additions: Mapping[str, Mapping[str, Any]]) -> None:
        self._request(f"patch_schema:{data_source}")
        schema = self.schemas[data_source]
        for name, request in additions.items():
            if name in schema or len(request) != 1:
                raise NotionSchemaConflict(f"invalid additive schema patch: {name}")
            type_name = next(iter(request))
            schema[name] = {
                "id": hashlib.sha256(f"{data_source}:{name}".encode("utf-8")).hexdigest()[:12],
                "name": name,
                "type": type_name,
                type_name: json.loads(json.dumps(request[type_name], sort_keys=True)),
            }
        if additions:
            self.schema_write_count += 1

    def find_pages(self, content_key: str) -> tuple[NotionPage, ...]:
        self._request("find_pages")
        return tuple(
            sorted((page for page in self.pages.values() if page.content_key == content_key), key=lambda p: p.page_ref)
        )

    def retrieve_page(self, page_ref: str) -> NotionPage | None:
        self._request("retrieve_page")
        return self.pages.get(page_ref)

    @staticmethod
    def _page(projection: NotionProjection, page_ref: str, existing: NotionPage | None = None) -> NotionPage:
        properties = {} if existing is None else json.loads(json.dumps(existing.properties, sort_keys=True))
        properties.update(json.loads(json.dumps(projection.properties, sort_keys=True)))
        return NotionPage(
            page_ref=page_ref,
            content_key=projection.content_key,
            projection_hash=projection.desired_projection_hash,
            output_hash=projection.output_hash(),
            properties=properties,
            children=tuple(json.loads(json.dumps(list(projection.children), sort_keys=True))),
        )

    def create_page(self, projection: NotionProjection) -> NotionPage:
        self._request("create_page")
        suffix = sum(1 for page in self.pages.values() if page.content_key == projection.content_key)
        page_ref = str(uuid.uuid5(_MOCK_NAMESPACE, f"page:{projection.content_key}:{suffix}"))
        page = self._page(projection, page_ref)
        self.pages[page_ref] = page
        self.page_create_count += 1
        return page

    def update_page(self, page_ref: str, projection: NotionProjection) -> NotionPage:
        self._request("update_page")
        existing = self.pages.get(page_ref)
        if existing is None:
            raise NotionTransportError(status=404, code="object_not_found")
        page = self._page(projection, page_ref, existing)
        self.pages[page_ref] = page
        self.page_update_count += 1
        return page


class NotionSinkWorker:
    def __init__(
        self,
        store: CanonicalStore,
        client: RateLimitedNotionClient,
        *,
        category_page_refs: Mapping[str, str] | None = None,
        max_attempts: int = NOTION_MAX_ATTEMPTS,
    ) -> None:
        if (
            not isinstance(max_attempts, int)
            or isinstance(max_attempts, bool)
            or max_attempts < 1
            or max_attempts > NOTION_MAX_ATTEMPTS
        ):
            raise X2NRuntimeError(ErrorCode.POLICY_BLOCKED, "Notion attempt policy is invalid")
        self.store = store
        self.client = client
        self.category_page_refs = dict(category_page_refs or {})
        self.max_attempts = max_attempts

    def _ensure_schema(self) -> None:
        categories = self.client.retrieve_schema("categories")
        items = self.client.retrieve_schema("items")
        category_additions = plan_additive_schema(categories, category_schema_specs())
        item_additions = plan_additive_schema(items, item_schema_specs(self.client.categories_data_source_id))
        if category_additions:
            self.client.patch_schema("categories", category_additions)
        if item_additions:
            self.client.patch_schema("items", item_additions)

    @staticmethod
    def _receipt(projection: SinkProjection, page: NotionPage, delivered_at: str) -> SinkReceipt:
        content_key = projection.canonical.content.content_key
        identity = hashlib.sha256(
            f"notion:{content_key}:{projection.desired_projection_hash}:{NOTION_SINK_SCHEMA_VERSION}".encode("utf-8")
        ).hexdigest()
        external_ref_hash = hashlib.sha256(page.page_ref.encode("utf-8")).hexdigest()
        return SinkReceipt.model_validate_json(
            json.dumps(
                {
                    "content_key": content_key,
                    "delivered_at": delivered_at,
                    "desired_projection_hash": projection.desired_projection_hash,
                    "external_ref_hash": external_ref_hash,
                    "output_hash": page.output_hash,
                    "receipt_id": f"receipt_notion_{identity[:32]}",
                    "run_id": projection.canonical.observation.run_id,
                    "schema_version": "1.0",
                    "sink": "notion",
                    "sink_key": build_sink_key("notion", content_key, NOTION_SINK_SCHEMA_VERSION),
                    "sink_object_ref": f"sinkref_notion_{identity[:32]}",
                    "sink_schema_version": NOTION_SINK_SCHEMA_VERSION,
                    "status": "verified",
                },
                ensure_ascii=False,
            )
        )

    @staticmethod
    def _scheduled_at(now: str, claim: OutboxClaim, retry_after_seconds: int | None) -> str:
        parsed = datetime.strptime(now, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
        backoff = min(2 ** max(0, claim.attempt_count - 1), 60)
        minimum = max(backoff, retry_after_seconds or 0)
        jitter_seed = hashlib.sha256(f"{claim.event_id}:{claim.attempt_count}".encode("utf-8")).digest()[0]
        jitter = 1 if jitter_seed % 2 else 0
        return (parsed + timedelta(seconds=minimum + jitter)).isoformat().replace("+00:00", "Z")

    def _retry_or_dead_letter(
        self,
        claim: OutboxClaim,
        *,
        error_code: str,
        now: str,
        retry_after_seconds: int | None,
    ) -> NotionDelivery:
        normalized = "notion_" + "".join(
            character if character.isalnum() or character in "._-" else "_" for character in error_code
        )
        if claim.attempt_count >= self.max_attempts:
            self.store.dead_letter_outbox(claim, error_code=normalized, now=now)
            return NotionDelivery(claim.event_id, "dead_letter", WriteDisposition.UPDATED, claim.attempt_count, "none")
        not_before = self._scheduled_at(now, claim, retry_after_seconds)
        self.store.retry_outbox(claim, error_code=normalized, not_before=not_before, now=now)
        return NotionDelivery(claim.event_id, "pending", WriteDisposition.UPDATED, claim.attempt_count, "none")

    @staticmethod
    def _error_code(value: str) -> str:
        return "notion_" + "".join(
            character if character.isalnum() or character in "._-" else "_" for character in value
        )

    def process(
        self,
        projection: SinkProjection,
        *,
        now: str,
        transition_hook: Callable[[str], None] | None = None,
    ) -> NotionDelivery:
        category_page_ref = None
        if projection.category_id is not None:
            category_page_ref = self.category_page_refs.get(projection.category_id)
        notion_projection = build_notion_projection(projection, category_page_ref=category_page_ref)
        disposition, event_id = self.store.enqueue_outbox(
            sink="notion",
            content_key=projection.canonical.content.content_key,
            desired_projection_hash=projection.desired_projection_hash,
            sink_schema_version=NOTION_SINK_SCHEMA_VERSION,
            now=now,
        )
        state = self.store.outbox_state(event_id)
        if state is None:
            raise X2NRuntimeError(ErrorCode.DATA_INTEGRITY_FAILED, "Notion Outbox event is unavailable")
        if state.status == "delivered":
            return NotionDelivery(event_id, "delivered", WriteDisposition.UNCHANGED, state.attempt_count, "none")
        if state.status == "dead_letter":
            return NotionDelivery(event_id, "dead_letter", WriteDisposition.UNCHANGED, state.attempt_count, "none")
        claim = self.store.claim_outbox(
            worker_id="notion-worker-v1",
            sink="notion",
            event_id=event_id,
            now=now,
        )
        if claim is None:
            return NotionDelivery(event_id, state.status, disposition, state.attempt_count, "none")
        if claim.event_id != event_id or claim.desired_projection_hash != projection.desired_projection_hash:
            raise X2NRuntimeError(ErrorCode.DATA_INTEGRITY_FAILED, "Notion worker claimed an unexpected event")
        remote_write = "none"
        try:
            self._ensure_schema()
            mapping = self.store.notion_mapping(claim.content_key)
            page: NotionPage | None
            if mapping is not None:
                page = self.client.retrieve_page(mapping.page_ref)
                if page is None or page.content_key != claim.content_key:
                    raise NotionDuplicatePage("private mapping does not resolve to its Content")
            else:
                pages = self.client.find_pages(claim.content_key)
                if len(pages) > 1:
                    raise NotionDuplicatePage("multiple pages share one content_key")
                page = pages[0] if pages else None
            if page is None:
                page = self.client.create_page(notion_projection)
                remote_write = "create"
            elif page.projection_hash != notion_projection.desired_projection_hash:
                page = self.client.update_page(page.page_ref, notion_projection)
                remote_write = "update"
            if transition_hook is not None:
                transition_hook(TRANSITION_AFTER_NOTION_SUCCESS)
            self.store.record_notion_mapping(content_key=claim.content_key, page_ref=page.page_ref, now=now)
            receipt = self._receipt(projection, page, now)
            self.store.complete_outbox(claim, receipt)
            return NotionDelivery(event_id, "delivered", disposition, claim.attempt_count, remote_write)
        except NotionTransportError as error:
            if error.status in {400, 401, 403, 404}:
                self.store.dead_letter_outbox(claim, error_code=self._error_code(error.code), now=now)
                return NotionDelivery(event_id, "dead_letter", WriteDisposition.UPDATED, claim.attempt_count, "none")
            return self._retry_or_dead_letter(
                claim,
                error_code=error.code,
                now=now,
                retry_after_seconds=error.retry_after_seconds,
            )
        except (TimeoutError, ConnectionResetError) as error:
            return self._retry_or_dead_letter(
                claim,
                error_code=type(error).__name__.lower(),
                now=now,
                retry_after_seconds=None,
            )
        except (NotionSchemaConflict, NotionDuplicatePage) as error:
            code = "schema_conflict" if isinstance(error, NotionSchemaConflict) else "duplicate_page"
            self.store.dead_letter_outbox(claim, error_code=f"notion_{code}", now=now)
            return NotionDelivery(event_id, "dead_letter", WriteDisposition.UPDATED, claim.attempt_count, "none")

    def reconcile(self, projection: SinkProjection, *, now: str) -> NotionDelivery:
        """Resume one deterministic Outbox projection after ambiguous remote completion."""

        return self.process(projection, now=now)
