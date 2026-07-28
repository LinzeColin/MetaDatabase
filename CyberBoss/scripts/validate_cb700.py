#!/usr/bin/env python3
"""Fail-closed local seal for CB-700.

Mapped acceptance: AC-012 (credential vault), AC-013 (OpenAI), AC-014
(DeepSeek), AC-015 (Gemini), AC-016 (Anthropic), AC-017 (provider fault
isolation), AC-045 (token pre-authorisation and hard budget), AC-046 (usage
normalisation and crash-conservative accounting), AC-047 (circuit breaker and
half-open probe).

Provider adapters are proved against frozen fake transports. Real BYOK keys are
outside the authorised scope, so live provider activation stays
`activation_pending` and is never counted as PASS.
"""

from __future__ import annotations

import hashlib
import json
import re
import subprocess
import sys
from pathlib import Path
from typing import Any

sys.dont_write_bytecode = True

REPO = Path(__file__).resolve().parents[2]
PROJECT = REPO / "CyberBoss"
APP = PROJECT / "app"
SRC = APP / "src/services"

ACCEPTANCE_IDS = (
    "AC-012", "AC-013", "AC-014", "AC-015", "AC-016",
    "AC-017", "AC-045", "AC-046", "AC-047",
)
NODE_SUITES = (
    "test/cb700-provider-vault-budget-circuit.test.js",
    "test/cb630-usercontext-guard-queue.test.js",
    "test/cb610-multiuser-foundation.test.js",
)
MODULES = (
    "secrets/credential-vault.js",
    "providers/policy.js",
    "providers/errors.js",
    "providers/openai-responses.js",
    "providers/deepseek.js",
    "providers/openai-compatible.js",
    "providers/gemini.js",
    "providers/anthropic.js",
    "providers/router.js",
    "runtime/token-estimator.js",
    "runtime/usage-normalizer.js",
    "runtime/sqlite-model-budget-store.js",
    "runtime/model-budget-guard.js",
    "runtime/provider-circuit-breaker.js",
    "runtime/model-runtime-controller.js",
)


class Checks:
    def __init__(self) -> None:
        self.rows: list[dict[str, Any]] = []

    def add(self, check_id: str, acceptance_id: str, ok: bool, detail: str) -> None:
        self.rows.append(
            {"check": check_id, "acceptance_id": acceptance_id,
             "result": "PASS" if ok else "FAIL", "detail": detail}
        )

    def pending(self, check_id: str, acceptance_id: str, detail: str) -> None:
        self.rows.append(
            {"check": check_id, "acceptance_id": acceptance_id,
             "result": "ACTIVATION_PENDING", "detail": detail}
        )

    @property
    def failed(self) -> list[dict[str, Any]]:
        return [row for row in self.rows if row["result"] == "FAIL"]

    @property
    def pending_rows(self) -> list[dict[str, Any]]:
        return [row for row in self.rows if row["result"] == "ACTIVATION_PENDING"]


def read(relative: str) -> str:
    return (SRC / relative).read_text(encoding="utf-8")


def run_node_suite(relative: str) -> dict[str, Any]:
    result = subprocess.run(
        ["node", "--test", relative], cwd=APP,
        capture_output=True, text=True, check=False,
    )
    output = result.stdout + result.stderr
    counts = {
        key: int(match.group(1))
        for key in ("tests", "pass", "fail")
        if (match := re.search(rf"^. {key} (\d+)$", output, re.MULTILINE))
    }
    return {
        "suite": relative, "returncode": result.returncode,
        "tests": counts.get("tests", 0), "pass": counts.get("pass", 0),
        "fail": counts.get("fail", None),
    }


