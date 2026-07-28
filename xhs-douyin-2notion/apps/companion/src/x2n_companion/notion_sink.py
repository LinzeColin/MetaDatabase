"""Credential-free Notion projection contract, mock transport and Outbox worker."""

from __future__ import annotations

import dataclasses
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
NOTION_SINK_SCHEMA_VERSION = "1.1.0"
NOTION_DEFAULT_REQUESTS_PER_SECOND = 2
NOTION_MAX_ATTEMPTS = 4
NOTION_MAX_RICH_TEXT_CHARS = 2_000
NOTION_MAX_CHILD_BLOCKS_PER_REQUEST = 100
NOTION_MAX_TOTAL_CHILD_BLOCKS = 500
NOTION_MAX_REQUEST_BYTES = 500_000
NOTION_SYNC_STATUS_SYNCED = "synced"
NOTION_SYNC_STATUS_FAILED = "failed"
NOTION_PLATFORM_VIEW_VALUES = (
    "xiaohongshu",
    "douyin",
    "bilibili",
    "kuaishou",
    "weibo",
    "taobao",
)
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
    child_batches: tuple[tuple[dict[str, Any], ...], ...] = field(repr=False)

    def output_hash(self) -> str:
        return canonical_json_sha256({"children": list(self.children), "properties": self.properties})


@dataclass(frozen=True)
class NotionPage:
    page_ref: str = field(repr=False)
    content_key: str
    projection_hash: str
    output_hash: str
    properties: dict[str, Any] = field(repr=False)
    managed_properties: dict[str, Any] = field(repr=False)
    children: tuple[dict[str, Any], ...] = field(repr=False)


@dataclass(frozen=True)
class NotionSchemaMigration:
    """One additive-only Notion Data Source migration plan.

    The plan deliberately contains no destructive action.  It is safe to apply
    repeatedly, and its safe receipt only exposes counts and hashes rather than
    Data Source identities.
    """

    schema_version: str
    category_additions: dict[str, dict[str, Any]] = field(repr=False)
    item_additions: dict[str, dict[str, Any]] = field(repr=False)

    def safe_dict(self) -> dict[str, Any]:
        payload = {
            "category_additions": self.category_additions,
            "item_additions": self.item_additions,
            "schema_version": self.schema_version,
        }
        return {
            "category_additions": len(self.category_additions),
            "item_additions": len(self.item_additions),
            "migration_sha256": canonical_json_sha256(payload),
            "schema_version": self.schema_version,
        }


@dataclass(frozen=True)
class NotionViewSpec:
    """An x2n-owned view definition; existing owner views are never mutated."""

    key: str
    name: str
    database_id: str = field(repr=False)
    data_source_id: str = field(repr=False)
    view_type: str
    filter: dict[str, Any] | None = field(default=None, repr=False)
    sorts: tuple[dict[str, Any], ...] = field(default=(), repr=False)
    configuration: dict[str, Any] | None = field(default=None, repr=False)

    def request(self) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "database_id": self.database_id,
            "data_source_id": self.data_source_id,
            "name": self.name,
            "type": self.view_type,
        }
        if self.filter is not None:
            payload["filter"] = self.filter
        if self.sorts:
            payload["sorts"] = list(self.sorts)
        if self.configuration is not None:
            payload["configuration"] = self.configuration
        return payload

    def output_hash(self) -> str:
        return canonical_json_sha256(self.request())


@dataclass(frozen=True)
class NotionView:
    view_ref: str = field(repr=False)
    name: str
    database_id: str = field(repr=False)
    data_source_id: str = field(repr=False)
    view_type: str
    filter: dict[str, Any] | None = field(default=None, repr=False)
    sorts: tuple[dict[str, Any], ...] = field(default=(), repr=False)
    configuration: dict[str, Any] | None = field(default=None, repr=False)

    def output_hash(self) -> str:
        payload: dict[str, Any] = {
            "database_id": self.database_id,
            "data_source_id": self.data_source_id,
            "name": self.name,
            "type": self.view_type,
        }
        if self.filter is not None:
            payload["filter"] = self.filter
        if self.sorts:
            payload["sorts"] = list(self.sorts)
        if self.configuration is not None:
            payload["configuration"] = self.configuration
        return canonical_json_sha256(payload)


