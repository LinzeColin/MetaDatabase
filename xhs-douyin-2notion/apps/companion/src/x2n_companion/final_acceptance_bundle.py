"""Public-safe final acceptance bundle for the direct Owner MVP release.

The bundle is intentionally generated only after the read-only go-live verifier
has proved an already-active runtime.  It contains aggregate facts and hashes
only; Owner manifests, content, profile state, media, credentials and local
paths are never accepted as inputs or rendered into its files.
"""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Mapping
from pathlib import Path
from typing import Any


BUNDLE_SCHEMA_VERSION = "1.0"
BUNDLE_FILENAMES = (
    "release_manifest.json",
    "governance_receipt.json",
    "traceability_report.json",
    "software_pipeline_summary.json",
    "model_pipeline_summary.json",
    "security_supply_chain_summary.json",
    "chaos_recovery_summary.json",
    "canary_summary.json",
    "owner_mvp_summary.json",
    "migration_rollback_summary.json",
    "system_card.md",
    "release_notes.md",
    "checksums.sha256",
)
_CHECKSUMMED_FILENAMES = tuple(name for name in BUNDLE_FILENAMES if name != "checksums.sha256")
_SHA256 = re.compile(r"^[0-9a-f]{64}$")
_COMMIT = re.compile(r"^[0-9a-f]{40}$")
_A005_ACCEPTANCE_IDS = (
    "ACC.x2n.capture.001",
    "ACC.x2n.capture.002",
    "ACC.x2n.capture.003",
    "ACC.x2n.capture.004",
    "ACC.x2n.capture.005",
    "ACC.x2n.capture.006",
    "ACC.x2n.xhs.001",
    "ACC.x2n.xhs.002",
    "ACC.x2n.dy.001",
    "ACC.x2n.dy.002",
    "ACC.x2n.bili.001",
    "ACC.x2n.ks.001",
    "ACC.x2n.wb.001",
    "ACC.x2n.tb.001",
    "ACC.x2n.data.002",
    "ACC.x2n.rel.006",
    "ACC.x2n.rel.007",
    "ACC.x2n.rel.008",
)


class FinalAcceptanceBundleError(RuntimeError):
    """Raised when public release evidence is incomplete or unsafe."""


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise FinalAcceptanceBundleError(message)


def _canonical_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"), sort_keys=True)


