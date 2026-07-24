from __future__ import annotations

import re
import tracemalloc
from datetime import date
from functools import partial

import pytest
from stage6_support import GeneratedMailboxClient, canonical_with_attachments, synthetic_xlsx

from moomooau_archive.attachment_inspector import (
    AttachmentDecision,
    AttachmentInspector,
    AttachmentLimits,
)
from moomooau_archive.capacity import (
    GIT_REPOSITORY_MUTATION_OVERHEAD_BYTES,
    GITHUB_GIT_OBJECT_ENFORCED_BYTES,
    GITHUB_RELEASE_ASSET_MAXIMUM_BYTES,
    CapacityDemand,
    CapacityLimits,
    CapacityPolicy,
    CapacitySnapshot,
    CapacityState,
    git_capacity_demand,
    reserved_git_capacity_demand,
)
from moomooau_archive.gmail_discovery import FullMailboxDiscoverer
from moomooau_archive.load_probe import (
    SyntheticLoadProfile,
    partition_key,
    run_streaming_load,
)
from moomooau_archive.operation_gate import (
    OperationalGate,
    OperationGateError,
    SensitiveOperation,
)


def _snapshot(
    *,
    git: int = 1_000_000,
    lfs: int = 1_000_000,
    git_object: int = 100_000,
    lfs_object: int = 100_000,
    release: int = 100_000,
) -> CapacitySnapshot:
    return CapacitySnapshot(git, lfs, git_object, lfs_object, release)


def _limits() -> CapacityLimits:
    return CapacityLimits(
        lfs_storage_budget_bytes=10_000_000_000,
        lfs_object_maximum_bytes=2_000_000_000,
    )


def _record_operation(destination: list[str], operation: SensitiveOperation) -> None:
    destination.append(operation.value)


def test_t0607_l3_streams_100k_messages_and_200k_attachments_through_concurrent_index() -> None:
    profile = SyntheticLoadProfile(100_000, 200_000, 8)
    tracemalloc.start()
    try:
        result = run_streaming_load(profile, batch_size=500)
        _current, peak = tracemalloc.get_traced_memory()
    finally:
        tracemalloc.stop()
    assert result.message_count == 100_000
    assert result.attachment_count == 200_000
    assert result.batches == 200
    assert result.maximum_batch_size == 500
    assert result.logical_object_count == 300_000
    assert result.created_count == result.unchanged_count == 300_000
    assert result.upsert_calls == 600_000
    assert result.configured_concurrency == 8
    assert re.fullmatch(r"[0-9a-f]{64}", result.stream_root)
    assert peak < 384 * 1024 * 1024


def test_t0607_concurrent_content_identity_root_is_deterministic() -> None:
    profile = SyntheticLoadProfile(1_000, 2_000, 4)
    first = run_streaming_load(profile, batch_size=137)
    second = run_streaming_load(profile, batch_size=500)
    assert first.stream_root == second.stream_root
    assert first.logical_object_count == second.logical_object_count == 3_000
    assert first.maximum_batch_size == 137
    assert second.maximum_batch_size == 500


def test_t0607_full_mailbox_discovery_reads_500_data_pages_without_gap() -> None:
    client = GeneratedMailboxClient(pages=500, refs_per_page=200)
    result = FullMailboxDiscoverer(
        client,  # type: ignore[arg-type]
        max_pages=503,
        max_message_refs=100_000,
    ).scan()
    assert len(result.refs) == 100_000
    assert result.refs[0].message_id == "msg-000000"
    assert result.refs[-1].message_id == "msg-099999"
    assert len({item.message_id for item in result.refs}) == 100_000
    assert result.pages_read == client.calls == 503
    assert dict(result.scope_ids)["ALL_MAIL"] == frozenset(item.message_id for item in result.refs)