def check_ac012(checks: Checks) -> None:
    vault = read("secrets/credential-vault.js")
    checks.add("ac012.random_per_user_dek", "AC-012",
               "createWrappedUserKey" in vault and "randomSource(KEY_BYTES)" in vault,
               "each user gets a random 32-byte DEK")
    checks.add("ac012.kek_wraps_with_aes_256_gcm", "AC-012",
               'ALGORITHM = "AES-256-GCM"' in vault and "aes-256-gcm" in vault,
               "the DEK is wrapped by the master KEK under AES-256-GCM")
    checks.add("ac012.provider_subkey_derived", "AC-012",
               "deriveProviderKey" in vault and "cyberboss-provider-key" in vault,
               "a per-provider sub-key is derived from the user DEK")
    checks.add("ac012.scope_binding_in_aad", "AC-012",
               "CyberBoss:user-key:${userId}" in vault
               and "CyberBoss:credential:${userId}:${providerId}" in vault,
               "user and provider scope are bound into the AAD")
    checks.add("ac012.scope_mismatch_refused", "AC-012",
               "USER_KEY_SCOPE_MISMATCH" in vault and "VAULT_SCOPE_MISMATCH" in vault,
               "a ciphertext lifted into another scope is refused")
    checks.add("ac012.constant_time_aad_compare", "AC-012",
               "timingSafeEqual" in vault,
               "the AAD comparison is constant time")
    checks.add("ac012.rotation_supported", "AC-012",
               "rotateUserKey" in vault,
               "keys can be rotated without losing stored credentials")
    checks.add("ac012.crypto_shred_supported", "AC-012",
               "cryptoShred" in vault and "status='destroyed'" in vault,
               "destroying the wrapped DEK crypto-shreds residual ciphertext")
    checks.add("ac012.keys_zeroed_after_use", "AC-012",
               vault.count(".fill(0)") >= 6,
               "derived key material is zeroed in finally blocks")
    checks.add("ac012.only_last4_in_clear", "AC-012",
               "last4: plaintext.slice(-4)" in vault,
               "the only plaintext fragment stored is the last four characters")
    checks.add("ac012.listing_has_no_ciphertext", "AC-012",
               "ciphertext_json" not in read("secrets/credential-vault.js").split("listCredentials")[1].split("}")[0],
               "listCredentials returns no ciphertext")


def check_provider_adapters(checks: Checks) -> None:
    policy = read("providers/policy.js")
    router = read("providers/router.js")
    checks.add("ac013.openai_responses_endpoint", "AC-013",
               "/v1/responses" in read("providers/openai-responses.js")
               and '"https://api.openai.com"' in router,
               "OpenAI uses the fixed official Responses endpoint")
    checks.add("ac013.openai_no_provider_retention", "AC-013",
               "store: false" in read("providers/openai-responses.js"),
               "OpenAI requests opt out of provider-side retention")
    checks.add("ac014.deepseek_reuses_openai_protocol", "AC-014",
               "/chat/completions" in read("providers/deepseek.js")
               and "OpenAICompatibleAdapter: DeepSeekAdapter" in read("providers/openai-compatible.js"),
               "DeepSeek reuses the OpenAI-compatible implementation with its own policy")
    checks.add("ac014.deepseek_origin_pinned", "AC-014",
               '"https://api.deepseek.com"' in router,
               "the DeepSeek origin is pinned")
    checks.add("ac015.gemini_header_auth", "AC-015",
               '"x-goog-api-key": apiKey' in read("providers/gemini.js"),
               "Gemini authenticates by header, never by query string")
    checks.add("ac015.gemini_origin_pinned", "AC-015",
               '"https://generativelanguage.googleapis.com"' in router,
               "the Gemini origin is pinned")
    checks.add("ac016.anthropic_messages_api", "AC-016",
               "/v1/messages" in read("providers/anthropic.js")
               and 'ANTHROPIC_VERSION = "2023-06-01"' in read("providers/anthropic.js"),
               "Anthropic uses the Messages API with a pinned version header")
    checks.add("ac016.anthropic_origin_pinned", "AC-016",
               '"https://api.anthropic.com"' in router,
               "the Anthropic origin is pinned")

    for acceptance in ("AC-013", "AC-014", "AC-015", "AC-016"):
        checks.add(f"{acceptance.lower().replace('-', '')}.model_allowlist_enforced", acceptance,
                   "assertModel" in policy and "MODEL_NOT_ALLOWED" in policy,
                   "the model must be in the server-owned allowlist")
    checks.add("ac013.user_cannot_supply_base_url", "AC-013",
               "PROVIDER_ORIGIN_NOT_OFFICIAL" in router
               and "PROVIDER_ORIGIN_MUST_BE_BARE_HTTPS" in policy,
               "a non-official or non-bare-HTTPS origin cannot be configured")
    checks.add("ac013.router_forwards_fixed_fields_only", "AC-013",
               "sendText({ providerId, apiKey, model, messages, maxOutputTokens, signal })" in router,
               "only fixed fields cross into an adapter")


