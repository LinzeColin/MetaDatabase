#!/usr/bin/env python3
"""Fail-closed local seal for CB-620 (AC-004 registration/consent, AC-010
one-time setup link, AC-011 web session security, AC-028 cross-device
continuity, AC-041 invite and suspension).

UNKNOWN and NOT_RUN are never folded into PASS.
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

ACCEPTANCE_IDS = ("AC-004", "AC-010", "AC-011", "AC-028", "AC-041")
NODE_SUITES = (
    "test/cb620-registration-consent-portal.test.js",
    "test/cb610-multiuser-foundation.test.js",
)
MODULES = (
    "users/onboarding-state.js",
    "users/registration-service.js",
    "users/invite-code-store.js",
    "security/setup-token-service.js",
    "security/session-token-service.js",
    "security/secure-setup-link.js",
    "portal/setup-portal.js",
)


class Checks:
    def __init__(self) -> None:
        self.rows: list[dict[str, Any]] = []

    def add(self, check_id: str, acceptance_id: str, ok: bool, detail: str) -> None:
        self.rows.append(
            {
                "check": check_id,
                "acceptance_id": acceptance_id,
                "result": "PASS" if ok else "FAIL",
                "detail": detail,
            }
        )

    @property
    def failed(self) -> list[dict[str, Any]]:
        return [row for row in self.rows if row["result"] != "PASS"]


def read(relative: str) -> str:
    return (SRC / relative).read_text(encoding="utf-8")


def run_node_suite(relative: str) -> dict[str, Any]:
    result = subprocess.run(
        ["node", "--test", relative],
        cwd=APP,
        capture_output=True,
        text=True,
        check=False,
    )
    output = result.stdout + result.stderr
    counts = {
        key: int(match.group(1))
        for key in ("tests", "pass", "fail")
        if (match := re.search(rf"^. {key} (\d+)$", output, re.MULTILINE))
    }
    return {
        "suite": relative,
        "returncode": result.returncode,
        "tests": counts.get("tests", 0),
        "pass": counts.get("pass", 0),
        "fail": counts.get("fail", None),
    }


def check_ac004(checks: Checks) -> None:
    onboarding = read("users/onboarding-state.js")
    registration = read("users/registration-service.js")

    checks.add(
        "ac004.frozen_chinese_commands",
        "AC-004",
        'START: "开始"' in onboarding and 'CONSENT: "同意并开始"' in onboarding,
        "「开始」 and 「同意并开始」 are the frozen entry commands",
    )
    checks.add(
        "ac004.start_only_creates_pending",
        "AC-004",
        "ensurePending" in registration
        and "activateConsent" in registration
        and registration.index("ensurePending") < registration.index("activateConsent"),
        "start() reaches ensurePending; only consent() reaches activateConsent",
    )
    checks.add(
        "ac004.consent_is_the_only_activation",
        "AC-004",
        registration.count("activateConsent(") == 1,
        "exactly one activation call site exists",
    )
    outcome_block = registration.split("const STATE_OUTCOME")[1].split("});")[0]
    pre_active = [
        state
        for state in ("unseen", "pending_invite", "pending_consent", "suspended")
        if re.search(rf"{state}:[^\n]*modelCalls: 0", outcome_block)
    ]
    checks.add(
        "ac004.pre_active_model_calls_zero",
        "AC-004",
        len(pre_active) == 4
        and re.search(r"active:[^\n]*modelCalls: null", outcome_block) is not None,
        f"states_declaring_zero={pre_active}",
    )
    checks.add(
        "ac004.reducer_has_no_imports",
        "AC-004",
        "require(" not in onboarding,
        "the onboarding reducer imports nothing, so it cannot reach a provider",
    )


def check_ac010(checks: Checks) -> None:
    setup = read("security/setup-token-service.js")
    link = read("security/secure-setup-link.js")

    checks.add(
        "ac010.ttl_is_ten_minutes",
        "AC-010",
        "DEFAULT_TTL_MS = 10 * 60 * 1000" in setup
        and "MAX_TTL_MS = 10 * 60 * 1000" in setup,
        "the setup token TTL is 10 minutes and cannot be raised",
    )
    checks.add(
        "ac010.hash_storage_only",
        "AC-010",
        "createHash(\"sha256\")" in setup and "token_hash" in setup,
        "only the SHA-256 hash of the token is stored",
    )
    checks.add(
        "ac010.single_use_atomic",
        "AC-010",
        "BEGIN IMMEDIATE" in setup
        and "used_at IS NULL" in setup
        and "LINK_INVALID" in setup,
        "consumption is atomic and a second use is refused",
    )
    checks.add(
        "ac010.expiry_refused",
        "AC-010",
        "LINK_EXPIRED" in setup,
        "an expired link is refused with its own code",
    )
    checks.add(
        "ac010.token_not_in_request_target",
        "AC-010",
        "url.hash =" in link and "tokenAppearsInRequestTarget" in link,
        "the token travels in the fragment, never the path or query",
    )
    checks.add(
        "ac010.https_origin_required",
        "AC-010",
        "HTTPS_ORIGIN_REQUIRED" in link,
        "a non-HTTPS origin cannot produce a setup link",
    )


def check_ac011(checks: Checks) -> None:
    session = read("security/session-token-service.js")
    portal = read("portal/setup-portal.js")

    for attribute in ("HttpOnly", "Secure", "SameSite=Strict"):
        checks.add(
            f"ac011.cookie_{attribute.split('=')[0].lower()}",
            "AC-011",
            f'"{attribute}"' in session,
            f"session cookie sets {attribute}",
        )
    checks.add(
        "ac011.exact_https_origin_allowlist",
        "AC-011",
        "this.allowedOrigins.includes(origin)" in portal
        and "requireHttpsOrigin" in portal,
        "origins are compared by exact match against an HTTPS allowlist",
    )
    checks.add(
        "ac011.host_allowlist",
        "AC-011",
        "HOST_NOT_ALLOWED" in portal and "this.allowedHosts.includes(host)" in portal,
        "the Host header must match the allowlist",
    )
    checks.add(
        "ac011.csrf_required",
        "AC-011",
        "CSRF_INVALID" in session and "requireCsrf: true" in portal,
        "mutating portal requests require a matching CSRF token",
    )
    checks.add(
        "ac011.server_owned_session_user",
        "AC-011",
        "session.userId" in portal and "USER_SCOPE_VIOLATION" in portal,
        "the acting user comes from the session row; a body claim is refused",
    )
    checks.add(
        "ac011.frozen_action_allowlist",
        "AC-011",
        "ACTION_ALLOWLIST" in portal and "ACTION_NOT_ALLOWED" in portal,
        "only frozen allowlisted actions reach a handler",
    )
    checks.add(
        "ac011.body_limit_16kib",
        "AC-011",
        "MAX_BODY_BYTES = 16 * 1024" in portal and "BODY_TOO_LARGE" in portal,
        "the request body is capped at 16 KiB",
    )
    checks.add(
        "ac011.body_size_checked_before_parse",
        "AC-011",
        portal.index("this.#assertBodySize(body)") < portal.index("this.#parseBody(body)"),
        "an oversized body is rejected before it is parsed",
    )
    checks.add(
        "ac011.global_revocation_from_wechat",
        "AC-011",
        "revokeAllForUser" in session and "revokeEverythingForUser" in portal,
        "one command revokes every session and outstanding setup link",
    )
    checks.add(
        "ac011.constant_time_csrf_compare",
        "AC-011",
        "timingSafeEqual" in session,
        "the CSRF comparison is constant time",
    )
    checks.add(
        "ac011.no_owner_capability_in_allowlist",
        "AC-011",
        not any(
            token in portal.split("ACTION_ALLOWLIST")[1].split("]")[0]
            for token in ("shell", "codex", "workspace", "exec")
        ),
        "no Owner-only capability is reachable from the portal allowlist",
    )


def check_ac028(checks: Checks) -> None:
    registration = read("users/registration-service.js")
    repository = read("users/user-repository.js")

    checks.add(
        "ac028.principal_resolves_existing_user",
        "AC-028",
        "resolveByPrincipal" in registration and "resumed: true" in registration,
        "a returning principal resumes its existing user rather than creating one",
    )
    checks.add(
        "ac028.no_second_account_system",
        "AC-028",
        "email" not in repository.lower() and "password" not in repository.lower(),
        "no email or password account system exists",
    )
    checks.add(
        "ac028.identity_is_channel_principal_only",
        "AC-028",
        "user_channels" in repository and "bot_account_ref" in repository,
        "identity is the WeChat bot account plus sender, nothing else",
    )


def check_ac041(checks: Checks) -> None:
    invite = read("users/invite-code-store.js")
    registration = read("users/registration-service.js")
    repository = read("users/user-repository.js")

    checks.add(
        "ac041.unknown_sender_pending_only",
        "AC-041",
        "REQUEST_INVITE" in registration and "pending_consent" in repository,
        "an unknown sender reaches only the minimal pending state",
    )
    checks.add(
        "ac041.invite_keyed_hash",
        "AC-041",
        "createHmac" in invite and "cyberboss-invite-code" in invite,
        "invite codes are stored as an HMAC-SHA256 keyed hash",
    )
    checks.add(
        "ac041.invite_min_length_12",
        "AC-041",
        "MIN_CODE_LENGTH = 12" in invite and "{12,32}" in invite,
        "invite codes are at least 12 characters",
    )
    checks.add(
        "ac041.invite_bounded_uses",
        "AC-041",
        "used_count < max_uses" in invite and "MAX_USES = 20" in invite,
        "uses are bounded and enforced atomically",
    )
    checks.add(
        "ac041.invite_revocable",
        "AC-041",
        "disabled_at" in invite and "revoke(" in invite,
        "an invite can be revoked",
    )
    checks.add(
        "ac041.invite_consumed_before_user_created",
        "AC-041",
        registration.index("this.invites.consume(inviteCode)")
        < registration.index("this.users.ensurePending"),
        "an invalid code creates no user row",
    )
    checks.add(
        "ac041.suspended_and_pending_block_model",
        "AC-041",
        'MODEL_ELIGIBLE_STATUSES = Object.freeze(["active"])' in repository,
        "only an active user may reach a model",
    )


def check_hygiene(checks: Checks) -> None:
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
    checks.add(
        "cb620.no_mac_or_secret_markers",
        "AC-011",
        not offenders,
        f"offenders={offenders}",
    )
    checks.add(
        "cb620.no_model_dependency_in_auth_path",
        "AC-004",
        not any(
            token in read(relative)
            for relative in MODULES
            for token in ("openai", "anthropic", "gemini", "deepseek", "llm", "completion(")
        ),
        "no authentication or onboarding module reaches a model provider",
    )


def check_suites(checks: Checks) -> list[dict[str, Any]]:
    results = [run_node_suite(name) for name in NODE_SUITES]
    for result in results:
        checks.add(
            f"cb620.suite.{Path(result['suite']).stem}",
            "AC-004",
            result["returncode"] == 0 and result["fail"] == 0 and result["tests"] > 0,
            f"tests={result['tests']} pass={result['pass']} fail={result['fail']}",
        )
    return results


def main() -> int:
    checks = Checks()
    check_ac004(checks)
    check_ac010(checks)
    check_ac011(checks)
    check_ac028(checks)
    check_ac041(checks)
    check_hygiene(checks)
    suites = check_suites(checks)

    report = {
        "schema_version": "cyberboss.cb620.validation.v1",
        "task_id": "CB-620",
        "product_version": "v0.0.0.8",
        "acceptance_ids": list(ACCEPTANCE_IDS),
        "check_count": len(checks.rows),
        "pass_count": len(checks.rows) - len(checks.failed),
        "fail_count": len(checks.failed),
        "unknown_count": 0,
        "not_run_count": 0,
        "status": "PASS" if not checks.failed else "FAIL",
        "node_suites": suites,
        "node_test_total": sum(item["tests"] for item in suites),
        "checks": checks.rows,
        "artifact_sha256": {
            f"app/src/services/{relative}": hashlib.sha256(
                (SRC / relative).read_bytes()
            ).hexdigest()
            for relative in MODULES
        },
    }
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if report["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
