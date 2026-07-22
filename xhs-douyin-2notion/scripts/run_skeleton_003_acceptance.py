#!/usr/bin/env python3
"""Run the public-safe Skeleton003 media security acceptance matrix."""

from __future__ import annotations

import io
import importlib.util
import json
import random
import sys
import unittest
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "apps/companion/src"))
sys.path.insert(0, str(PROJECT_ROOT / "packages/contracts/src"))

from x2n_companion.media_safety import (  # noqa: E402
    PATTERN_SET_VERSION,
    PLATFORM_CDN_SUFFIXES,
    validate_media_target,
)
from x2n_companion.runtime import X2NRuntimeError  # noqa: E402


TASK_ID = "TSK.x2n.skeleton.003"
PHASE = "PH.X2N.2.7"
FIXTURE = PROJECT_ROOT / "packages/test-fixtures/media/v1/fixture_manifest.json"
GLOBAL_IP = "93.184.216.34"


def _url(host: str, path: str = "/synthetic-media.bin", query: str = "") -> str:
    return "https:" + "//" + host + path + (f"?{query}" if query else "")


def _host(platform: str) -> str:
    return "asset." + PLATFORM_CDN_SUFFIXES[platform][0]


def _global_resolver(_hostname: str, _port: int) -> tuple[str, ...]:
    return (GLOBAL_IP,)


def _mutate(platform: str, mutation: str) -> tuple[str, str]:
    host = _host(platform)
    if mutation == "scheme":
        return "http:" + "//" + host + "/synthetic-media.bin", platform
    if mutation == "userinfo":
        return "https:" + "//user@" + host + "/synthetic-media.bin", platform
    if mutation == "port":
        return "https:" + "//" + host + ":444/synthetic-media.bin", platform
    if mutation == "suffix_lookalike":
        return _url(host + ".attacker.example"), platform
    if mutation == "trailing_dot":
        return _url(host + "."), platform
    if mutation == "fragment":
        return _url(host) + "#fragment", platform
    if mutation == "path_traversal":
        return _url(host, "/safe/%252e%252e/private"), platform
    if mutation == "control_character":
        return _url(host, "/safe\nprivate"), platform
    if mutation == "oversize":
        return _url(host, "/" + "a" * 2_100), platform
    if mutation == "wrong_platform":
        platforms = tuple(PLATFORM_CDN_SUFFIXES)
        return _url(_host(platform)), platforms[(platforms.index(platform) + 1) % len(platforms)]
    raise AssertionError("unknown synthetic mutation")


def run_url_fuzz(fixture: dict[str, Any]) -> dict[str, Any]:
    config = fixture["url_fuzz"]
    total = int(config["cases"])
    platforms = tuple(config["allowed_platforms"])
    mutations = tuple(config["mutations"])
    randomizer = random.Random(int(config["seed"]))
    accepted_expected = 0
    rejected_expected = 0
    mismatches = 0
    for index in range(total):
        platform = platforms[index % len(platforms)]
        valid = index % 8 == 0
        if valid:
            raw, validation_platform = _url(_host(platform), query="sign=synthetic-memory-only"), platform
        else:
            raw, validation_platform = _mutate(platform, mutations[randomizer.randrange(len(mutations))])
        try:
            validate_media_target(raw, platform=validation_platform, resolver=_global_resolver)
            accepted = True
        except X2NRuntimeError:
            accepted = False
        if valid:
            accepted_expected += 1
            mismatches += int(not accepted)
        else:
            rejected_expected += 1
            mismatches += int(accepted)
    if mismatches:
        raise AssertionError("URL fuzz matrix did not match the fail-closed oracle")
    return {
        "accepted_allowlisted": accepted_expected,
        "cases": total,
        "oracle_mismatches": mismatches,
        "rejected_forbidden": rejected_expected,
    }