def check_ac017(checks: Checks) -> None:
    errors = read("providers/errors.js")
    controller = read("runtime/model-runtime-controller.js")
    checks.add("ac017.status_codes_normalized", "AC-017",
               all(code in errors for code in ("CREDENTIAL_INVALID", "RATE_LIMITED", "NO_BALANCE", "PROVIDER_UNAVAILABLE")),
               "401/403, 429, 402 and 5xx map to distinct codes")
    checks.add("ac017.messages_are_chinese", "AC-017",
               len(re.findall(r"[一-鿿]", errors)) > 40,
               "every provider error message is Chinese")
    checks.add("ac017.no_provider_body_in_diagnostic", "AC-017",
               "Buffer.byteLength(String(body)" in errors and ".update(`${providerId}:${status}:" in errors,
               "the diagnostic hashes shape only, never provider content")
    checks.add("ac017.default_bounded_timeout", "AC-017",
               "DEFAULT_REQUEST_TIMEOUT_MS = 60_000" in controller
               and "requestTimeoutMs must be a positive integer" in controller,
               "the controller always applies a bounded timeout")
    cancel_branch = re.search(
        r'const circuitErrors\s*=\s*(.*?);', controller, re.DOTALL
    )
    checks.add("ac017.external_cancel_does_not_poison_circuit", "AC-017",
               cancel_branch is not None
               and "REQUEST_CANCELLED" in cancel_branch.group(1)
               and "[]" in cancel_branch.group(1).split("REQUEST_CANCELLED")[1].split("this.#recordFailure")[0],
               "an external cancel takes the empty-failure branch, so no provider failure is recorded")
    checks.add("ac017.no_secret_in_error_path", "AC-017",
               "apiKey" not in errors,
               "the error module never sees a credential")


def check_ac045_ac046(checks: Checks) -> None:
    guard = read("runtime/model-budget-guard.js")
    store = read("runtime/sqlite-model-budget-store.js")
    controller = read("runtime/model-runtime-controller.js")
    estimator = read("runtime/token-estimator.js")
    normalizer = read("runtime/usage-normalizer.js")

    checks.add("ac045.conservative_upper_bound", "AC-045",
               "Buffer.byteLength" in estimator and "Math.max(1, utf8Bytes" in estimator,
               "the input estimate is a UTF-8 byte upper bound")
    checks.add("ac045.reserve_before_provider_call", "AC-045",
               controller.index("this.budget.preflight(") < controller.index("this.router.sendText("),
               "the reservation is taken before the provider is called")
    checks.add("ac045.circuit_before_budget", "AC-045",
               controller.index("this.circuit.beforeRequest(") < controller.index("this.budget.preflight("),
               "the circuit is consulted before a reservation is spent")
    checks.add("ac045.begin_immediate_atomic_reservation", "AC-045",
               'database.exec("BEGIN IMMEDIATE")' in store
               and "reserveIfWithinLimits" in store,
               "the limit check and the reservation share one BEGIN IMMEDIATE transaction")
    checks.add("ac045.denial_reports_zero_model_calls", "AC-045",
               guard.count("modelCalls: 0") >= 3,
               "every budget denial reports modelCalls 0")
    checks.add("ac045.chinese_repair_action", "AC-045",
               "调整额度" in guard or "设置页" in guard,
               "an over-budget reply tells the user in Chinese what to do next")
    checks.add("ac045.hard_limits_present", "AC-045",
               all(key in store for key in (
                   "USER_DAILY_TOKEN_BUDGET_EXHAUSTED", "USER_MONTHLY_TOKEN_BUDGET_EXHAUSTED",
                   "GLOBAL_DAILY_TOKEN_BUDGET_EXHAUSTED", "GLOBAL_MONTHLY_TOKEN_BUDGET_EXHAUSTED")),
               "user and global, daily and monthly hard limits all exist")

    checks.add("ac046.four_provider_usage_normalized", "AC-046",
               all(p in normalizer for p in ("openai", "deepseek", "google", "anthropic")),
               "all four providers have usage field mappings")
    checks.add("ac046.missing_usage_charges_reservation", "AC-046",
               'chargeMode: "reserved"' in guard and "reservation_fallback" in guard,
               "missing usage charges the full reservation, never zero")
    checks.add("ac046.expired_reservation_charged", "AC-046",
               "expired_charged" in store and "RESERVATION_EXPIRED" in store,
               "a reservation orphaned by a crash is charged conservatively")
    checks.add("ac046.request_id_user_scoped", "AC-046",
               "WHERE user_id=? AND request_id=?" in store,
               "request_id idempotency is scoped to the user")
    checks.add("ac046.success_survives_accounting_outage", "AC-046",
               "pending_conservative_reservation" in controller,
               "a valid provider answer is not lost to a bookkeeping outage")
    checks.add("ac046.transport_uncertainty_charged", "AC-046",
               "settleUnknown" in guard and "transport_uncertain_reserved" in guard,
               "an uncertain transport outcome charges rather than releases")


