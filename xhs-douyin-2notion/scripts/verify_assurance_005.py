#!/usr/bin/env python3
"""Fail-closed verifier for the public direct-Owner-MVP core receipt."""

from __future__ import annotations

import json
import re
import subprocess
import sys
from pathlib import Path
from typing import Any, Sequence


PROJECT_ROOT = Path(__file__).resolve().parents[1]
TASK_ID = "TSK.x2n.assurance.005"
RELEASE_VERSION = "v0.0.0.1"
STATUS = "PASS_OWNER_MVP_DIRECT_RELEASE_CORE"
RECEIPT = PROJECT_ROOT / "evidence/release/TSK.x2n.assurance.005.json"
SCHEMA = PROJECT_ROOT / "machine/schemas/stage_6_assurance_005_go_live_receipt.schema.json"
ARTIFACT_POLICY = PROJECT_ROOT / "machine/policy/artifact_allowlist.json"
_SHA256 = re.compile(r"^[0-9a-f]{64}$")
_COMMIT = re.compile(r"^[0-9a-f]{40}$")
_PLATFORM_CDN = re.compile(
    "|".join(
        re.escape("".join(parts))
        for parts in (
            ("xhs", "cdn"),
            ("douyin", "vod"),
            ("byte", "img"),
            ("pstat", "p"),
            ("bili", "video"),
            ("hd", "slb"),
            ("ks", "cdn"),
            ("yx", "imgs"),
            ("sina", "img"),
            ("tb", "cdn"),
            ("ali", "cdn"),
        )
    ),
    re.I,
)


class Assurance005VerificationError(RuntimeError):
    pass


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise Assurance005VerificationError(message)


def _load_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
        raise Assurance005VerificationError("required public receipt or schema is unavailable") from error
    _require(isinstance(value, dict), "public receipt must be an object")
    return value


def _safe_payload(payload: Any) -> None:
    rendered = json.dumps(payload, ensure_ascii=False, sort_keys=True)
    _require("/" + "Users/" not in rendered and "/" + "home/" not in rendered, "local path entered public receipt")
    _require("github" + "_pat_" not in rendered and "Bearer" + " " not in rendered, "credential entered public receipt")
    _require(_PLATFORM_CDN.search(rendered) is None, "platform CDN entered public receipt")


def _git(arguments: Sequence[str]) -> str:
    result = subprocess.run(
        ["git", "-C", str(PROJECT_ROOT), *arguments],
        stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL,
        text=True,
        check=False,
    )
    _require(result.returncode == 0, "local Git release identity is unavailable")
    return result.stdout.strip()


def validate_receipt(receipt: dict[str, Any]) -> dict[str, Any]:
    expected = {
        "artifact",
        "artifact_scan",
        "boundaries",
        "go_live",
        "native_host",
        "phase",
        "release_source",
        "release_version",
        "schema_version",
        "status",
        "task_id",
    }
    _require(set(receipt) == expected, "public receipt shape is invalid")
    _require(
        receipt["schema_version"] == "1.0"
        and receipt["task_id"] == TASK_ID
        and receipt["phase"] == "PH.X2N.6.5"
        and receipt["release_version"] == RELEASE_VERSION
        and receipt["status"] == STATUS,
        "public receipt identity drifted",
    )
    source = receipt["release_source"]
    artifact = receipt["artifact"]
    scan = receipt["artifact_scan"]
    boundaries = receipt["boundaries"]
    go_live = receipt["go_live"]
    host = receipt["native_host"]
    _require(
        isinstance(source, dict)
        and set(source) == {"commit", "tag"}
        and _COMMIT.fullmatch(str(source.get("commit"))) is not None
        and source.get("tag") == RELEASE_VERSION,
        "public receipt release source is invalid",
    )
    _require(
        isinstance(artifact, dict)
        and set(artifact) == {"artifact_sha256", "runtime_data_files", "source_only_artifact"}
        and _SHA256.fullmatch(str(artifact.get("artifact_sha256"))) is not None
        and artifact.get("runtime_data_files") == 0
        and artifact.get("source_only_artifact") is True,
        "public receipt staged artifact is invalid",
    )
    _require(
        isinstance(scan, dict)
        and set(scan) == {"allowlist_findings", "artifact_sha256", "member_count", "runtime_data_files", "status"}
        and scan.get("allowlist_findings") == 0
        and _SHA256.fullmatch(str(scan.get("artifact_sha256"))) is not None
        and type(scan.get("member_count")) is int
        and scan.get("member_count") > 0
        and scan.get("runtime_data_files") == 0
        and scan.get("status") == "PASS",
        "public receipt source artifact scan is invalid",
    )
    _require(
        isinstance(boundaries, dict)
        and set(boundaries)
        == {
            "external_disabled_scope_count",
            "model_mode",
            "private_manifest_item_count",
            "private_manifest_scope_count",
        }
        and boundaries.get("external_disabled_scope_count") == 4
        and boundaries.get("model_mode") in {"disabled", "suggestion_only"}
        and boundaries.get("private_manifest_item_count") == 80
        and boundaries.get("private_manifest_scope_count") == 4,
        "public receipt release boundaries are invalid",
    )
    _require(
        isinstance(go_live, dict)
        and set(go_live)
        == {"baseline_hash", "owner_mvp_baseline_relations", "rollback_rehearsed", "sidepanel_native_handshake"}
        and _SHA256.fullmatch(str(go_live.get("baseline_hash"))) is not None
        and go_live.get("owner_mvp_baseline_relations") == 80
        and go_live.get("rollback_rehearsed") is True
        and go_live.get("sidepanel_native_handshake") == "PASS",
        "public receipt direct MVP proof is invalid",
    )
    _require(
        isinstance(host, dict)
        and set(host) == {"native_host_release_bound", "release_artifact_sha256"}
        and host.get("native_host_release_bound") is True
        and host.get("release_artifact_sha256") == artifact.get("artifact_sha256"),
        "public receipt Native Host binding is invalid",
    )
    _safe_payload(receipt)
    tags = {line for line in _git(("tag", "--points-at", str(source["commit"]))).splitlines() if line}
    _require(RELEASE_VERSION in tags, "public receipt source commit is not release-tagged")
    return {
        "artifact_sha256": artifact["artifact_sha256"],
        "paths_emitted": False,
        "release_commit": source["commit"],
        "status": "PASS",
        "task_id": TASK_ID,
    }


def main() -> int:
    try:
        schema = _load_json(SCHEMA)
        _require(schema.get("$id") == "urn:x2n:stage-6-assurance-005-go-live-receipt:1.0", "receipt schema drifted")
        policy = _load_json(ARTIFACT_POLICY)
        _require(
            {"scripts/run_assurance_005_acceptance.py", "scripts/verify_assurance_005.py"}
            <= set(policy.get("enforcement", [])),
            "public artifact policy does not register assurance005 verification",
        )
        result = validate_receipt(_load_json(RECEIPT))
    except Assurance005VerificationError:
        failure = {"paths_emitted": False, "status": "FAIL_CLOSED", "task_id": TASK_ID}
        print(json.dumps(failure, ensure_ascii=False, sort_keys=True), file=sys.stderr)
        return 2
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