@dataclass(frozen=True)
class NotionViewDelivery:
    key: str
    state: str
    output_hash: str
    view_ref_hash: str

    def safe_dict(self) -> dict[str, str]:
        return {
            "key": self.key,
            "output_hash": self.output_hash,
            "state": self.state,
            "view_ref_hash": self.view_ref_hash,
        }


@dataclass(frozen=True)
class NotionViewReconciliation:
    capability: str
    deliveries: tuple[NotionViewDelivery, ...]
    fallback_reason: str | None = None

    def safe_dict(self) -> dict[str, Any]:
        return {
            "capability": self.capability,
            "deliveries": [item.safe_dict() for item in self.deliveries],
            "fallback_reason": self.fallback_reason,
        }


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
    items_database_id: str
    categories_database_id: str

    def retrieve_schema(self, data_source: str) -> Mapping[str, Mapping[str, Any]]: ...

    def patch_schema(self, data_source: str, additions: Mapping[str, Mapping[str, Any]]) -> None: ...

    def find_pages(self, content_key: str) -> tuple[NotionPage, ...]: ...

    def retrieve_page(self, page_ref: str) -> NotionPage | None: ...

    def create_page(
        self,
        projection: NotionProjection,
        children: tuple[dict[str, Any], ...],
    ) -> NotionPage: ...

    def update_page(
        self,
        page_ref: str,
        projection: NotionProjection,
        children: tuple[dict[str, Any], ...],
    ) -> NotionPage: ...

    def append_page_children(self, page_ref: str, children: tuple[dict[str, Any], ...]) -> NotionPage: ...

    def list_views(self, data_source_id: str) -> tuple[NotionView, ...]: ...

    def create_view(self, specification: NotionViewSpec) -> NotionView: ...


def _canonical_notion_uuid(value: str, *, label: str) -> str:
    try:
        parsed = uuid.UUID(value)
    except (ValueError, TypeError, AttributeError):
        raise X2NRuntimeError(ErrorCode.INVALID_INPUT, f"Notion {label} is invalid") from None
    if str(parsed) != value.lower():
        raise X2NRuntimeError(ErrorCode.INVALID_INPUT, f"Notion {label} is invalid")
    return str(parsed)


def category_schema_specs() -> dict[str, NotionPropertySpec]:
    return {
        "Category ID": NotionPropertySpec("rich_text", {"rich_text": {}}),
        "Name": NotionPropertySpec("title", {"title": {}}),
        "Slug": NotionPropertySpec("rich_text", {"rich_text": {}}),
        "X2N Schema Version": NotionPropertySpec("rich_text", {"rich_text": {}}),
    }


def item_schema_specs(categories_data_source_id: str) -> dict[str, NotionPropertySpec]:
    category_id = _canonical_notion_uuid(categories_data_source_id, label="Categories Data Source identity")
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
        "Sync Status": NotionPropertySpec("select", {"select": {}}),
        "X2N Schema Version": NotionPropertySpec("rich_text", {"rich_text": {}}),
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


def plan_schema_migration(
    categories: Mapping[str, Mapping[str, Any]],
    items: Mapping[str, Mapping[str, Any]],
    *,
    categories_data_source_id: str,
) -> NotionSchemaMigration:
    """Build a versioned, additive-only remote schema plan before any write."""

    return NotionSchemaMigration(
        schema_version=NOTION_SINK_SCHEMA_VERSION,
        category_additions=plan_additive_schema(categories, category_schema_specs()),
        item_additions=plan_additive_schema(items, item_schema_specs(categories_data_source_id)),
    )


def _rich_text(value: str) -> list[dict[str, Any]]:
    return [{"type": "text", "text": {"content": value}}]


