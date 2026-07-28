"""Owner-governed taxonomy, suggestion-only classification and private evaluation.

This module intentionally separates the two capabilities that are easy to
confuse in a content product: an Owner may change the primary taxonomy, while
a classifier may only choose from an immutable snapshot supplied to it.  The
classifier has no Store dependency, no mutation methods, no model/network
route, and keeps source text in short-lived, non-serializable objects.

The initial route is deterministic lexical matching.  It is useful for
auditable suggestions and private calibration without pretending that a
synthetic score is a model-quality result.  Automatic acceptance remains
closed until a matching private Gold Set evaluation creates a valid gate.
"""

from __future__ import annotations

import hashlib
import json
import math
import re
import stat
import unicodedata
from collections.abc import Iterator, Sequence
from contextlib import contextmanager
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Literal, Protocol
from uuid import UUID

from x2n_contracts import Classification, ErrorCode, TaxonomyCategory
from x2n_contracts.models import ClassificationCandidate, DecisionMode, ReviewStatus

from .runtime import RuntimePaths, X2NRuntimeError


TASK_ID = "TSK.x2n.multimodal.005"
CLASSIFICATION_POLICY_VERSION = "x2n-classification-v1"
CLASSIFIER_RULESET_VERSION = "x2n-taxonomy-lexical-v1"
CLASSIFICATION_GOLD_DATASET_SCHEMA = "x2n-classification-gold-v1"
DEFAULT_CLASSIFIER_SNAPSHOT_SHA256 = hashlib.sha256(b"x2n-deterministic-taxonomy-classifier-v1").hexdigest()
RULESET_SHA256 = hashlib.sha256(CLASSIFIER_RULESET_VERSION.encode("utf-8")).hexdigest()

MAX_CATEGORIES = 200
MAX_CLASSIFICATION_SOURCES = 16
MAX_SOURCE_CHARS = 20_000
MAX_TOTAL_SOURCE_CHARS = 40_000
MAX_CACHE_ENTRIES = 128
MAX_GOLD_DATASET_BYTES = 2 * 1024 * 1024
MAX_GOLD_CASES = 500
MIN_SMOKE_CASES = 40
MIN_PRIVATE_GOLD_CASES = 100
MIN_CASES_PER_ENABLED_CATEGORY = 5
MIN_HIGH_CONFIDENCE_CASES = 20
AUTO_ACCEPT_THRESHOLD = 0.90
MIN_HIGH_CONFIDENCE_PRECISION = 0.90
MACRO_F1_REFERENCE = 0.80

_SAFE_TOKEN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")
_OPAQUE_REF = re.compile(r"^[a-z][a-z0-9_]{1,31}_[A-Za-z0-9][A-Za-z0-9._-]{0,191}$")
_SHA256 = re.compile(r"^[0-9a-f]{64}$")
_RFC3339_Z = re.compile(
    r"^[0-9]{4}-(?:0[1-9]|1[0-2])-(?:0[1-9]|[12][0-9]|3[01])"
    r"T(?:[01][0-9]|2[0-3]):[0-5][0-9]:[0-5][0-9](?:\.[0-9]{1,6})?Z$"
)
_RESERVED_SLUGS = frozenset({"unclassified"})


def _fail(code: ErrorCode, message: str) -> None:
    raise X2NRuntimeError(code, message)