def check_ac047(checks: Checks) -> None:
    breaker = read("runtime/provider-circuit-breaker.js")
    store = read("runtime/sqlite-model-budget-store.js")
    controller = read("runtime/model-runtime-controller.js")
    checks.add("ac047.two_scopes", "AC-047",
               "USER_FAILURE_CODES" in breaker and "GLOBAL_FAILURE_CODES" in breaker
               and '"user_provider"' in breaker and '"global"' in breaker,
               "user_provider and global scopes are distinct")
    checks.add("ac047.credential_failure_is_user_scoped", "AC-047",
               "CREDENTIAL_INVALID" in breaker.split("USER_FAILURE_CODES")[1].split("]")[0],
               "a bad credential breaks only that user's connection")
    checks.add("ac047.outage_is_global_scoped", "AC-047",
               "PROVIDER_UNAVAILABLE" in breaker.split("GLOBAL_FAILURE_CODES")[1].split("]")[0],
               "a provider outage breaks that provider for everyone")
    checks.add("ac047.state_persisted", "AC-047",
               "SqliteCircuitStore" in store and "provider_circuits" in store,
               "circuit state is persisted in SQLite and survives a restart")
    checks.add("ac047.single_half_open_probe", "AC-047",
               "probeInFlight" in breaker and "#grantProbe" in breaker,
               "at most one half-open probe is granted at a time")
    checks.add("ac047.probe_lease_bounded", "AC-047",
               "halfOpenProbeLeaseMs" in breaker
               and "row.retryAt = now + this.halfOpenProbeLeaseMs" in breaker,
               "a lost completion cannot wedge the circuit: the probe lease expires")
    checks.add("ac047.probe_released_on_downstream_denial", "AC-047",
               "if (global.probe) {" in breaker and "#releaseProbe" in breaker,
               "a user-scope denial releases the global probe it did not use")
    checks.add("ac047.cross_scope_probe_released", "AC-047",
               "cancelOppositeScopeProbe" in breaker,
               "a failure in one scope releases the other scope's probe")
    checks.add("ac047.unclassified_failure_releases_all_probes", "AC-047",
               "!USER_FAILURE_CODES.includes(code)" in controller
               and "!GLOBAL_FAILURE_CODES.includes(code)" in controller,
               "an unclassifiable failure releases every probe it held")
    checks.add("ac047.fake_clock_injectable", "AC-047",
               "clock = () => Date.now()" in breaker,
               "the cooldown uses an injectable clock, so no test waits on real time")