def _paragraph_chunks(value: str) -> list[dict[str, Any]]:
    if not value:
        return []
    chunks: list[dict[str, Any]] = []
    for fragment in _text_chunks(value):
        chunks.append(
            {
                "object": "block",
                "paragraph": {"rich_text": _rich_text(fragment)},
                "type": "paragraph",
            }
        )
    return chunks


def _text_chunks(value: str) -> tuple[str, ...]:
    """Split exact text on a nearby safe boundary without dropping characters."""

    if not isinstance(value, str):
        raise X2NRuntimeError(ErrorCode.INVALID_INPUT, "Notion text is invalid")
    fragments: list[str] = []
    offset = 0
    while offset < len(value):
        stop = min(offset + NOTION_MAX_RICH_TEXT_CHARS, len(value))
        if stop < len(value):
            boundaries = (
                value.rfind("\n", offset, stop),
                value.rfind(" ", offset, stop),
                value.rfind("。", offset, stop),
                value.rfind("，", offset, stop),
                value.rfind(".", offset, stop),
            )
            candidate = max(boundaries)
            if candidate >= offset + NOTION_MAX_RICH_TEXT_CHARS // 2:
                stop = candidate + 1
        fragments.append(value[offset:stop])
        offset = stop
    return tuple(fragments)


def _child_batches(children: tuple[dict[str, Any], ...]) -> tuple[tuple[dict[str, Any], ...], ...]:
    return tuple(
        children[offset : offset + NOTION_MAX_CHILD_BLOCKS_PER_REQUEST]
        for offset in range(0, len(children), NOTION_MAX_CHILD_BLOCKS_PER_REQUEST)
    )


def item_view_specs(*, database_id: str, data_source_id: str) -> tuple[NotionViewSpec, ...]:
    """Return the strictly x2n-owned Items views for the current Notion API contract."""

    database_id = _canonical_notion_uuid(database_id, label="Items Database identity")
    data_source_id = _canonical_notion_uuid(data_source_id, label="Items Data Source identity")
    table_configuration = {"type": "table", "wrap_cells": True}
    gallery_configuration = {"type": "gallery"}
    recent_first = ({"direction": "descending", "property": "Captured At"},)

    def spec(
        key: str,
        name: str,
        filter_value: dict[str, Any] | None,
        *,
        view_type: str = "table",
        sorts: tuple[dict[str, Any], ...] = (),
    ) -> NotionViewSpec:
        return NotionViewSpec(
            key=key,
            name=name,
            database_id=database_id,
            data_source_id=data_source_id,
            view_type=view_type,
            filter=filter_value,
            sorts=sorts,
            configuration=gallery_configuration if view_type == "gallery" else table_configuration,
        )

    return (
        spec("default_table", "X2N · Default Table", None, sorts=recent_first),
        spec(
            "category_gallery",
            "X2N · Category Gallery",
            {"property": "Category", "relation": {"is_not_empty": True}},
            view_type="gallery",
            sorts=recent_first,
        ),
        spec(
            "likes_inbox",
            "X2N · Likes Inbox",
            {"property": "Relations", "multi_select": {"contains": "liked"}},
            sorts=recent_first,
        ),
        spec(
            "favorites",
            "X2N · Favorites",
            {"property": "Relations", "multi_select": {"contains": "favorited"}},
            sorts=recent_first,
        ),
        spec(
            "needs_review",
            "X2N · Needs Review",
            {"property": "Review Status", "select": {"equals": ["unclassified", "suggested"]}},
            sorts=recent_first,
        ),
        spec(
            "processing_failed",
            "X2N · Processing Failed",
            {"property": "Sync Status", "select": {"equals": NOTION_SYNC_STATUS_FAILED}},
            sorts=recent_first,
        ),
        *tuple(
            spec(
                f"platform_{platform}",
                f"X2N · Platform · {platform.title()}",
                {"property": "Platform", "select": {"equals": platform}},
                sorts=recent_first,
            )
            for platform in NOTION_PLATFORM_VIEW_VALUES
        ),
        spec("recent", "X2N · Recent", None, sorts=recent_first),
    )


