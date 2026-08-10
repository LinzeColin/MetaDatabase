from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
RUNTIME = ROOT / "runtime"
if str(RUNTIME) not in sys.path:
    sys.path.insert(0, str(RUNTIME))

from shadow_runtime_attestation import (
    CORE_LABEL,
    EXPECTED_MEMORY_BYTES,
    EXPECTED_PORT_MAPPING,
    EXPECTED_STATUS_PAYLOAD,
    SHADOW_LABEL,
    ShadowRuntimeAttestationError,
    collect_shadow_runtime_facts,
    evaluate_shadow_runtime_facts,
)


def _facts(**overrides: object) -> dict[str, object]:
    values: dict[str, object] = {
        "shadow_container_count": 1,
        "core_container_count": 0,
        "shadow_running": True,
        "memory_limit_bytes": EXPECTED_MEMORY_BYTES,
        "memory_swap_limit_bytes": EXPECTED_MEMORY_BYTES,
        "port_mapping": EXPECTED_PORT_MAPPING,
        "status_payload_matches": True,
    }
    values.update(overrides)
    return values


def test_exact_loopback_shadow_snapshot_passes_without_additional_swap() -> None:
    result = evaluate_shadow_runtime_facts(_facts())

    assert result["status"] == "PASS"
    assert result["attestation_valid"] is True
    assert result["failure_codes"] == []
    assert result["observed"]["additional_container_swap_allowed"] is False
    assert result["secret_values_read"] is False
    assert result["config_or_secret_file_read"] is False
    assert result["external_network_accessed"] is False
    assert result["runtime_state_changed"] is False
    assert result["real_time_soak_waited"] is False


@pytest.mark.parametrize(
    ("overrides", "failure_code"),
    [
        ({"shadow_container_count": 0}, "EXACTLY_ONE_SHADOW_CONTAINER"),
        ({"core_container_count": 1}, "CORE_RUNTIME_ABSENT"),
        ({"shadow_running": False}, "SHADOW_CONTAINER_RUNNING"),
        ({"memory_limit_bytes": EXPECTED_MEMORY_BYTES - 1}, "SHADOW_MEMORY_LIMIT_512_MIB"),
        ({"memory_swap_limit_bytes": EXPECTED_MEMORY_BYTES + 1}, "SHADOW_NO_ADDITIONAL_SWAP"),
        ({"port_mapping": "0.0.0.0:8081"}, "LOOPBACK_PORT_MAPPING"),
        ({"status_payload_matches": False}, "SAFE_STATUS_PAYLOAD"),
    ],
)
def test_each_shadow_boundary_fails_closed(overrides: dict[str, object], failure_code: str) -> None:
    result = evaluate_shadow_runtime_facts(_facts(**overrides))

    assert result["status"] == "FAIL"
    assert result["attestation_valid"] is False
    assert failure_code in result["failure_codes"]


def test_malformed_fact_shape_or_types_are_rejected() -> None:
    with pytest.raises(ShadowRuntimeAttestationError):
        evaluate_shadow_runtime_facts({"shadow_container_count": 1})
    with pytest.raises(ShadowRuntimeAttestationError):
        evaluate_shadow_runtime_facts(_facts(status_payload_matches=1))
    with pytest.raises(ShadowRuntimeAttestationError):
        evaluate_shadow_runtime_facts(_facts(memory_limit_bytes=-1))


def test_collection_uses_only_docker_metadata_and_fixed_loopback_status() -> None:
    calls: list[tuple[str, ...]] = []
    container = "synthetic-container-id"

    def run(arguments: tuple[str, ...]) -> str:
        calls.append(arguments)
        responses = {
            ("docker", "ps", "-q", "--filter", SHADOW_LABEL): container + "\n",
            ("docker", "ps", "-q", "--filter", CORE_LABEL): "",
            ("docker", "inspect", "--format", "{{.State.Running}}", container): "true\n",
            (
                "docker",
                "inspect",
                "--format",
                "{{.HostConfig.Memory}}/{{.HostConfig.MemorySwap}}",
                container,
            ): "%d/%d\n" % (EXPECTED_MEMORY_BYTES, EXPECTED_MEMORY_BYTES),
            ("docker", "port", container, "8080/tcp"): EXPECTED_PORT_MAPPING + "\n",
        }
        return responses[arguments]

    probe_calls: list[tuple[str, int]] = []

    def probe(host: str, port: int) -> dict[str, object]:
        probe_calls.append((host, port))
        return dict(EXPECTED_STATUS_PAYLOAD)

    facts = collect_shadow_runtime_facts(run=run, probe=probe)

    assert facts == _facts()
    assert probe_calls == [("127.0.0.1", 8081)]
    assert all(command[0] == "docker" for command in calls)
    assert all("exec" not in command and "compose" not in command for command in calls)


def test_collection_does_not_probe_when_shadow_count_is_not_exactly_one() -> None:
    def run(arguments: tuple[str, ...]) -> str:
        if arguments == ("docker", "ps", "-q", "--filter", SHADOW_LABEL):
            return "one\ntwo\n"
        if arguments == ("docker", "ps", "-q", "--filter", CORE_LABEL):
            return ""
        raise AssertionError("unexpected command: %r" % (arguments,))

    def probe(_host: str, _port: int) -> dict[str, object]:
        raise AssertionError("status probe must not run")

    facts = collect_shadow_runtime_facts(run=run, probe=probe)

    assert facts["shadow_container_count"] == 2
    assert facts["shadow_running"] is None
    assert facts["status_payload_matches"] is False


def test_contract_and_installer_remain_one_shot_and_non_secret() -> None:
    contract = json.loads((RUNTIME / "host_bundle_contract.json").read_text(encoding="utf-8"))
    script = (RUNTIME / "shadow_runtime_attestation.py").read_text(encoding="utf-8")
    installer = (RUNTIME / "install_shadow_runtime_attestation.sh").read_text(encoding="utf-8")

    assert contract["post_freeze_shadow_attestation"] == {
        "script": "runtime/shadow_runtime_attestation.py",
        "installer": "runtime/install_shadow_runtime_attestation.sh",
        "execution": "ONE_SHOT_FIXED_LOOPBACK_ONLY",
        "secret_values_read": False,
        "config_or_secret_file_read": False,
        "external_network_accessed": False,
        "runtime_state_changed": False,
        "real_time_soak_waited": False,
    }
    assert "127.0.0.1" in script
    for forbidden in ("/etc/abd", "cloudflared", "systemctl", "docker compose", "docker exec"):
        assert forbidden not in script
    assert "systemctl" not in installer
    assert "docker" not in installer
    assert "/usr/local/lib/abd/shadow_runtime_attestation.py" in installer