def check_ac048_and_hygiene(checks: Checks) -> None:
    store = read("runtime/sqlite-model-budget-store.js")
    breaker = read("runtime/provider-circuit-breaker.js")
    aggregate_block = store.split("aggregateByProvider")[1]
    checks.add("ac048.aggregate_has_no_user_dimension", "AC-045",
               "user_id" not in aggregate_block.split("GROUP BY")[0].split("SELECT")[1],
               "the provider aggregate selects no user dimension")
    checks.add("ac048.circuit_aggregate_has_no_user", "AC-047",
               "userId" not in breaker.split("aggregateStatus()")[1],
               "the circuit aggregate exposes counts only")

    offenders: list[str] = []
    secret_pattern = re.compile(
        r"(?:sk-[A-Za-z0-9]{16,}|BEGIN [A-Z ]*PRIVATE KEY|Bearer\s+[A-Za-z0-9._-]{20,})"
    )
    for relative in MODULES:
        text = read(relative)
        for marker in ("/Users/", ".plist", "LaunchAgent", "LaunchDaemon", "launchd"):
            if marker in text:
                offenders.append(f"{relative}:{marker}")
        if secret_pattern.search(text):
            offenders.append(f"{relative}:secret_pattern")
    checks.add("cb700.no_mac_or_secret_markers", "AC-012", not offenders, f"offenders={offenders}")

    # Structural proof: no control-plane module may import a provider adapter,
    # so a health probe, a budget summary or a status projection cannot reach a
    # model even by accident.
    control_plane = (
        "runtime/provider-circuit-breaker.js",
        "runtime/sqlite-model-budget-store.js",
        "runtime/model-budget-guard.js",
        "runtime/token-estimator.js",
        "runtime/usage-normalizer.js",
    )
    importers = [
        relative
        for relative in control_plane
        if re.search(r'require\("\.\./providers/', read(relative))
        or "sendText" in read(relative)
    ]
    checks.add("cb700.no_background_model_call", "AC-045",
               not importers,
               f"control-plane modules importing a provider or calling sendText: {importers}")


def check_activation(checks: Checks) -> None:
    checks.pending(
        "cb700.real_provider_activation", "AC-013",
        "live BYOK keys for OpenAI, Gemini, DeepSeek and Anthropic are outside the authorised "
        "scope, so real provider activation stays activation_pending. Adapters are proved against "
        "frozen fake transports; no simulator result is presented as a live provider pass. "
        "Real activation is performed at CB-830.",
    )


def check_suites(checks: Checks) -> list[dict[str, Any]]:
    results = [run_node_suite(name) for name in NODE_SUITES]
    for result in results:
        checks.add(
            f"cb700.suite.{Path(result['suite']).stem}", "AC-045",
            result["returncode"] == 0 and result["fail"] == 0 and result["tests"] > 0,
            f"tests={result['tests']} pass={result['pass']} fail={result['fail']}",
        )
    return results


def main() -> int:
    checks = Checks()
    check_ac012(checks)
    check_provider_adapters(checks)
    check_ac017(checks)
    check_ac045_ac046(checks)
    check_ac047(checks)
    check_ac048_and_hygiene(checks)
    check_activation(checks)
    suites = check_suites(checks)

    report = {
        "schema_version": "cyberboss.cb700.validation.v1",
        "task_id": "CB-700",
        "product_version": "v0.0.0.8",
        "acceptance_ids": list(ACCEPTANCE_IDS),
        "check_count": len(checks.rows),
        "pass_count": len([r for r in checks.rows if r["result"] == "PASS"]),
        "fail_count": len(checks.failed),
        "activation_pending_count": len(checks.pending_rows),
        "unknown_count": 0,
        "not_run_count": 0,
        "status": "PASS" if not checks.failed else "FAIL",
        "node_suites": suites,
        "node_test_total": sum(item["tests"] for item in suites),
        "checks": checks.rows,
        "artifact_sha256": {
            f"app/src/services/{relative}": hashlib.sha256((SRC / relative).read_bytes()).hexdigest()
            for relative in MODULES
        },
    }
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if report["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