def category_view_specs(*, database_id: str, data_source_id: str) -> tuple[NotionViewSpec, ...]:
    """Return the x2n-owned Category directory view without creating categories."""

    database_id = _canonical_notion_uuid(database_id, label="Categories Database identity")
    data_source_id = _canonical_notion_uuid(data_source_id, label="Categories Data Source identity")
    return (
        NotionViewSpec(
            key="category_directory",
            name="X2N · Categories",
            database_id=database_id,
            data_source_id=data_source_id,
            view_type="gallery",
            sorts=({"direction": "ascending", "property": "Name"},),
            configuration={"type": "gallery"},
        ),
    )


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
        "Sync Status": {"select": {"name": NOTION_SYNC_STATUS_SYNCED}, "type": "select"},
        "X2N Schema Version": {
            "rich_text": _rich_text(NOTION_SINK_SCHEMA_VERSION),
            "type": "rich_text",
        },
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
    if len(children) > NOTION_MAX_TOTAL_CHILD_BLOCKS:
        raise X2NRuntimeError(ErrorCode.POLICY_BLOCKED, "Notion projection exceeds the bounded child block limit")
    child_batches = _child_batches(tuple(children))
    if any(
        len(
            json.dumps(list(batch), ensure_ascii=False, separators=(",", ":"), sort_keys=True).encode("utf-8")
        )
        > NOTION_MAX_REQUEST_BYTES
        for batch in child_batches
    ):
        raise X2NRuntimeError(ErrorCode.POLICY_BLOCKED, "Notion child batch exceeds the request size limit")
    rendered = json.dumps(
        {"children": children, "properties": properties},
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")
    if len(rendered) > NOTION_MAX_REQUEST_BYTES:
        raise X2NRuntimeError(ErrorCode.POLICY_BLOCKED, "Notion projection exceeds the request size limit")
    validate_persistable_text(rendered.decode("utf-8"))
    return NotionProjection(
        content_key=content.content_key,
        desired_projection_hash=projection.desired_projection_hash,
        properties=properties,
        children=tuple(children),
        child_batches=child_batches,
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
        self.items_database_id = transport.items_database_id
        self.categories_database_id = transport.categories_database_id

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

    def create_page(self, projection: NotionProjection, children: tuple[dict[str, Any], ...]) -> NotionPage:
        return self._call(self.transport.create_page, projection, children)

    def update_page(
        self,
        page_ref: str,
        projection: NotionProjection,
        children: tuple[dict[str, Any], ...],
    ) -> NotionPage:
        return self._call(self.transport.update_page, page_ref, projection, children)

    def append_page_children(self, page_ref: str, children: tuple[dict[str, Any], ...]) -> NotionPage:
        return self._call(self.transport.append_page_children, page_ref, children)

    def list_views(self, data_source_id: str) -> tuple[NotionView, ...]:
        return self._call(self.transport.list_views, data_source_id)

    def create_view(self, specification: NotionViewSpec) -> NotionView:
        return self._call(self.transport.create_view, specification)


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
        self.items_database_id = str(uuid.uuid5(_MOCK_NAMESPACE, "items-database"))
        self.categories_database_id = str(uuid.uuid5(_MOCK_NAMESPACE, "categories-database"))
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
        self.views: dict[str, NotionView] = {}
        self.timeline: list[dict[str, Any]] = []
        self.faults: list[MockFault] = []
        self.schema_write_count = 0
        self.page_create_count = 0
        self.page_update_count = 0
        self.page_append_count = 0
        self.view_create_count = 0

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
    def _page(
        projection: NotionProjection,
        page_ref: str,
        existing: NotionPage | None = None,
        children: tuple[dict[str, Any], ...] | None = None,
    ) -> NotionPage:
        properties = {} if existing is None else json.loads(json.dumps(existing.properties, sort_keys=True))
        properties.update(json.loads(json.dumps(projection.properties, sort_keys=True)))
        managed_properties = json.loads(json.dumps(projection.properties, sort_keys=True))
        page_children = projection.children if children is None else children
        copied_children = tuple(json.loads(json.dumps(list(page_children), sort_keys=True)))
        return NotionPage(
            page_ref=page_ref,
            content_key=projection.content_key,
            projection_hash=projection.desired_projection_hash,
            output_hash=canonical_json_sha256(
                {"children": list(copied_children), "properties": managed_properties}
            ),
            properties=properties,
            managed_properties=managed_properties,
            children=copied_children,
        )

    def create_page(
        self,
        projection: NotionProjection,
        children: tuple[dict[str, Any], ...] | None = None,
    ) -> NotionPage:
        self._request("create_page")
        child_batch = projection.children if children is None else children
        if len(child_batch) > NOTION_MAX_CHILD_BLOCKS_PER_REQUEST:
            raise NotionSchemaConflict("Notion page creation exceeds the bounded request limit")
        suffix = sum(1 for page in self.pages.values() if page.content_key == projection.content_key)
        page_ref = str(uuid.uuid5(_MOCK_NAMESPACE, f"page:{projection.content_key}:{suffix}"))
        page = self._page(projection, page_ref, children=child_batch)
        self.pages[page_ref] = page
        self.page_create_count += 1
        return page

    def update_page(
        self,
        page_ref: str,
        projection: NotionProjection,
        children: tuple[dict[str, Any], ...] | None = None,
    ) -> NotionPage:
        self._request("update_page")
        existing = self.pages.get(page_ref)
        if existing is None:
            raise NotionTransportError(status=404, code="object_not_found")
        child_batch = projection.children if children is None else children
        if len(child_batch) > NOTION_MAX_CHILD_BLOCKS_PER_REQUEST:
            raise NotionSchemaConflict("Notion page update exceeds the bounded request limit")
        page = self._page(projection, page_ref, existing, children=child_batch)
        self.pages[page_ref] = page
        self.page_update_count += 1
        return page

    def append_page_children(self, page_ref: str, children: tuple[dict[str, Any], ...]) -> NotionPage:
        self._request("append_page_children")
        if len(children) > NOTION_MAX_CHILD_BLOCKS_PER_REQUEST:
            raise NotionSchemaConflict("Notion child append exceeds the bounded request limit")
        existing = self.pages.get(page_ref)
        if existing is None:
            raise NotionTransportError(status=404, code="object_not_found")
        copied_children = tuple(json.loads(json.dumps(list(children), sort_keys=True)))
        merged_children = (*existing.children, *copied_children)
        page = dataclasses.replace(
            existing,
            output_hash=canonical_json_sha256(
                {"children": list(merged_children), "properties": existing.managed_properties}
            ),
            children=merged_children,
        )
        self.pages[page_ref] = page
        self.page_append_count += 1
        return page

    def list_views(self, data_source_id: str) -> tuple[NotionView, ...]:
        self._request("list_views")
        if data_source_id not in {self.items_data_source_id, self.categories_data_source_id}:
            raise NotionTransportError(status=404, code="object_not_found")
        return tuple(
            sorted(
                (item for item in self.views.values() if item.data_source_id == data_source_id),
                key=lambda item: item.view_ref,
            )
        )

    def create_view(self, specification: NotionViewSpec) -> NotionView:
        self._request("create_view")
        expected_database_id = {
            self.items_data_source_id: self.items_database_id,
            self.categories_data_source_id: self.categories_database_id,
        }.get(specification.data_source_id)
        if expected_database_id is None:
            raise NotionTransportError(status=404, code="object_not_found")
        if specification.database_id != expected_database_id:
            raise NotionSchemaConflict("view database does not own the supplied data source")
        duplicate = sum(
            1
            for item in self.views.values()
            if item.data_source_id == specification.data_source_id and item.name == specification.name
        )
        view_ref = str(uuid.uuid5(_MOCK_NAMESPACE, f"view:{specification.data_source_id}:{specification.name}:{duplicate}"))
        view = NotionView(
            view_ref=view_ref,
            name=specification.name,
            database_id=specification.database_id,
            data_source_id=specification.data_source_id,
            view_type=specification.view_type,
            filter=json.loads(json.dumps(specification.filter, sort_keys=True)),
            sorts=tuple(json.loads(json.dumps(list(specification.sorts), sort_keys=True))),
            configuration=json.loads(json.dumps(specification.configuration, sort_keys=True)),
        )
        self.views[view_ref] = view
        self.view_create_count += 1
        return view


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

    def _ensure_schema(self) -> NotionSchemaMigration:
        categories = self.client.retrieve_schema("categories")
        items = self.client.retrieve_schema("items")
        migration = plan_schema_migration(
            categories,
            items,
            categories_data_source_id=self.client.categories_data_source_id,
        )
        if migration.category_additions:
            self.client.patch_schema("categories", migration.category_additions)
        if migration.item_additions:
            self.client.patch_schema("items", migration.item_additions)
        return migration

    def reconcile_views(self) -> NotionViewReconciliation:
        """Create only missing x2n-owned views; never overwrite an owner view.

        View installation is intentionally outside page delivery and Outbox.  A
        view is an optional navigation projection, so an unavailable view API
        returns a precise fallback rather than claiming a view was created or
        delaying Canonical/Markdown/Notion page reconciliation.
        """

        specifications = (
            *item_view_specs(
                database_id=self.client.items_database_id,
                data_source_id=self.client.items_data_source_id,
            ),
            *category_view_specs(
                database_id=self.client.categories_database_id,
                data_source_id=self.client.categories_data_source_id,
            ),
        )
        deliveries: list[NotionViewDelivery] = []
        try:
            self._ensure_schema()
            existing_by_data_source = {
                data_source_id: self.client.list_views(data_source_id)
                for data_source_id in dict.fromkeys(specification.data_source_id for specification in specifications)
            }
            for specification in specifications:
                existing = existing_by_data_source[specification.data_source_id]
                matches = [item for item in existing if item.name == specification.name]
                if len(matches) > 1:
                    raise NotionSchemaConflict("multiple views share one x2n-managed name")
                if not matches:
                    view = self.client.create_view(specification)
                    deliveries.append(
                        NotionViewDelivery(
                            key=specification.key,
                            state="created",
                            output_hash=view.output_hash(),
                            view_ref_hash=hashlib.sha256(view.view_ref.encode("utf-8")).hexdigest(),
                        )
                    )
                    existing_by_data_source[specification.data_source_id] = (*existing, view)
                    continue
                view = matches[0]
                if view.output_hash() != specification.output_hash():
                    raise NotionSchemaConflict("x2n-managed view differs from the declared safe definition")
                deliveries.append(
                    NotionViewDelivery(
                        key=specification.key,
                        state="unchanged",
                        output_hash=view.output_hash(),
                        view_ref_hash=hashlib.sha256(view.view_ref.encode("utf-8")).hexdigest(),
                    )
                )
            return NotionViewReconciliation("SUPPORTED", tuple(deliveries))
        except NotionTransportError as error:
            return NotionViewReconciliation(
                "FALLBACK_DOCUMENTED",
                tuple(deliveries),
                fallback_reason=self._error_code(error.code),
            )

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
            first_batch = notion_projection.child_batches[0] if notion_projection.child_batches else ()
            if page is None:
                page = self.client.create_page(notion_projection, first_batch)
                remote_write = "create"
            elif (
                page.projection_hash != notion_projection.desired_projection_hash
                or page.output_hash != notion_projection.output_hash()
            ):
                page = self.client.update_page(page.page_ref, notion_projection, first_batch)
                remote_write = "update"
            for child_batch in notion_projection.child_batches[1:]:
                page = self.client.append_page_children(page.page_ref, child_batch)
            if page.output_hash != notion_projection.output_hash():
                raise X2NRuntimeError(ErrorCode.DATA_INTEGRITY_FAILED, "Notion page body did not reconcile")
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
