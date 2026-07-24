from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator

from moomooau_archive.public_inventory import (
    DatasetAvailability,
    PrivateDatasetObservation,
    PublicConclusion,
    PublicInventoryError,
    PublicNextAction,
    PublicRunConclusion,
    PublicRunState,
    StrictPublicInventoryPublisher,
)
from moomooau_archive.secret_values import SecretBytes

PROJECT_ROOT = Path(__file__).resolve().parents[2]


def test_t0407_public_inventory_contains_only_buckets_versions_status_and_opaque_root() -> None:
    now = datetime(2026, 7, 20, 4, 30, tzinfo=UTC)
    private_root = "b" * 64
    observations = (
        PrivateDatasetObservation(
            dataset_name="document_envelopes",
            schema_version="1.0.0",
            parser_versions=("1.0.0", "2.0.0"),
            availability=DatasetAvailability.AVAILABLE,
            exact_count=137,
            latest_recorded_at_utc=now - timedelta(hours=3),
            private_snapshot_root=private_root,
        ),
        PrivateDatasetObservation(
            dataset_name="statements",
            schema_version="1.0.0",
            parser_versions=("1.0.0",),
            availability=DatasetAvailability.UNAVAILABLE,
            exact_count=0,
            latest_recorded_at_utc=None,
            private_snapshot_root="c" * 64,
        ),
    )
    conclusion = PublicRunConclusion(
        PublicRunState.NOT_RUN,
        PublicConclusion.NOT_RUN,
        PublicConclusion.NOT_RUN,
        PublicNextAction.RUN_PRODUCTION_ACCEPTANCE,
    )
    key = SecretBytes(b"synthetic-public-opaque-root-key-material")
    try:
        first = StrictPublicInventoryPublisher().render(
            observations,
            conclusion,
            now_utc=now,
            opaque_root_key=key,
        )
        second = StrictPublicInventoryPublisher().render(
            tuple(reversed(observations)),
            conclusion,
            now_utc=now,
            opaque_root_key=key,
        )
    finally:
        key.destroy()
    assert first.payload == second.payload
    assert first.opaque_root == second.opaque_root
    value = json.loads(first.payload)
    assert value["datasets"][0]["count_bucket"] == "100+"
    assert value["datasets"][0]["freshness_bucket"] == "<24h"
    assert value["datasets"][1]["count_bucket"] == "0"
    assert value["datasets"][1]["freshness_bucket"] == "no-data"
    assert value["run"] == {
        "state": "NOT_RUN",
        "test_conclusion": "NOT_RUN",
        "recovery_conclusion": "NOT_RUN",
        "next_action": "RUN_PRODUCTION_ACCEPTANCE",
    }
    text = first.payload.decode("utf-8")
    assert "exact_count" not in text
    assert all(item != 137 for item in _walk_values(value))
    assert now.isoformat() not in text
    assert private_root not in text
    assert "MooMooAU/" not in text
    assert "source_id" not in text

    schema = json.loads(
        (
            PROJECT_ROOT / "machine/stages/S4/public-schemas/public-inventory-v1.schema.json"
        ).read_text(encoding="utf-8")
    )
    Draft202012Validator(schema).validate(value)


@pytest.mark.parametrize(
    ("state", "action"),
    [
        (PublicRunState.DEGRADED_RAW_ONLY, PublicNextAction.RETRY),
        (PublicRunState.WAITING_PASSWORD, PublicNextAction.REPROCESS_WITH_PROTECTED_SECRET),
        (PublicRunState.M3_FAILED, PublicNextAction.REPAIR_M3),
        (PublicRunState.TIMELINE_FAILED, PublicNextAction.REPAIR_TIMELINE),
        (PublicRunState.FAILED, PublicNextAction.INVESTIGATE),
    ],
)
def test_t0407_public_run_state_preserves_diagnostic_action_without_private_details(
    state: PublicRunState,
    action: PublicNextAction,
) -> None:
    conclusion = PublicRunConclusion(
        state,
        PublicConclusion.FAIL,
        PublicConclusion.FAIL,
        action,
    )
    assert conclusion.run_state is state
    assert conclusion.next_action is action


def test_t0407_healthy_and_future_freshness_claims_fail_closed() -> None:
    with pytest.raises(PublicInventoryError, match="healthy"):
        PublicRunConclusion(
            PublicRunState.HEALTHY,
            PublicConclusion.PASS,
            PublicConclusion.NOT_RUN,
            PublicNextAction.NONE,
        )
    with pytest.raises(PublicInventoryError, match="state and next action"):
        PublicRunConclusion(
            PublicRunState.M3_FAILED,
            PublicConclusion.FAIL,
            PublicConclusion.FAIL,
            PublicNextAction.REPAIR_TIMELINE,
        )

    now = datetime(2026, 7, 20, 4, 30, tzinfo=UTC)
    observation = PrivateDatasetObservation(
        dataset_name="analytics",
        schema_version="1.0.0",
        parser_versions=("1.0.0",),
        availability=DatasetAvailability.AVAILABLE,
        exact_count=1,
        latest_recorded_at_utc=now + timedelta(seconds=1),
        private_snapshot_root="d" * 64,
    )
    key = SecretBytes(b"synthetic-public-opaque-root-key-material")
    try:
        with pytest.raises(PublicInventoryError, match="future"):
            StrictPublicInventoryPublisher().render(
                (observation,),
                PublicRunConclusion(
                    PublicRunState.NOT_RUN,
                    PublicConclusion.NOT_RUN,
                    PublicConclusion.NOT_RUN,
                    PublicNextAction.RUN_PRODUCTION_ACCEPTANCE,
                ),
                now_utc=now,
                opaque_root_key=key,
            )
    finally:
        key.destroy()


def _walk_values(value: object) -> tuple[object, ...]:
    if isinstance(value, dict):
        return tuple(item for nested in value.values() for item in _walk_values(nested))
    if isinstance(value, list):
        return tuple(item for nested in value for item in _walk_values(nested))
    return (value,)