def test_t0607_large_attachment_mime_depth_and_zip_ratio_fail_closed() -> None:
    large = AttachmentInspector(
        AttachmentLimits(
            maximum_attachment_bytes=1_024,
            maximum_total_decoded_bytes=2_048,
        )
    ).inspect(
        canonical_with_attachments(
            (("large.bin", "application", "octet-stream", b"x" * 4_096),),
            suffix="large-boundary",
        )
    )
    assert large.attachments[0].decision is AttachmentDecision.QUARANTINED
    assert large.attachments[0].content is None

    bomb = AttachmentInspector().inspect(
        canonical_with_attachments(
            (
                (
                    "ratio.xlsx",
                    "application",
                    "octet-stream",
                    synthetic_xlsx(bomb_bytes=1_000_000),
                ),
            ),
            suffix="zip-ratio-boundary",
        )
    )
    assert bomb.attachments[0].reason_code == "ZIP_BOMB_LIMIT"

    nested_raw = (
        b"MIME-Version: 1.0\r\n"
        b"Content-Type: multipart/mixed; boundary=one\r\n\r\n"
        b"--one\r\nContent-Type: multipart/mixed; boundary=two\r\n\r\n"
        b"--two\r\nContent-Type: text/plain\r\n\r\nsynthetic\r\n"
        b"--two--\r\n--one--\r\n"
    )
    from hashlib import sha256

    from moomooau_archive.canonical_raw import CanonicalRaw

    nested = CanonicalRaw(
        message_id="synthetic-depth",
        thread_id="thread-synthetic-depth",
        internal_date_ms=1_767_225_600_000,
        label_ids=("INBOX",),
        plaintext_sha256=sha256(nested_raw).hexdigest(),
        byte_count=len(nested_raw),
        data=nested_raw,
    )
    depth = AttachmentInspector(AttachmentLimits(maximum_depth=1)).inspect(nested)
    assert depth.message_quarantined
    assert depth.message_reason_code == "MIME_DEPTH_LIMIT"


def test_t0607_capacity_states_gate_actual_operations_and_ten_year_partitions() -> None:
    policy = CapacityPolicy()
    unknown = policy.evaluate(
        _snapshot(),
        CapacityLimits(lfs_storage_budget_bytes=None, lfs_object_maximum_bytes=None),
    )
    green = policy.evaluate(_snapshot(), _limits())
    yellow = policy.evaluate(_snapshot(git=7_500_000_000), _limits())
    red = policy.evaluate(_snapshot(git=9_100_000_000), _limits())
    release_red = policy.evaluate(
        _snapshot(release=GITHUB_RELEASE_ASSET_MAXIMUM_BYTES),
        _limits(),
    )
    assert [item.state for item in (unknown, green, yellow, red, release_red)] == [
        CapacityState.UNKNOWN,
        CapacityState.GREEN,
        CapacityState.YELLOW,
        CapacityState.RED,
        CapacityState.RED,
    ]

    executed: list[str] = []
    for assessment in (unknown, red, release_red):
        gate = OperationalGate(assessment)
        with pytest.raises(OperationGateError):
            gate.execute(
                SensitiveOperation.PRODUCTION_RUN,
                partial(_record_operation, executed, SensitiveOperation.PRODUCTION_RUN),
            )
        for operation in (
            SensitiveOperation.RAW_WRITE,
            SensitiveOperation.PROCESSED_WRITE,
            SensitiveOperation.TIMELINE_WRITE,
            SensitiveOperation.BACKFILL,
        ):
            with pytest.raises(OperationGateError):
                gate.execute(
                    operation,
                    partial(_record_operation, executed, operation),
                    demand=CapacityDemand(
                        git_repository_add_bytes=1,
                        git_object_bytes=1,
                    ),
                )
        with pytest.raises(OperationGateError):
            gate.execute(
                SensitiveOperation.M3,
                partial(_record_operation, executed, SensitiveOperation.M3),
            )
    assert executed == []

    yellow_gate = OperationalGate(yellow)
    yellow_gate.execute(
        SensitiveOperation.RAW_WRITE,
        lambda: executed.append("raw"),
        demand=CapacityDemand(git_repository_add_bytes=1, git_object_bytes=1),
    )
    with pytest.raises(OperationGateError):
        yellow_gate.execute(
            SensitiveOperation.BACKFILL,
            lambda: executed.append("backfill"),
            demand=CapacityDemand(git_repository_add_bytes=1, git_object_bytes=1),
        )
    green_gate = OperationalGate(green)
    green_gate.execute(
        SensitiveOperation.BACKFILL,
        lambda: executed.append("backfill"),
        demand=CapacityDemand(git_repository_add_bytes=1, git_object_bytes=1),
    )
    assert executed == ["raw", "backfill"]

    projected_gate = OperationalGate(policy.evaluate(_snapshot(git=8_800_000_000), _limits()))
    with pytest.raises(OperationGateError, match="projected"):
        projected_gate.execute(
            SensitiveOperation.RAW_WRITE,
            lambda: executed.append("projected-crossing"),
            demand=CapacityDemand(
                git_repository_add_bytes=200_000_000,
                git_object_bytes=1_000_000,
            ),
        )
    with pytest.raises(OperationGateError, match="prospective"):
        green_gate.execute(
            SensitiveOperation.PROCESSED_WRITE,
            lambda: executed.append("missing-demand"),
        )
    assert executed == ["raw", "backfill"]

    partitions = {
        partition_key(date(year, month, 1)) for year in range(2016, 2026) for month in range(1, 13)
    }
    assert len(partitions) == 120
    assert min(partitions) == "2016/01"
    assert max(partitions) == "2025/12"