def _sha256(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _canonical_sha256(value: object) -> str:
    rendered = json.dumps(value, ensure_ascii=False, allow_nan=False, separators=(",", ":"), sort_keys=True)
    return _sha256(rendered)


def _safe_token(value: object, *, label: str) -> str:
    if not isinstance(value, str) or _SAFE_TOKEN.fullmatch(value) is None:
        _fail(ErrorCode.INVALID_INPUT, f"Taxonomy {label} is invalid")
    return value


def _opaque_ref(value: object, *, label: str) -> str:
    if not isinstance(value, str) or _OPAQUE_REF.fullmatch(value) is None:
        _fail(ErrorCode.INVALID_INPUT, f"Taxonomy {label} is invalid")
    return value


def _hash(value: object, *, label: str) -> str:
    if not isinstance(value, str) or _SHA256.fullmatch(value) is None:
        _fail(ErrorCode.DATA_INTEGRITY_FAILED, f"Taxonomy {label} is invalid")
    return value


def _bounded_text(value: object, *, label: str, maximum: int, allow_empty: bool = False) -> str:
    if not isinstance(value, str) or (not allow_empty and not value.strip()) or len(value) > maximum:
        _fail(ErrorCode.INVALID_INPUT, f"Taxonomy {label} is invalid")
    for character in value:
        if unicodedata.category(character) == "Cc" and character not in {"\n", "\r", "\t"}:
            _fail(ErrorCode.POLICY_BLOCKED, "Taxonomy source contains a control character")
    return value


def _normalize_term(value: str) -> str:
    normalized = unicodedata.normalize("NFKC", value).casefold().strip()
    return " ".join(normalized.split())


def _private_directory(path: Path) -> None:
    if path.is_symlink() or not path.is_dir():
        _fail(ErrorCode.POLICY_BLOCKED, "Classification private workspace is unavailable")
    try:
        if stat.S_IMODE(path.stat().st_mode) != 0o700:
            _fail(ErrorCode.POLICY_BLOCKED, "Classification private workspace is not owner-only")
    except OSError:
        raise X2NRuntimeError(ErrorCode.STORAGE_FAILED, "Classification private workspace is unavailable") from None


def _private_child(root: Path, name: str) -> Path:
    candidate = root / name
    if type(name) is not str or "/" in name or "\\" in name or ".." in Path(name).parts:
        _fail(ErrorCode.POLICY_BLOCKED, "Classification private child name is invalid")
    try:
        candidate.resolve(strict=False).relative_to(root.resolve(strict=True))
    except ValueError:
        _fail(ErrorCode.POLICY_BLOCKED, "Classification private child escaped its workspace")
    except OSError:
        raise X2NRuntimeError(ErrorCode.STORAGE_FAILED, "Classification private workspace is unavailable") from None
    return candidate


def _private_regular_file(path: Path, *, maximum_bytes: int) -> int:
    if path.is_symlink() or not path.is_file() or path.suffix != ".json":
        _fail(ErrorCode.DATA_INTEGRITY_FAILED, "Classification private Gold Set is unavailable")
    try:
        metadata = path.stat()
    except OSError:
        raise X2NRuntimeError(ErrorCode.STORAGE_FAILED, "Classification private Gold Set is unavailable") from None
    if not stat.S_ISREG(metadata.st_mode) or stat.S_IMODE(metadata.st_mode) != 0o600:
        _fail(ErrorCode.POLICY_BLOCKED, "Classification private Gold Set is not owner-only")
    if not 0 < metadata.st_size <= maximum_bytes:
        _fail(ErrorCode.POLICY_BLOCKED, "Classification private Gold Set exceeds its resource policy")
    return int(metadata.st_size)


def _sha256_file(path: Path, *, maximum_bytes: int) -> tuple[str, int]:
    _private_regular_file(path, maximum_bytes=maximum_bytes)
    digest = hashlib.sha256()
    size = 0
    try:
        with path.open("rb") as handle:
            while chunk := handle.read(1024 * 1024):
                size += len(chunk)
                if size > maximum_bytes:
                    _fail(ErrorCode.POLICY_BLOCKED, "Classification private Gold Set exceeds its resource policy")
                digest.update(chunk)
    except X2NRuntimeError:
        raise
    except OSError:
        raise X2NRuntimeError(ErrorCode.STORAGE_FAILED, "Classification private Gold Set is unavailable") from None
    if size <= 0:
        _fail(ErrorCode.DATA_INTEGRITY_FAILED, "Classification private Gold Set is empty")
    return digest.hexdigest(), size


@dataclass(frozen=True)
class TaxonomyRevision:
    """Append-only Owner operation persisted beside the current category row."""

    revision_id: str
    category_id: UUID
    operation: Literal["create", "update", "disable", "merge"]
    actor: Literal["owner"]
    category_version: int
    previous_version: int | None
    merge_target_category_id: UUID | None
    payload_sha256: str
    created_at: str

    def __post_init__(self) -> None:
        _opaque_ref(self.revision_id, label="revision id")
        if self.operation not in {"create", "update", "disable", "merge"} or self.actor != "owner":
            _fail(ErrorCode.POLICY_BLOCKED, "Taxonomy revision actor or operation is invalid")
        if isinstance(self.category_version, bool) or not isinstance(self.category_version, int) or self.category_version < 1:
            _fail(ErrorCode.DATA_INTEGRITY_FAILED, "Taxonomy revision version is invalid")
        if self.previous_version is not None and (
            isinstance(self.previous_version, bool)
            or not isinstance(self.previous_version, int)
            or not 1 <= self.previous_version < self.category_version
        ):
            _fail(ErrorCode.DATA_INTEGRITY_FAILED, "Taxonomy revision prior version is invalid")
        if self.operation == "create" and (self.previous_version is not None or self.merge_target_category_id is not None):
            _fail(ErrorCode.DATA_INTEGRITY_FAILED, "Taxonomy create revision is invalid")
        if self.operation in {"update", "disable"} and (
            self.previous_version is None or self.merge_target_category_id is not None
        ):
            _fail(ErrorCode.DATA_INTEGRITY_FAILED, "Taxonomy revision is invalid")
        if self.operation == "merge" and (
            self.previous_version is None
            or self.merge_target_category_id is None
            or self.merge_target_category_id == self.category_id
        ):
            _fail(ErrorCode.DATA_INTEGRITY_FAILED, "Taxonomy merge revision is invalid")
        _hash(self.payload_sha256, label="revision payload hash")
        if _RFC3339_Z.fullmatch(self.created_at) is None:
            _fail(ErrorCode.DATA_INTEGRITY_FAILED, "Taxonomy revision timestamp is invalid")

    def safe_dict(self) -> dict[str, int | str | None]:
        return {
            "actor": self.actor,
            "category_id": str(self.category_id),
            "category_version": self.category_version,
            "created_at": self.created_at,
            "merge_target_category_id": None if self.merge_target_category_id is None else str(self.merge_target_category_id),
            "operation": self.operation,
            "payload_sha256": self.payload_sha256,
            "previous_version": self.previous_version,
            "revision_id": self.revision_id,
        }


@dataclass(frozen=True)
class TaxonomySnapshot:
    """A deterministic, immutable registry view consumed by the classifier."""

    categories: tuple[TaxonomyCategory, ...]
    version: int
    snapshot_sha256: str = field(init=False)

    def __post_init__(self) -> None:
        if not isinstance(self.categories, tuple) or len(self.categories) > MAX_CATEGORIES:
            _fail(ErrorCode.POLICY_BLOCKED, "Taxonomy category count is invalid")
        if not all(isinstance(category, TaxonomyCategory) for category in self.categories):
            _fail(ErrorCode.INVALID_INPUT, "Taxonomy snapshot category is invalid")
        identifiers = [str(category.category_id) for category in self.categories]
        if identifiers != sorted(identifiers) or len(set(identifiers)) != len(identifiers):
            _fail(ErrorCode.DATA_INTEGRITY_FAILED, "Taxonomy snapshot ordering is invalid")
        if isinstance(self.version, bool) or not isinstance(self.version, int) or self.version < 0:
            _fail(ErrorCode.DATA_INTEGRITY_FAILED, "Taxonomy snapshot version is invalid")
        if self.categories and self.version != sum(category.version for category in self.categories):
            _fail(ErrorCode.DATA_INTEGRITY_FAILED, "Taxonomy snapshot version diverged")
        terms: dict[str, UUID] = {}
        for category in self.categories:
            if not category.enabled:
                continue
            for term in (category.name, *category.aliases):
                normalized = _normalize_term(term)
                if not normalized:
                    _fail(ErrorCode.DATA_INTEGRITY_FAILED, "Taxonomy term is invalid")
                prior = terms.setdefault(normalized, category.category_id)
                if prior != category.category_id:
                    _fail(ErrorCode.DATA_INTEGRITY_FAILED, "Enabled taxonomy aliases are ambiguous")
        payload = [category.model_dump(mode="json") for category in self.categories]
        object.__setattr__(self, "snapshot_sha256", _canonical_sha256(payload))

    @classmethod
    def from_categories(cls, categories: Sequence[TaxonomyCategory]) -> "TaxonomySnapshot":
        ordered = tuple(sorted(categories, key=lambda category: str(category.category_id)))
        # Categories are never deleted and every Owner mutation increments the
        # corresponding category version.  Their version sum therefore serves
        # as a simple global monotonic registry revision without a mutable
        # counter that a classifier could accidentally own.
        return cls(ordered, sum(category.version for category in ordered))

    @property
    def enabled_categories(self) -> tuple[TaxonomyCategory, ...]:
        return tuple(category for category in self.categories if category.enabled)

    def category(self, category_id: UUID) -> TaxonomyCategory | None:
        return next((category for category in self.categories if category.category_id == category_id), None)

    def require_enabled(self, category_id: UUID) -> TaxonomyCategory:
        category = self.category(category_id)
        if category is None:
            _fail(ErrorCode.DATA_INTEGRITY_FAILED, "Taxonomy category is unknown")
        if not category.enabled:
            _fail(ErrorCode.POLICY_BLOCKED, "Taxonomy category is disabled")
        return category

    def safe_dict(self) -> dict[str, int | str]:
        return {
            "category_count": len(self.categories),
            "enabled_category_count": len(self.enabled_categories),
            "snapshot_sha256": self.snapshot_sha256,
            "version": self.version,
        }


class TaxonomyStore(Protocol):
    def put_taxonomy_category(self, category: TaxonomyCategory) -> Any: ...

    def merge_taxonomy_category(self, source: TaxonomyCategory, target_category_id: UUID) -> Any: ...

    def list_taxonomy_categories(self, *, include_disabled: bool = True) -> tuple[TaxonomyCategory, ...]: ...


class TaxonomyRegistry:
    """The sole Owner-facing category mutation boundary for this task."""

    def __init__(self, store: TaxonomyStore) -> None:
        self._store = store

    def snapshot(self) -> TaxonomySnapshot:
        return TaxonomySnapshot.from_categories(self._store.list_taxonomy_categories())

    @staticmethod
    def _validate_category(category: TaxonomyCategory) -> None:
        if category.created_by != "owner" or category.level != 1:
            _fail(ErrorCode.POLICY_BLOCKED, "Only Owner top-level taxonomy categories are permitted")
        if category.slug in _RESERVED_SLUGS:
            _fail(ErrorCode.POLICY_BLOCKED, "Reserved fallback category cannot enter the Owner registry")

    def _validate_terms(self, category: TaxonomyCategory, *, replacing: UUID | None) -> None:
        self._validate_category(category)
        existing = self.snapshot()
        proposed = TaxonomySnapshot.from_categories(
            tuple(item for item in existing.categories if item.category_id != replacing) + (category,)
        )
        del proposed

    def create(self, category: TaxonomyCategory) -> Any:
        existing = self.snapshot()
        if existing.category(category.category_id) is not None:
            _fail(ErrorCode.DATA_INTEGRITY_FAILED, "Taxonomy category already exists")
        if category.version != 1:
            _fail(ErrorCode.DATA_INTEGRITY_FAILED, "New taxonomy category must start at version one")
        self._validate_terms(category, replacing=None)
        return self._store.put_taxonomy_category(category)

    def update(self, category: TaxonomyCategory) -> Any:
        existing = self.snapshot().category(category.category_id)
        if existing is None or category.version <= existing.version:
            _fail(ErrorCode.DATA_INTEGRITY_FAILED, "Taxonomy update version conflicts with Owner truth")
        self._validate_terms(category, replacing=category.category_id)
        return self._store.put_taxonomy_category(category)

    def disable(self, category: TaxonomyCategory) -> Any:
        existing = self.snapshot().category(category.category_id)
        if existing is None or not existing.enabled or category.enabled or category.version <= existing.version:
            _fail(ErrorCode.DATA_INTEGRITY_FAILED, "Taxonomy disable revision is invalid")
        self._validate_terms(category, replacing=category.category_id)
        return self._store.put_taxonomy_category(category)

    def merge(self, source: TaxonomyCategory, *, target_category_id: UUID) -> Any:
        existing = self.snapshot()
        original = existing.category(source.category_id)
        target = existing.require_enabled(target_category_id)
        if (
            original is None
            or original.enabled
            or source.enabled
            or source.version <= original.version
            or source.category_id == target.category_id
        ):
            _fail(ErrorCode.DATA_INTEGRITY_FAILED, "Taxonomy merge revision is invalid")
        self._validate_terms(source, replacing=source.category_id)
        return self._store.merge_taxonomy_category(source, target.category_id)


@dataclass(frozen=True)
class ClassificationPolicy:
    """Non-relaxable zero-side-effect budget and automatic-routing threshold."""

    version: str = CLASSIFICATION_POLICY_VERSION
    max_sources: int = MAX_CLASSIFICATION_SOURCES
    max_source_chars: int = MAX_SOURCE_CHARS
    max_total_source_chars: int = MAX_TOTAL_SOURCE_CHARS
    max_cache_entries: int = MAX_CACHE_ENTRIES
    auto_accept_threshold: float = AUTO_ACCEPT_THRESHOLD
    max_model_calls: int = 0
    max_network_calls: int = 0
    max_file_reads: int = 0
    max_config_writes: int = 0
    max_cloud_cost_microunits: int = 0

    def __post_init__(self) -> None:
        if self.version != CLASSIFICATION_POLICY_VERSION:
            _fail(ErrorCode.INVALID_INPUT, "Classification policy version is unsupported")
        limits = (
            ("max_sources", self.max_sources, MAX_CLASSIFICATION_SOURCES),
            ("max_source_chars", self.max_source_chars, MAX_SOURCE_CHARS),
            ("max_total_source_chars", self.max_total_source_chars, MAX_TOTAL_SOURCE_CHARS),
            ("max_cache_entries", self.max_cache_entries, MAX_CACHE_ENTRIES),
        )
        for label, value, maximum in limits:
            if isinstance(value, bool) or not isinstance(value, int) or not 0 < value <= maximum:
                _fail(ErrorCode.POLICY_BLOCKED, f"Classification {label} exceeds its approved budget")
        if self.max_total_source_chars < self.max_source_chars:
            _fail(ErrorCode.POLICY_BLOCKED, "Classification aggregate source policy is invalid")
        if not isinstance(self.auto_accept_threshold, (float, int)) or isinstance(self.auto_accept_threshold, bool):
            _fail(ErrorCode.INVALID_INPUT, "Classification threshold is invalid")
        if not AUTO_ACCEPT_THRESHOLD <= float(self.auto_accept_threshold) <= 1.0:
            _fail(ErrorCode.POLICY_BLOCKED, "Classification threshold cannot be relaxed")
        for label in (
            "max_model_calls",
            "max_network_calls",
            "max_file_reads",
            "max_config_writes",
            "max_cloud_cost_microunits",
        ):
            if getattr(self, label) != 0:
                _fail(ErrorCode.POLICY_BLOCKED, "Classification side-effect budget must remain zero")

    def safe_dict(self) -> dict[str, float | int | str]:
        return {
            "auto_accept_threshold": float(self.auto_accept_threshold),
            "max_cache_entries": self.max_cache_entries,
            "max_cloud_cost_microunits": self.max_cloud_cost_microunits,
            "max_config_writes": self.max_config_writes,
            "max_file_reads": self.max_file_reads,
            "max_model_calls": self.max_model_calls,
            "max_network_calls": self.max_network_calls,
            "max_source_chars": self.max_source_chars,
            "max_sources": self.max_sources,
            "max_total_source_chars": self.max_total_source_chars,
            "version": self.version,
        }


@dataclass(frozen=True)
class ClassifierDescriptor:
    """Versioned local lexical rule provenance, never an executable model route."""

    provider_id: str = "local-constrained-classifier"
    provider_version: str = "1"
    model_id: str = "deterministic-lexical-rules"
    model_snapshot_sha256: str = DEFAULT_CLASSIFIER_SNAPSHOT_SHA256
    ruleset_sha256: str = RULESET_SHA256
    execution_mode: Literal["deterministic_local"] = "deterministic_local"
    cloud_upload_authorized: bool = False
    retention: Literal["local_ephemeral"] = "local_ephemeral"
    tools_available: bool = False

    def __post_init__(self) -> None:
        _safe_token(self.provider_id, label="provider id")
        _safe_token(self.provider_version, label="provider version")
        _safe_token(self.model_id, label="model id")
        _hash(self.model_snapshot_sha256, label="model snapshot")
        _hash(self.ruleset_sha256, label="ruleset")
        if (
            self.execution_mode != "deterministic_local"
            or self.cloud_upload_authorized
            or self.retention != "local_ephemeral"
            or self.tools_available
        ):
            _fail(ErrorCode.POLICY_BLOCKED, "Classifier descriptor is not local and no-action")

    def safe_dict(self) -> dict[str, bool | str]:
        return {
            "cloud_upload_authorized": self.cloud_upload_authorized,
            "execution_mode": self.execution_mode,
            "model_id": self.model_id,
            "model_snapshot_sha256": self.model_snapshot_sha256,
            "provider_id": self.provider_id,
            "provider_version": self.provider_version,
            "retention": self.retention,
            "ruleset_sha256": self.ruleset_sha256,
            "tools_available": self.tools_available,
        }

    @property
    def fingerprint(self) -> str:
        return _canonical_sha256(self.safe_dict())


@dataclass(frozen=True)
class ClassificationSource:
    """Untrusted in-memory artifact text that cannot be serialized or persisted."""

    artifact_id: str
    content: str = field(repr=False, compare=False)
    source_sha256: str | None = None

    def __post_init__(self) -> None:
        _opaque_ref(self.artifact_id, label="source artifact id")
        content = _bounded_text(self.content, label="source content", maximum=MAX_SOURCE_CHARS)
        digest = _sha256(content)
        if self.source_sha256 is not None and self.source_sha256 != digest:
            _fail(ErrorCode.DATA_INTEGRITY_FAILED, "Classification source provenance is invalid")
        object.__setattr__(self, "source_sha256", digest)

    def safe_dict(self) -> dict[str, bool | int | str]:
        return {
            "artifact_id": self.artifact_id,
            "content_characters": len(self.content),
            "content_emitted": False,
            "source_sha256": self.source_sha256 or "",
        }

    def __getstate__(self) -> None:
        raise TypeError("Classification sources cannot be serialized")

    def __reduce_ex__(self, protocol: int) -> None:
        del protocol
        raise TypeError("Classification sources cannot be serialized")


@dataclass(frozen=True)
class ClassificationRequest:
    content_key: str
    sources: tuple[ClassificationSource, ...] = field(repr=False, compare=False)

    def __post_init__(self) -> None:
        if not isinstance(self.content_key, str) or not 3 <= len(self.content_key) <= 768:
            _fail(ErrorCode.INVALID_INPUT, "Classification content key is invalid")
        if not isinstance(self.sources, tuple) or not self.sources or len(self.sources) > MAX_CLASSIFICATION_SOURCES:
            _fail(ErrorCode.POLICY_BLOCKED, "Classification source count is invalid")
        if not all(isinstance(source, ClassificationSource) for source in self.sources):
            _fail(ErrorCode.INVALID_INPUT, "Classification source type is invalid")
        identifiers = [source.artifact_id for source in self.sources]
        if len(set(identifiers)) != len(identifiers):
            _fail(ErrorCode.DATA_INTEGRITY_FAILED, "Classification source artifact ids are duplicated")
        if sum(len(source.content) for source in self.sources) > MAX_TOTAL_SOURCE_CHARS:
            _fail(ErrorCode.POLICY_BLOCKED, "Classification source content exceeds its resource policy")

    @property
    def ordered_sources(self) -> tuple[ClassificationSource, ...]:
        return tuple(sorted(self.sources, key=lambda source: source.artifact_id))

    @property
    def input_hash(self) -> str:
        return _canonical_sha256([source.safe_dict() for source in self.ordered_sources])

    @property
    def artifact_ids(self) -> tuple[str, ...]:
        return tuple(source.artifact_id for source in self.ordered_sources)

    def safe_dict(self) -> dict[str, object]:
        return {
            "content_key_sha256": _sha256(self.content_key),
            "input_hash": self.input_hash,
            "source_count": len(self.sources),
            "sources": [source.safe_dict() for source in self.ordered_sources],
        }

    def __getstate__(self) -> None:
        raise TypeError("Classification requests cannot be serialized")

    def __reduce_ex__(self, protocol: int) -> None:
        del protocol
        raise TypeError("Classification requests cannot be serialized")


@dataclass(frozen=True)
class CalibrationBucket:
    name: str
    lower_bound: float
    upper_bound: float
    sample_count: int
    correct_count: int

    def __post_init__(self) -> None:
        _safe_token(self.name, label="calibration bucket")
        values = (self.lower_bound, self.upper_bound)
        if not all(isinstance(value, (float, int)) and not isinstance(value, bool) and math.isfinite(float(value)) for value in values):
            _fail(ErrorCode.INVALID_INPUT, "Classification calibration bounds are invalid")
        if not 0 <= float(self.lower_bound) < float(self.upper_bound) <= 1:
            _fail(ErrorCode.DATA_INTEGRITY_FAILED, "Classification calibration bounds are invalid")
        if (
            isinstance(self.sample_count, bool)
            or isinstance(self.correct_count, bool)
            or not isinstance(self.sample_count, int)
            or not isinstance(self.correct_count, int)
            or not 0 <= self.correct_count <= self.sample_count
        ):
            _fail(ErrorCode.DATA_INTEGRITY_FAILED, "Classification calibration counts are invalid")

    @property
    def calibrated_score(self) -> float:
        return 0.0 if self.sample_count == 0 else self.correct_count / self.sample_count

    def safe_dict(self) -> dict[str, float | int | str]:
        return {
            "calibrated_score": self.calibrated_score,
            "correct_count": self.correct_count,
            "lower_bound": float(self.lower_bound),
            "name": self.name,
            "sample_count": self.sample_count,
            "upper_bound": float(self.upper_bound),
        }


@dataclass(frozen=True)
class CalibrationProfile:
    version: str
    taxonomy_snapshot_sha256: str
    dataset_sha256: str
    buckets: tuple[CalibrationBucket, ...]
    profile_sha256: str = field(init=False)

    def __post_init__(self) -> None:
        _safe_token(self.version, label="calibration version")
        _hash(self.taxonomy_snapshot_sha256, label="calibration taxonomy snapshot")
        _hash(self.dataset_sha256, label="calibration dataset")
        if not isinstance(self.buckets, tuple) or not self.buckets or not all(
            isinstance(bucket, CalibrationBucket) for bucket in self.buckets
        ):
            _fail(ErrorCode.DATA_INTEGRITY_FAILED, "Classification calibration buckets are invalid")
        if self.buckets[0].lower_bound != 0.0 or self.buckets[-1].upper_bound != 1.0:
            _fail(ErrorCode.DATA_INTEGRITY_FAILED, "Classification calibration coverage is incomplete")
        for prior, current in zip(self.buckets, self.buckets[1:]):
            if prior.upper_bound != current.lower_bound:
                _fail(ErrorCode.DATA_INTEGRITY_FAILED, "Classification calibration buckets are not contiguous")
        object.__setattr__(self, "profile_sha256", _canonical_sha256(self.safe_dict()))

    def bucket_for(self, score: float) -> CalibrationBucket:
        if not isinstance(score, (int, float)) or isinstance(score, bool) or not 0 <= float(score) <= 1:
            _fail(ErrorCode.INVALID_INPUT, "Classification score is invalid")
        for bucket in self.buckets:
            if bucket.lower_bound <= float(score) < bucket.upper_bound or (
                float(score) == 1.0 and bucket.upper_bound == 1.0
            ):
                return bucket
        _fail(ErrorCode.DATA_INTEGRITY_FAILED, "Classification score has no calibration bucket")

    def calibrate(self, score: float) -> tuple[str, float]:
        bucket = self.bucket_for(score)
        return bucket.name, bucket.calibrated_score

    def safe_dict(self) -> dict[str, object]:
        return {
            "buckets": [bucket.safe_dict() for bucket in self.buckets],
            "dataset_sha256": self.dataset_sha256,
            "taxonomy_snapshot_sha256": self.taxonomy_snapshot_sha256,
            "version": self.version,
        }


@dataclass(frozen=True)
class ClassificationSuggestion:
    suggestion_id: str
    content_key: str
    taxonomy_version: int
    taxonomy_snapshot_sha256: str
    classifier_fingerprint: str
    input_hash: str
    source_artifact_ids: tuple[str, ...]
    primary_category_id: UUID | None
    candidate_ranking: tuple[ClassificationCandidate, ...]
    confidence_raw: float | None
    calibrated_confidence: float | None
    calibration_bucket: str | None
    disposition: Literal["unclassified", "suggested", "auto_accepted"]

    def __post_init__(self) -> None:
        _opaque_ref(self.suggestion_id, label="suggestion id")
        if not isinstance(self.content_key, str) or not 3 <= len(self.content_key) <= 768:
            _fail(ErrorCode.INVALID_INPUT, "Classification suggestion content key is invalid")
        if isinstance(self.taxonomy_version, bool) or not isinstance(self.taxonomy_version, int) or self.taxonomy_version < 0:
            _fail(ErrorCode.DATA_INTEGRITY_FAILED, "Classification suggestion taxonomy version is invalid")
        for value, label in (
            (self.taxonomy_snapshot_sha256, "suggestion taxonomy snapshot"),
            (self.classifier_fingerprint, "suggestion classifier"),
            (self.input_hash, "suggestion input"),
        ):
            _hash(value, label=label)
        if not isinstance(self.source_artifact_ids, tuple) or not self.source_artifact_ids:
            _fail(ErrorCode.DATA_INTEGRITY_FAILED, "Classification suggestion evidence is invalid")
        if len(set(self.source_artifact_ids)) != len(self.source_artifact_ids):
            _fail(ErrorCode.DATA_INTEGRITY_FAILED, "Classification suggestion evidence is duplicated")
        for artifact_id in self.source_artifact_ids:
            _opaque_ref(artifact_id, label="suggestion artifact id")
        if not isinstance(self.candidate_ranking, tuple) or len(self.candidate_ranking) > 20:
            _fail(ErrorCode.DATA_INTEGRITY_FAILED, "Classification suggestion candidates are invalid")
        ids = [candidate.category_id for candidate in self.candidate_ranking]
        scores = [candidate.calibrated_score for candidate in self.candidate_ranking]
        if len(set(ids)) != len(ids) or scores != sorted(scores, reverse=True):
            _fail(ErrorCode.DATA_INTEGRITY_FAILED, "Classification suggestion ranking is invalid")
        values = (self.confidence_raw, self.calibrated_confidence)
        if any(value is not None and (not isinstance(value, (float, int)) or not 0 <= float(value) <= 1) for value in values):
            _fail(ErrorCode.DATA_INTEGRITY_FAILED, "Classification suggestion confidence is invalid")
        if self.calibration_bucket is not None:
            _safe_token(self.calibration_bucket, label="suggestion calibration bucket")
        if self.disposition == "unclassified":
            if self.primary_category_id is not None or self.candidate_ranking or any(value is not None for value in values):
                _fail(ErrorCode.DATA_INTEGRITY_FAILED, "Unclassified suggestion is invalid")
        elif self.disposition in {"suggested", "auto_accepted"}:
            if (
                self.primary_category_id is None
                or self.taxonomy_version < 1
                or not self.candidate_ranking
                or self.primary_category_id != self.candidate_ranking[0].category_id
                or any(value is None for value in values)
            ):
                _fail(ErrorCode.DATA_INTEGRITY_FAILED, "Classification suggestion is invalid")
        else:  # pragma: no cover - Literal protection at type-check time.
            _fail(ErrorCode.INVALID_INPUT, "Classification suggestion disposition is invalid")

    @property
    def safe_confidence(self) -> float | None:
        return None if self.calibrated_confidence is None else float(self.calibrated_confidence)

    def safe_dict(self) -> dict[str, object]:
        return {
            "calibrated_confidence": self.safe_confidence,
            "calibration_bucket": self.calibration_bucket,
            "candidate_ranking": [candidate.model_dump(mode="json") for candidate in self.candidate_ranking],
            "classifier_fingerprint": self.classifier_fingerprint,
            "content_key_sha256": _sha256(self.content_key),
            "confidence_raw": self.confidence_raw,
            "disposition": self.disposition,
            "input_hash": self.input_hash,
            "primary_category_id": None if self.primary_category_id is None else str(self.primary_category_id),
            "source_artifact_ids": list(self.source_artifact_ids),
            "suggestion_id": self.suggestion_id,
            "taxonomy_snapshot_sha256": self.taxonomy_snapshot_sha256,
            "taxonomy_version": self.taxonomy_version,
        }

    def to_classification(
        self,
        *,
        created_at: str,
        review_status: ReviewStatus,
        tags: tuple[str, ...] = (),
        supersedes_classification_id: str | None = None,
        primary_category_id: UUID | None = None,
        decision_mode: DecisionMode = DecisionMode.RULE,
    ) -> Classification:
        category_id = self.primary_category_id if primary_category_id is None else primary_category_id
        if category_id is None or self.disposition == "unclassified":
            _fail(ErrorCode.POLICY_BLOCKED, "Unclassified suggestion cannot be committed as a category")
        candidates = list(self.candidate_ranking)
        if category_id not in {candidate.category_id for candidate in candidates}:
            candidates.append(ClassificationCandidate(category_id=category_id, calibrated_score=1.0))
        candidates.sort(key=lambda candidate: (-candidate.calibrated_score, str(candidate.category_id)))
        seed = "|".join(
            (
                self.suggestion_id,
                str(category_id),
                review_status.value,
                supersedes_classification_id or "",
                decision_mode.value,
            )
        )
        return Classification(
            schema_version="1.0",
            classification_id=f"class_{_sha256(seed)[:32]}",
            content_key=self.content_key,
            taxonomy_version=max(1, self.taxonomy_version),
            primary_category_id=category_id,
            tags=tags,
            candidate_ranking=tuple(candidates[:20]),
            decision_mode=decision_mode,
            confidence_raw=self.confidence_raw,
            calibration_bucket=self.calibration_bucket,
            evidence_artifact_ids=self.source_artifact_ids,
            explanation_private_ref=None,
            review_status=review_status,
            created_at=created_at,
            supersedes_classification_id=supersedes_classification_id,
        )


@dataclass(frozen=True)
class AutoClassificationGate:
    """A private-evaluation receipt is required before auto acceptance can exist."""

    enabled: bool = False
    evaluation_sha256: str | None = None
    taxonomy_snapshot_sha256: str | None = None

    def __post_init__(self) -> None:
        if self.enabled:
            if self.evaluation_sha256 is None or self.taxonomy_snapshot_sha256 is None:
                _fail(ErrorCode.POLICY_BLOCKED, "Automatic classification lacks a private evaluation receipt")
            _hash(self.evaluation_sha256, label="automatic classification evaluation")
            _hash(self.taxonomy_snapshot_sha256, label="automatic classification taxonomy snapshot")
        elif self.evaluation_sha256 is not None or self.taxonomy_snapshot_sha256 is not None:
            _fail(ErrorCode.DATA_INTEGRITY_FAILED, "Disabled automatic classification gate is invalid")

    def permits(self, snapshot: TaxonomySnapshot) -> bool:
        return self.enabled and self.taxonomy_snapshot_sha256 == snapshot.snapshot_sha256

    @classmethod
    def from_evaluation(cls, report: "ClassificationEvaluationReport") -> "AutoClassificationGate":
        if report.scope != "private_gold" or report.status != "pass" or not report.auto_classify_allowed:
            return cls()
        return cls(True, report.evaluation_sha256, report.taxonomy_snapshot_sha256)

    def safe_dict(self) -> dict[str, bool | str | None]:
        return {
            "enabled": self.enabled,
            "evaluation_sha256": self.evaluation_sha256,
            "taxonomy_snapshot_sha256": self.taxonomy_snapshot_sha256,
        }


def _category_terms(category: TaxonomyCategory) -> tuple[tuple[str, float], tuple[tuple[str, float], ...]]:
    positive: dict[str, float] = {}
    for value, weight in ((category.name, 1.0), *((alias, 0.95) for alias in category.aliases), *((example, 0.80) for example in category.positive_examples)):
        normalized = _normalize_term(value)
        if len(normalized) >= 2:
            positive[normalized] = max(weight, positive.get(normalized, 0.0))
    negative: dict[str, float] = {}
    for value in category.negative_examples:
        normalized = _normalize_term(value)
        if len(normalized) >= 2:
            negative[normalized] = 0.95
    return tuple(positive.items()), tuple(negative.items())


def _raw_score(category: TaxonomyCategory, source_text: str) -> float:
    positives, negatives = _category_terms(category)
    if not positives:
        return 0.0
    matched = [weight for term, weight in positives if term in source_text]
    if not matched:
        return 0.0
    coverage = len(matched) / len(positives)
    score = max(matched) * (0.85 + 0.15 * coverage)
    negative = max((weight for term, weight in negatives if term in source_text), default=0.0)
    return max(0.0, min(1.0, score * (1.0 - negative)))


class ClassificationSession:
    """A bounded session-local cache with no handle to a taxonomy writer or Store."""

    def __init__(self, descriptor: ClassifierDescriptor, policy: ClassificationPolicy) -> None:
        self._descriptor = descriptor
        self._policy = policy
        self._cache: dict[tuple[str, str, str, str, str], ClassificationSuggestion] = {}
        self._cache_hits = 0
        self._cache_misses = 0

    def suggest(
        self,
        request: ClassificationRequest,
        snapshot: TaxonomySnapshot,
        *,
        calibration: CalibrationProfile | None = None,
        gate: AutoClassificationGate = AutoClassificationGate(),
    ) -> ClassificationSuggestion:
        if calibration is not None and calibration.taxonomy_snapshot_sha256 != snapshot.snapshot_sha256:
            _fail(ErrorCode.DATA_INTEGRITY_FAILED, "Classification calibration does not match the taxonomy snapshot")
        calibration_hash = "uncalibrated" if calibration is None else calibration.profile_sha256
        gate_hash = "suggestion_only" if not gate.enabled else gate.evaluation_sha256 or "invalid"
        cache_key = (self._descriptor.fingerprint, snapshot.snapshot_sha256, calibration_hash, gate_hash, request.input_hash)
        cached = self._cache.get(cache_key)
        if cached is not None:
            self._cache_hits += 1
            return cached
        enabled = snapshot.enabled_categories
        if not enabled:
            suggestion = ClassificationSuggestion(
                suggestion_id=f"suggestion_{_sha256('|'.join(cache_key))[:32]}",
                content_key=request.content_key,
                taxonomy_version=snapshot.version,
                taxonomy_snapshot_sha256=snapshot.snapshot_sha256,
                classifier_fingerprint=self._descriptor.fingerprint,
                input_hash=request.input_hash,
                source_artifact_ids=request.artifact_ids,
                primary_category_id=None,
                candidate_ranking=(),
                confidence_raw=None,
                calibrated_confidence=None,
                calibration_bucket=None,
                disposition="unclassified",
            )
        else:
            source_text = _normalize_term("\n".join(source.content for source in request.ordered_sources))
            scored: list[tuple[float, float, int, str, UUID, str]] = []
            for category in enabled:
                raw = _raw_score(category, source_text)
                if raw <= 0.0:
                    continue
                bucket, calibrated = ("uncalibrated", raw) if calibration is None else calibration.calibrate(raw)
                scored.append((calibrated, raw, category.priority, str(category.category_id), category.category_id, bucket))
            scored.sort(key=lambda item: (-item[0], -item[1], -item[2], item[3]))
            if not scored:
                suggestion = ClassificationSuggestion(
                    suggestion_id=f"suggestion_{_sha256('|'.join(cache_key))[:32]}",
                    content_key=request.content_key,
                    taxonomy_version=snapshot.version,
                    taxonomy_snapshot_sha256=snapshot.snapshot_sha256,
                    classifier_fingerprint=self._descriptor.fingerprint,
                    input_hash=request.input_hash,
                    source_artifact_ids=request.artifact_ids,
                    primary_category_id=None,
                    candidate_ranking=(),
                    confidence_raw=None,
                    calibrated_confidence=None,
                    calibration_bucket=None,
                    disposition="unclassified",
                )
            else:
                candidates = tuple(
                    ClassificationCandidate(category_id=item[4], calibrated_score=item[0]) for item in scored[:20]
                )
                best = scored[0]
                automatic = gate.permits(snapshot) and best[0] >= self._policy.auto_accept_threshold
                disposition: Literal["suggested", "auto_accepted"] = "auto_accepted" if automatic else "suggested"
                suggestion = ClassificationSuggestion(
                    suggestion_id=f"suggestion_{_sha256('|'.join((*cache_key, disposition)))[:32]}",
                    content_key=request.content_key,
                    taxonomy_version=snapshot.version,
                    taxonomy_snapshot_sha256=snapshot.snapshot_sha256,
                    classifier_fingerprint=self._descriptor.fingerprint,
                    input_hash=request.input_hash,
                    source_artifact_ids=request.artifact_ids,
                    primary_category_id=best[4],
                    candidate_ranking=candidates,
                    confidence_raw=best[1],
                    calibrated_confidence=best[0],
                    calibration_bucket=best[5],
                    disposition=disposition,
                )
        if len(self._cache) >= self._policy.max_cache_entries:
            _fail(ErrorCode.POLICY_BLOCKED, "Classification session cache budget is exhausted")
        self._cache[cache_key] = suggestion
        self._cache_misses += 1
        return suggestion

    def safe_ledger(self) -> dict[str, int]:
        return {
            "cache_entries": len(self._cache),
            "cache_hits": self._cache_hits,
            "cache_misses": self._cache_misses,
            "cloud_uploads": 0,
            "file_reads": 0,
            "model_calls": 0,
            "network_calls": 0,
        }

    def close(self) -> None:
        self._cache.clear()
        self._cache_hits = 0
        self._cache_misses = 0


class ConstrainedClassifier:
    """Deterministic, local-only selector over an immutable taxonomy snapshot."""

    def __init__(
        self,
        *,
        descriptor: ClassifierDescriptor = ClassifierDescriptor(),
        policy: ClassificationPolicy = ClassificationPolicy(),
    ) -> None:
        self.descriptor = descriptor
        self.policy = policy

    @contextmanager
    def session(self) -> Iterator[ClassificationSession]:
        session = ClassificationSession(self.descriptor, self.policy)
        try:
            yield session
        finally:
            session.close()


@dataclass(frozen=True)
class ClassificationGoldCase:
    case_id: str
    content_key: str
    evidence_artifact_id: str
    input_text: str = field(repr=False, compare=False)
    expected_category_id: UUID
    synthetic: bool

    def __post_init__(self) -> None:
        _safe_token(self.case_id, label="Gold Set case id")
        if not isinstance(self.content_key, str) or not 3 <= len(self.content_key) <= 768:
            _fail(ErrorCode.INVALID_INPUT, "Classification Gold Set content key is invalid")
        _opaque_ref(self.evidence_artifact_id, label="Gold Set evidence artifact id")
        _bounded_text(self.input_text, label="Gold Set input", maximum=MAX_TOTAL_SOURCE_CHARS)
        if not isinstance(self.synthetic, bool):
            _fail(ErrorCode.INVALID_INPUT, "Classification Gold Set synthetic marker is invalid")

    @property
    def input_hash(self) -> str:
        return _sha256(self.input_text)

    def safe_dict(self) -> dict[str, bool | str]:
        return {
            "case_id": self.case_id,
            "content_key_sha256": _sha256(self.content_key),
            "evidence_artifact_id": self.evidence_artifact_id,
            "expected_category_id": str(self.expected_category_id),
            "input_hash": self.input_hash,
            "synthetic": self.synthetic,
        }


@dataclass(frozen=True)
class PrivateClassificationGoldDataset:
    dataset_id: str
    sha256: str
    taxonomy_snapshot_sha256: str
    classifier_fingerprint: str
    cases: tuple[ClassificationGoldCase, ...] = field(repr=False, compare=False)

    def __post_init__(self) -> None:
        _safe_token(self.dataset_id, label="Gold Set dataset id")
        _hash(self.sha256, label="Gold Set dataset hash")
        _hash(self.taxonomy_snapshot_sha256, label="Gold Set taxonomy snapshot")
        _hash(self.classifier_fingerprint, label="Gold Set classifier fingerprint")
        if not self.cases or len(self.cases) > MAX_GOLD_CASES:
            _fail(ErrorCode.DATA_INTEGRITY_FAILED, "Classification private Gold Set is invalid")

    def safe_dict(self) -> dict[str, int | str]:
        return {
            "case_count": len(self.cases),
            "classifier_fingerprint": self.classifier_fingerprint,
            "dataset_id": self.dataset_id,
            "dataset_sha256": self.sha256,
            "taxonomy_snapshot_sha256": self.taxonomy_snapshot_sha256,
        }


def _gold_case_from_private_payload(value: object) -> ClassificationGoldCase:
    if not isinstance(value, dict):
        _fail(ErrorCode.DATA_INTEGRITY_FAILED, "Classification private Gold Set case is invalid")
    expected = {"case_id", "content_key", "evidence_artifact_id", "expected_category_id", "input_text"}
    if set(value) != expected:
        _fail(ErrorCode.DATA_INTEGRITY_FAILED, "Classification private Gold Set case shape is invalid")
    try:
        return ClassificationGoldCase(
            case_id=value["case_id"],
            content_key=value["content_key"],
            evidence_artifact_id=value["evidence_artifact_id"],
            input_text=value["input_text"],
            expected_category_id=UUID(str(value["expected_category_id"])),
            synthetic=False,
        )
    except (TypeError, ValueError, X2NRuntimeError):
        raise X2NRuntimeError(ErrorCode.DATA_INTEGRITY_FAILED, "Classification private Gold Set case is invalid") from None


def load_private_classification_gold_dataset(
    paths: RuntimePaths,
    dataset_id: str,
) -> PrivateClassificationGoldDataset:
    """Load one owner-provisioned 0600 classification Gold Set without copying it."""

    safe_dataset_id = _safe_token(dataset_id, label="Gold Set dataset id")
    root = paths.data_root / "runtime/diagnostics/classification-gold"
    _private_directory(root)
    dataset_path = _private_child(root, f"{safe_dataset_id}.json")
    digest, _ = _sha256_file(dataset_path, maximum_bytes=MAX_GOLD_DATASET_BYTES)
    try:
        payload = json.loads(dataset_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError):
        raise X2NRuntimeError(ErrorCode.DATA_INTEGRITY_FAILED, "Classification private Gold Set is invalid") from None
    expected = {"cases", "classifier_fingerprint", "dataset_id", "schema_version", "taxonomy_snapshot_sha256"}
    if (
        not isinstance(payload, dict)
        or set(payload) != expected
        or payload.get("schema_version") != CLASSIFICATION_GOLD_DATASET_SCHEMA
        or payload.get("dataset_id") != safe_dataset_id
        or not isinstance(payload.get("cases"), list)
        or not 1 <= len(payload["cases"]) <= MAX_GOLD_CASES
    ):
        _fail(ErrorCode.DATA_INTEGRITY_FAILED, "Classification private Gold Set shape is invalid")
    return PrivateClassificationGoldDataset(
        dataset_id=safe_dataset_id,
        sha256=digest,
        taxonomy_snapshot_sha256=payload["taxonomy_snapshot_sha256"],
        classifier_fingerprint=payload["classifier_fingerprint"],
        cases=tuple(_gold_case_from_private_payload(item) for item in payload["cases"]),
    )


@dataclass(frozen=True)
class CategoryEvaluation:
    category_id: UUID
    cases: int
    true_positives: int
    false_positives: int
    false_negatives: int
    f1: float

    def safe_dict(self) -> dict[str, float | int | str]:
        return {
            "cases": self.cases,
            "category_id": str(self.category_id),
            "f1": self.f1,
            "false_negatives": self.false_negatives,
            "false_positives": self.false_positives,
            "true_positives": self.true_positives,
        }


def _wilson_interval(successes: int, total: int) -> tuple[float | None, float | None]:
    if total == 0:
        return None, None
    z = 1.959963984540054
    proportion = successes / total
    denominator = 1 + (z * z / total)
    center = (proportion + z * z / (2 * total)) / denominator
    margin = z * math.sqrt((proportion * (1 - proportion) + z * z / (4 * total)) / total) / denominator
    return max(0.0, center - margin), min(1.0, center + margin)


def _calibration_profile(
    *,
    dataset_sha256: str,
    snapshot_sha256: str,
    scores: Sequence[tuple[float, bool]],
) -> CalibrationProfile:
    definitions = (("low", 0.0, 0.50), ("medium", 0.50, 0.90), ("high", 0.90, 1.0))
    buckets: list[CalibrationBucket] = []
    for name, lower, upper in definitions:
        values = [correct for score, correct in scores if lower <= score < upper or (score == 1.0 and upper == 1.0)]
        buckets.append(CalibrationBucket(name, lower, upper, len(values), sum(values)))
    return CalibrationProfile(
        version="classification-calibration-v1",
        taxonomy_snapshot_sha256=snapshot_sha256,
        dataset_sha256=dataset_sha256,
        buckets=tuple(buckets),
    )


@dataclass(frozen=True)
class ClassificationEvaluationReport:
    scope: Literal["ci_synth_contract_only", "private_gold"]
    status: Literal["pass", "low_quality", "not_run"]
    dataset_sha256: str
    taxonomy_snapshot_sha256: str
    classifier_fingerprint: str
    evaluated_cases: int
    enabled_category_count: int
    representative_category_count: int
    macro_f1: float
    high_confidence_cases: int
    high_confidence_correct: int
    high_confidence_precision: float | None
    high_confidence_precision_ci95_lower: float | None
    high_confidence_precision_ci95_upper: float | None
    high_confidence_coverage: float
    auto_classify_allowed: bool
    category_reports: tuple[CategoryEvaluation, ...]
    calibration: CalibrationProfile
    evaluation_sha256: str = field(init=False)

    def __post_init__(self) -> None:
        for value, label in (
            (self.dataset_sha256, "evaluation dataset"),
            (self.taxonomy_snapshot_sha256, "evaluation taxonomy snapshot"),
            (self.classifier_fingerprint, "evaluation classifier"),
        ):
            _hash(value, label=label)
        if self.scope not in {"ci_synth_contract_only", "private_gold"} or self.status not in {
            "pass",
            "low_quality",
            "not_run",
        }:
            _fail(ErrorCode.DATA_INTEGRITY_FAILED, "Classification evaluation state is invalid")
        if self.status == "pass" and (self.scope != "private_gold" or not self.auto_classify_allowed):
            _fail(ErrorCode.DATA_INTEGRITY_FAILED, "Classification pass cannot originate from synthetic evaluation")
        if self.scope == "ci_synth_contract_only" and (self.status != "not_run" or self.auto_classify_allowed):
            _fail(ErrorCode.DATA_INTEGRITY_FAILED, "Synthetic evaluation cannot enable automatic classification")
        object.__setattr__(self, "evaluation_sha256", _canonical_sha256(self.safe_dict(include_evaluation_hash=False)))

    def safe_dict(self, *, include_evaluation_hash: bool = True) -> dict[str, object]:
        payload: dict[str, object] = {
            "auto_classify_allowed": self.auto_classify_allowed,
            "calibration": self.calibration.safe_dict(),
            "categories": [item.safe_dict() for item in self.category_reports],
            "classifier_fingerprint": self.classifier_fingerprint,
            "dataset_sha256": self.dataset_sha256,
            "enabled_category_count": self.enabled_category_count,
            "evaluated_cases": self.evaluated_cases,
            "high_confidence_cases": self.high_confidence_cases,
            "high_confidence_correct": self.high_confidence_correct,
            "high_confidence_coverage": self.high_confidence_coverage,
            "high_confidence_precision": self.high_confidence_precision,
            "high_confidence_precision_ci95_lower": self.high_confidence_precision_ci95_lower,
            "high_confidence_precision_ci95_upper": self.high_confidence_precision_ci95_upper,
            "macro_f1": self.macro_f1,
            "representative_category_count": self.representative_category_count,
            "scope": self.scope,
            "status": self.status,
            "taxonomy_snapshot_sha256": self.taxonomy_snapshot_sha256,
        }
        if include_evaluation_hash:
            payload["evaluation_sha256"] = self.evaluation_sha256
        return payload


class ClassificationEvaluator:
    """Private Gold Set evaluator; synthetic cases can test shape but never grant quality."""

    def __init__(self, *, classifier: ConstrainedClassifier = ConstrainedClassifier()) -> None:
        self.classifier = classifier

    def evaluate(
        self,
        cases: Sequence[ClassificationGoldCase],
        snapshot: TaxonomySnapshot,
        *,
        private_gold: bool,
        dataset_sha256: str,
        expected_classifier_fingerprint: str | None = None,
    ) -> ClassificationEvaluationReport:
        _hash(dataset_sha256, label="Gold Set dataset hash")
        if not cases or len(cases) > MAX_GOLD_CASES:
            _fail(ErrorCode.INVALID_INPUT, "Classification evaluation case count is invalid")
        if not snapshot.enabled_categories:
            _fail(ErrorCode.POLICY_BLOCKED, "Classification evaluation requires an Owner taxonomy")
        if private_gold and any(case.synthetic for case in cases):
            _fail(ErrorCode.POLICY_BLOCKED, "Classification private Gold Set cannot contain synthetic cases")
        if expected_classifier_fingerprint is not None and expected_classifier_fingerprint != self.classifier.descriptor.fingerprint:
            _fail(ErrorCode.DATA_INTEGRITY_FAILED, "Classification Gold Set classifier provenance is stale")
        enabled_ids = {category.category_id for category in snapshot.enabled_categories}
        if any(case.expected_category_id not in enabled_ids for case in cases):
            _fail(ErrorCode.DATA_INTEGRITY_FAILED, "Classification Gold Set refers to an unknown or disabled category")
        predictions: list[tuple[ClassificationGoldCase, UUID | None, float]] = []
        with self.classifier.session() as session:
            for case in cases:
                request = ClassificationRequest(
                    content_key=case.content_key,
                    sources=(ClassificationSource(case.evidence_artifact_id, case.input_text),),
                )
                suggestion = session.suggest(request, snapshot)
                predictions.append((case, suggestion.primary_category_id, suggestion.safe_confidence or 0.0))
        per_category: list[CategoryEvaluation] = []
        for category_id in sorted(enabled_ids, key=str):
            expected = [row for row in predictions if row[0].expected_category_id == category_id]
            true_positives = sum(predicted == category_id and case.expected_category_id == category_id for case, predicted, _ in predictions)
            false_positives = sum(predicted == category_id and case.expected_category_id != category_id for case, predicted, _ in predictions)
            false_negatives = sum(predicted != category_id and case.expected_category_id == category_id for case, predicted, _ in predictions)
            denominator = 2 * true_positives + false_positives + false_negatives
            f1 = 0.0 if denominator == 0 else 2 * true_positives / denominator
            per_category.append(
                CategoryEvaluation(category_id, len(expected), true_positives, false_positives, false_negatives, f1)
            )
        macro_f1 = sum(item.f1 for item in per_category) / len(per_category)
        high = [(case, predicted, score) for case, predicted, score in predictions if score >= AUTO_ACCEPT_THRESHOLD]
        high_correct = sum(predicted == case.expected_category_id for case, predicted, _ in high)
        high_precision = None if not high else high_correct / len(high)
        interval_lower, interval_upper = _wilson_interval(high_correct, len(high))
        coverage = len(high) / len(cases)
        representatives = sum(item.cases >= MIN_CASES_PER_ENABLED_CATEGORY for item in per_category)
        calibration = _calibration_profile(
            dataset_sha256=dataset_sha256,
            snapshot_sha256=snapshot.snapshot_sha256,
            scores=[(score, predicted == case.expected_category_id) for case, predicted, score in predictions],
        )
        sufficient = (
            len(cases) >= MIN_PRIVATE_GOLD_CASES
            and representatives == len(per_category)
            and len(high) >= MIN_HIGH_CONFIDENCE_CASES
        )
        quality_pass = (
            sufficient
            and high_precision is not None
            and high_precision >= MIN_HIGH_CONFIDENCE_PRECISION
            and macro_f1 >= MACRO_F1_REFERENCE
        )
        if private_gold:
            scope: Literal["ci_synth_contract_only", "private_gold"] = "private_gold"
            status: Literal["pass", "low_quality", "not_run"] = "pass" if quality_pass else "low_quality"
            auto_allowed = quality_pass
        else:
            scope = "ci_synth_contract_only"
            status = "not_run"
            auto_allowed = False
        return ClassificationEvaluationReport(
            scope=scope,
            status=status,
            dataset_sha256=dataset_sha256,
            taxonomy_snapshot_sha256=snapshot.snapshot_sha256,
            classifier_fingerprint=self.classifier.descriptor.fingerprint,
            evaluated_cases=len(cases),
            enabled_category_count=len(per_category),
            representative_category_count=representatives,
            macro_f1=macro_f1,
            high_confidence_cases=len(high),
            high_confidence_correct=high_correct,
            high_confidence_precision=high_precision,
            high_confidence_precision_ci95_lower=interval_lower,
            high_confidence_precision_ci95_upper=interval_upper,
            high_confidence_coverage=coverage,
            auto_classify_allowed=auto_allowed,
            category_reports=tuple(per_category),
            calibration=calibration,
        )


class ClassificationStore(Protocol):
    def append_classification(self, classification: Classification) -> Any: ...


class OwnerReviewService:
    """Persist only explicit Owner confirmation/correction as append-only classifications."""

    def __init__(self, store: ClassificationStore) -> None:
        self._store = store

    @staticmethod
    def _validate_suggestion(suggestion: ClassificationSuggestion, snapshot: TaxonomySnapshot) -> UUID:
        if suggestion.taxonomy_snapshot_sha256 != snapshot.snapshot_sha256:
            _fail(ErrorCode.DATA_INTEGRITY_FAILED, "Review suggestion taxonomy snapshot is stale")
        if suggestion.primary_category_id is None:
            _fail(ErrorCode.POLICY_BLOCKED, "Unclassified content requires an explicit Owner category choice")
        snapshot.require_enabled(suggestion.primary_category_id)
        return suggestion.primary_category_id

    def confirm(
        self,
        suggestion: ClassificationSuggestion,
        snapshot: TaxonomySnapshot,
        *,
        created_at: str,
        tags: tuple[str, ...] = (),
    ) -> Any:
        self._validate_suggestion(suggestion, snapshot)
        classification = suggestion.to_classification(
            created_at=created_at,
            review_status=ReviewStatus.OWNER_CONFIRMED,
            tags=tags,
        )
        return self._store.append_classification(classification)

    def correct(
        self,
        suggestion: ClassificationSuggestion,
        snapshot: TaxonomySnapshot,
        *,
        primary_category_id: UUID,
        supersedes_classification_id: str,
        created_at: str,
        tags: tuple[str, ...] = (),
    ) -> Any:
        if suggestion.taxonomy_snapshot_sha256 != snapshot.snapshot_sha256:
            _fail(ErrorCode.DATA_INTEGRITY_FAILED, "Review suggestion taxonomy snapshot is stale")
        snapshot.require_enabled(primary_category_id)
        _opaque_ref(supersedes_classification_id, label="review superseded classification id")
        classification = suggestion.to_classification(
            created_at=created_at,
            review_status=ReviewStatus.OWNER_CORRECTED,
            tags=tags,
            supersedes_classification_id=supersedes_classification_id,
            primary_category_id=primary_category_id,
            decision_mode=DecisionMode.HUMAN,
        )
        return self._store.append_classification(classification)