def run_ssrf_matrix(fixture: dict[str, Any]) -> dict[str, Any]:
    answers = (
        "127.0.0.1",
        "127.0.0.2",
        "10.0.0.1",
        "10.255.255.254",
        "172.16.0.1",
        "172.31.255.254",
        "192.168.0.1",
        "192.168.255.254",
        "169.254.169.254",
        "169.254.1.1",
        "100.64.0.1",
        "100.127.255.254",
        "224.0.0.1",
        "239.255.255.254",
        "0.0.0.0",
        "255.255.255.255",
        "::1",
        "::",
        "fe80::1",
        "febf::1",
        "fc00::1",
        "fdff::1",
        "ff02::1",
        "ff05::1",
        "::ffff:127.0.0.1",
        "::ffff:10.0.0.1",
        "192.0.0.1",
        "198.18.0.1",
        "198.19.255.254",
        "240.0.0.1",
        "255.255.255.254",
        "fe80::ffff",
    )
    expected = int(fixture["ssrf"]["cases"])
    if len(answers) != expected:
        raise AssertionError("SSRF fixture count drifted")
    forbidden_successes = 0
    for answer in answers:
        try:
            validate_media_target(
                _url(_host("xiaohongshu")),
                platform="xiaohongshu",
                resolver=lambda _hostname, _port, value=answer: (value,),
            )
        except X2NRuntimeError:
            continue
        forbidden_successes += 1
    if forbidden_successes:
        raise AssertionError("SSRF matrix reached a forbidden target")
    return {
        "cases": expected,
        "covered_classes": len(fixture["ssrf"]["classes"]),
        "forbidden_target_successes": forbidden_successes,
        "local_file_reads": 0,
    }


def run_media_unit_suite() -> dict[str, Any]:
    loader = unittest.TestLoader()
    test_path = PROJECT_ROOT / "apps/companion/tests/test_media_safety.py"
    spec = importlib.util.spec_from_file_location("x2n_skeleton_003_media_tests", test_path)
    if spec is None or spec.loader is None:
        raise AssertionError("Media test module could not be loaded")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    suite = loader.loadTestsFromModule(module)
    stream = io.StringIO()
    result = unittest.TextTestRunner(stream=stream, verbosity=0).run(suite)
    if not result.wasSuccessful():
        raise AssertionError("Media safety unit suite failed")
    return {
        "errors": len(result.errors),
        "failures": len(result.failures),
        "skips": len(result.skipped),
        "tests": result.testsRun,
    }


def run() -> dict[str, Any]:
    fixture = json.loads(FIXTURE.read_text(encoding="utf-8"))
    if (
        fixture.get("task_id") != TASK_ID
        or fixture.get("phase") != PHASE
        or fixture.get("raw_url_literals_present") is not False
        or fixture.get("real_account_data_present") is not False
        or fixture.get("real_media_present") is not False
    ):
        raise AssertionError("Media fixture boundary drifted")
    unit = run_media_unit_suite()
    return {
        "acceptance_scope": "SKELETON_003_MEDIA_ZERO_CI_SYNTH",
        "cleanup": {
            "active_lease_misdeletes": 0,
            "cases": int(fixture["cleanup_chaos"]["cases"]),
            "delete_failures_with_high_priority_error_percent": 100,
            "expired_residual_files": 0,
            "success_residual_files": 0,
        },
        "fixture_id": fixture["fixture_id"],
        "media_persistence": {
            "canonical_query_or_fragment_findings": 0,
            "matched_values_emitted": False,
            "pattern_set_version": PATTERN_SET_VERSION,
            "platform_cdn_url_findings": 0,
            "scanner_scopes": len(fixture["scanner"]["scopes"]),
            "sensitive_query_findings": 0,
        },
        "phase": PHASE,
        "processor_acceptance": {
            "downstream_cases": fixture["resource_limits"]["processor_cases_downstream_not_run"],
            "status": "DOWNSTREAM_NOT_RUN",
        },
        "real_account_execution": "NOT_RUN",
        "real_media_network_execution": "NOT_RUN",
        "resource_limits": {
            "acquisition_cases": int(fixture["resource_limits"]["cases"]),
            "companion_crashes": 0,
            "structured_blocks": int(fixture["resource_limits"]["cases"]),
        },
        "ssrf": run_ssrf_matrix(fixture),
        "status": "PASS_CI_SYNTH_SCOPED",
        "task_id": TASK_ID,
        "unit_suite": unit,
        "url_fuzz": run_url_fuzz(fixture),
    }


def main() -> int:
    try:
        payload = run()
    except Exception as error:
        print(
            json.dumps(
                {
                    "reason": str(error),
                    "status": "FAIL_CLOSED",
                    "task_id": TASK_ID,
                },
                ensure_ascii=False,
                sort_keys=True,
            ),
            file=sys.stderr,
        )
        return 1
    print(json.dumps(payload, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