def test_t0607_prospective_capacity_covers_every_dimension_and_uncertain_writes() -> None:
    policy = CapacityPolicy()
    projected_red = (
        policy.evaluate(
            _snapshot(lfs=8_800_000_000),
            _limits(),
            CapacityDemand(lfs_storage_add_bytes=200_000_000),
        ),
        policy.evaluate(
            _snapshot(),
            _limits(),
            CapacityDemand(git_object_bytes=GITHUB_GIT_OBJECT_ENFORCED_BYTES),
        ),
        policy.evaluate(
            _snapshot(),
            _limits(),
            CapacityDemand(lfs_object_bytes=2_000_000_000),
        ),
        policy.evaluate(
            _snapshot(),
            _limits(),
            CapacityDemand(live_release_asset_bytes=GITHUB_RELEASE_ASSET_MAXIMUM_BYTES),
        ),
    )
    assert all(item.state is CapacityState.RED and not item.write_allowed for item in projected_red)

    executed: list[str] = []
    gate = OperationalGate(policy.evaluate(_snapshot(git=8_800_000_000), _limits()))
    with pytest.raises(RuntimeError, match="uncertain remote response"):
        gate.execute(
            SensitiveOperation.RAW_WRITE,
            lambda: (_ for _ in ()).throw(RuntimeError("uncertain remote response")),
            demand=CapacityDemand(
                git_repository_add_bytes=100_000_000,
                git_object_bytes=1_000_000,
            ),
        )
    assert gate.consumed_capacity.git_repository_add_bytes == 100_000_000
    with pytest.raises(OperationGateError, match="projected"):
        gate.execute(
            SensitiveOperation.PROCESSED_WRITE,
            lambda: executed.append("should-not-run"),
            demand=CapacityDemand(
                git_repository_add_bytes=100_000_000,
                git_object_bytes=1_000_000,
            ),
        )
    assert executed == []

    exact = git_capacity_demand((b"x", b"yy"))
    assert exact.git_repository_add_bytes == 3 + 2 * GIT_REPOSITORY_MUTATION_OVERHEAD_BYTES
    assert exact.git_object_bytes == 2
    reserved = reserved_git_capacity_demand(1024, mutation_count=4, release_asset_bytes=2048)
    assert reserved.git_repository_add_bytes == 4 * (1024 + GIT_REPOSITORY_MUTATION_OVERHEAD_BYTES)
    assert reserved.git_object_bytes == 1024
    assert reserved.live_release_asset_bytes == 2048