def _json_document(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n"


def _sha256_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _bundle_digest(hashes: Mapping[str, str]) -> str:
    return hashlib.sha256(
        _canonical_json(
            {
                "bundle_schema_version": BUNDLE_SCHEMA_VERSION,
                "file_sha256": {name: hashes[name] for name in _CHECKSUMMED_FILENAMES},
            }
        ).encode("utf-8")
    ).hexdigest()


def _required_receipt(receipt: Mapping[str, Any]) -> None:
    source = receipt.get("release_source")
    artifact = receipt.get("artifact")
    scan = receipt.get("artifact_scan")
    go_live = receipt.get("go_live")
    gates = receipt.get("external_gates")
    knowledge_assets = receipt.get("knowledge_assets")
    _require(
        receipt.get("schema_version") == "1.0"
        and receipt.get("task_id") == "TSK.x2n.assurance.005"
        and receipt.get("phase") == "PH.X2N.6.5"
        and receipt.get("release_version") == "v0.0.0.1"
        and receipt.get("status") == "PASS_OWNER_MVP_DIRECT_RELEASE_CORE",
        "release receipt identity is invalid",
    )
    _require(
        isinstance(source, Mapping)
        and _COMMIT.fullmatch(str(source.get("commit"))) is not None
        and source.get("tag") == "v0.0.0.1",
        "release source identity is invalid",
    )
    _require(
        isinstance(artifact, Mapping)
        and _SHA256.fullmatch(str(artifact.get("artifact_sha256"))) is not None
        and artifact.get("runtime_data_files") == 0
        and artifact.get("source_only_artifact") is True,
        "staged artifact proof is invalid",
    )
    _require(
        isinstance(scan, Mapping)
        and scan.get("status") == "PASS"
        and scan.get("allowlist_findings") == 0
        and scan.get("runtime_data_files") == 0,
        "source artifact scan is invalid",
    )
    _require(
        isinstance(go_live, Mapping)
        and go_live.get("owner_mvp_baseline_relations") == 80
        and go_live.get("rollback_rehearsed") is True
        and go_live.get("sidepanel_native_handshake") == "PASS",
        "owner MVP proof is invalid",
    )
    _require(isinstance(gates, list) and len(gates) == 4, "external gate proof is invalid")
    _require(
        isinstance(knowledge_assets, Mapping)
        and set(knowledge_assets)
        == {
            "markdown_content_count",
            "markdown_library_sha256",
            "markdown_renderer_version",
            "notion_mode",
            "notion_platform_calls",
            "private_durability_manifest_sha256",
        }
        and type(knowledge_assets.get("markdown_content_count")) is int
        and knowledge_assets["markdown_content_count"] >= 1
        and _SHA256.fullmatch(str(knowledge_assets.get("markdown_library_sha256"))) is not None
        and isinstance(knowledge_assets.get("markdown_renderer_version"), str)
        and knowledge_assets.get("notion_mode") == "DISABLED_OWNER_INPUT"
        and type(knowledge_assets.get("notion_platform_calls")) is int
        and knowledge_assets.get("notion_platform_calls") == 0
        and _SHA256.fullmatch(str(knowledge_assets.get("private_durability_manifest_sha256"))) is not None,
        "knowledge-asset and durability proof is invalid",
    )


def build_final_acceptance_bundle(receipt: Mapping[str, Any]) -> tuple[dict[str, str], str]:
    """Render deterministic aggregate-only Bundle documents and their root digest."""

    _required_receipt(receipt)
    source = dict(receipt["release_source"])
    artifact = dict(receipt["artifact"])
    scan = dict(receipt["artifact_scan"])
    boundaries = dict(receipt["boundaries"])
    go_live = dict(receipt["go_live"])
    knowledge_assets = dict(receipt["knowledge_assets"])
    native_host = dict(receipt["native_host"])
    external_gates = [dict(item) for item in receipt["external_gates"]]
    summaries: dict[str, str] = {
        "release_manifest.json": _json_document(
            {
                "bundle_schema_version": BUNDLE_SCHEMA_VERSION,
                "files": list(_CHECKSUMMED_FILENAMES),
                "release_source": source,
                "release_version": receipt["release_version"],
                "task_id": receipt["task_id"],
            }
        ),
        "governance_receipt.json": _json_document(
            {
                "external_gates": external_gates,
                "phase": receipt["phase"],
                "release_version": receipt["release_version"],
                "status": receipt["status"],
                "task_id": receipt["task_id"],
            }
        ),
        "traceability_report.json": _json_document(
            {
                "acceptance_ids": list(_A005_ACCEPTANCE_IDS),
                "external_gate_settlement": "PASS_DISABLED_EXTERNAL_GATE",
                "phase": receipt["phase"],
                "task_id": receipt["task_id"],
            }
        ),
        "software_pipeline_summary.json": _json_document(
            {
                "artifact": artifact,
                "artifact_scan": scan,
                "markdown_library_sha256": knowledge_assets["markdown_library_sha256"],
                "native_host_release_bound": native_host["native_host_release_bound"],
                "source_only_artifact": True,
            }
        ),
        "model_pipeline_summary.json": _json_document(
            {
                "automatic_classification": "disabled",
                "model_mode": boundaries["model_mode"],
                "owner_taxonomy_mutations": 0,
            }
        ),
        "security_supply_chain_summary.json": _json_document(
            {
                "artifact_allowlist_findings": scan["allowlist_findings"],
                "credentials_persisted": 0,
                "external_gate_count": len(external_gates),
                "runtime_data_files": scan["runtime_data_files"],
            }
        ),
        "chaos_recovery_summary.json": _json_document(
            {
                "chaos_campaign_precondition": "TSK.x2n.assurance.004",
                "rollback_rehearsed": go_live["rollback_rehearsed"],
                "rollback_target": "previous_stable_or_disable",
            }
        ),
        "canary_summary.json": _json_document(
            {
                "delivery_mode": "direct_owner_mvp",
                "external_gates": external_gates,
                "pre_release_stage": "none",
                "primary_baseline_relations": go_live["owner_mvp_baseline_relations"],
            }
        ),
        "owner_mvp_summary.json": _json_document(
            {
                "baseline_hash": go_live["baseline_hash"],
                "owner_mvp_baseline_relations": go_live["owner_mvp_baseline_relations"],
                "knowledge_assets": knowledge_assets,
                "private_manifest_item_count": boundaries["private_manifest_item_count"],
                "private_manifest_scope_count": boundaries["private_manifest_scope_count"],
                "sidepanel_native_handshake": go_live["sidepanel_native_handshake"],
            }
        ),
        "migration_rollback_summary.json": _json_document(
            {
                "rollback_rehearsed": go_live["rollback_rehearsed"],
                "private_durability_manifest_sha256": knowledge_assets["private_durability_manifest_sha256"],
                "runtime_online": True,
                "source_artifact_sha256": artifact["artifact_sha256"],
            }
        ),
        "system_card.md": "\n".join(
            (
                "# x2n v0.0.0.1 System Card",
                "",
                "## Release boundary",
                "",
                "- Delivery mode: direct Owner MVP; no pre-release stage.",
                "- Enabled baseline: Xiaohongshu favorites/likes and Douyin favorites/likes, exactly 20 items each.",
                "- Bilibili, Kuaishou, Weibo, and Taobao remain externally gated and make no platform call.",
                "- Markdown is materialized deterministically from Canonical before deployment and its Canonical archive is durably verified.",
                "- Notion is explicitly disabled by the Owner input in this release; it receives no call.",
                "",
                "## Model and taxonomy",
                "",
                f"- Model mode: {boundaries['model_mode']}.",
                "- Automatic classification is disabled; the Owner remains the only primary-taxonomy authority.",
                "",
                "## Safety and recovery",
                "",
                "- Canonical SQLite remains the local truth source; public evidence is aggregate-only.",
                "- The staged Side Panel and Native Host share one verified release artifact identity.",
                "- Rollback rehearsal passed before deployment; rollback disables execution before pointer reversal.",
                "",
            )
        ),
        "release_notes.md": "\n".join(
            (
                "# x2n v0.0.0.1 Release Notes",
                "",
                "## Direct Owner MVP",
                "",
                "- The release is deployed, running, and verified with an immediate local online smoke.",
                "- The Owner MVP baseline contains 80 aggregate relations across four fixed XHS/Douyin scopes.",
                "- The release uses exact private hash manifests, bounded explicit actions, and verified rollback.",
                "- A deterministic Markdown library was rebuilt twice without drift before deployment and Canonical durability was verified.",
                "",
                "## Capability boundary",
                "",
                "- Bilibili, Kuaishou, Weibo, and Taobao are externally gated with flags off, zero calls, and no live-support claim.",
                "- Model capability is explicitly limited to the configured disabled or suggestion-only mode.",
                "",
            )
        ),
    }
    _require(tuple(summaries) == _CHECKSUMMED_FILENAMES, "bundle document order drifted")
    hashes = {name: _sha256_text(summaries[name]) for name in _CHECKSUMMED_FILENAMES}
    summaries["checksums.sha256"] = "".join(f"{hashes[name]}  {name}\n" for name in _CHECKSUMMED_FILENAMES)
    _require(tuple(summaries) == BUNDLE_FILENAMES, "bundle file set drifted")
    return summaries, _bundle_digest(hashes)


def verify_final_acceptance_bundle(
    bundle_directory: Path,
    receipt: Mapping[str, Any],
) -> dict[str, Any]:
    """Verify an immutable public bundle against the public receipt root hash."""

    _required_receipt(receipt)
    expected_digest = receipt.get("final_acceptance_bundle_sha256")
    _require(_SHA256.fullmatch(str(expected_digest)) is not None, "bundle root digest is invalid")
    _require(
        not bundle_directory.is_symlink() and bundle_directory.is_dir(),
        "final acceptance bundle directory is unsafe",
    )
    entries = {entry.name: entry for entry in bundle_directory.iterdir()}
    _require(set(entries) == set(BUNDLE_FILENAMES), "final acceptance bundle file set is invalid")
    documents: dict[str, str] = {}
    for name in BUNDLE_FILENAMES:
        path = entries[name]
        _require(not path.is_symlink() and path.is_file(), "final acceptance bundle member is unsafe")
        try:
            documents[name] = path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError) as error:
            raise FinalAcceptanceBundleError("final acceptance bundle member is unreadable") from error
    expected_lines = [
        f"{_sha256_text(documents[name])}  {name}" for name in _CHECKSUMMED_FILENAMES
    ]
    _require(
        documents["checksums.sha256"].splitlines() == expected_lines,
        "final acceptance bundle checksum manifest is invalid",
    )
    hashes = {name: _sha256_text(documents[name]) for name in _CHECKSUMMED_FILENAMES}
    _require(_bundle_digest(hashes) == expected_digest, "final acceptance bundle root digest diverged")
    try:
        release_manifest = json.loads(documents["release_manifest.json"])
        governance = json.loads(documents["governance_receipt.json"])
        owner_mvp = json.loads(documents["owner_mvp_summary.json"])
        migration = json.loads(documents["migration_rollback_summary.json"])
    except json.JSONDecodeError as error:
        raise FinalAcceptanceBundleError("final acceptance bundle JSON is invalid") from error
    _require(
        release_manifest
        == {
            "bundle_schema_version": BUNDLE_SCHEMA_VERSION,
            "files": list(_CHECKSUMMED_FILENAMES),
            "release_source": receipt["release_source"],
            "release_version": receipt["release_version"],
            "task_id": receipt["task_id"],
        },
        "final acceptance release manifest drifted",
    )
    _require(
        governance.get("external_gates") == receipt["external_gates"]
        and governance.get("status") == receipt["status"],
        "final acceptance governance receipt drifted",
    )
    _require(
        owner_mvp.get("owner_mvp_baseline_relations") == 80
        and owner_mvp.get("baseline_hash") == receipt["go_live"]["baseline_hash"]
        and owner_mvp.get("knowledge_assets") == receipt["knowledge_assets"]
        and migration.get("rollback_rehearsed") is True
        and migration.get("private_durability_manifest_sha256")
        == receipt["knowledge_assets"]["private_durability_manifest_sha256"]
        and migration.get("source_artifact_sha256") == receipt["artifact"]["artifact_sha256"],
        "final acceptance owner MVP summary drifted",
    )
    _require(
        receipt["release_version"] in documents["system_card.md"]
        and receipt["release_version"] in documents["release_notes.md"],
        "final acceptance markdown identity drifted",
    )
    return {
        "bundle_file_count": len(BUNDLE_FILENAMES),
        "bundle_sha256": expected_digest,
        "paths_emitted": False,
    }
