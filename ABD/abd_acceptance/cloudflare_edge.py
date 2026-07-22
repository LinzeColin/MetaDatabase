from __future__ import annotations

import hashlib
import json
import re
import shutil
import subprocess
import tempfile
import xml.etree.ElementTree as ET
from copy import deepcopy
from html.parser import HTMLParser
from pathlib import Path
from typing import Any, Dict, List, Mapping, MutableMapping, Sequence
from urllib.parse import urlsplit

from .canonical_facts import DuplicateKeyError, sha256_file, strict_json_load
from .infrastructure_iac import verify_existing_phase_evidence as verify_infrastructure_iac_evidence
from .stage3_delivery import (
    PINNED_RECEIPT_SHA256 as STAGE3_DELIVERY_RECEIPT_SHA256,
    RECEIPT_PATH as STAGE3_DELIVERY_RECEIPT_PATH,
)


CONTRACT_ID = "AC-S04-P02"
REQUIREMENT_ID = "REQ-S04-P02"
STAGE_ID = "S04"
PHASE_ID = "P02"
VERSION = "0.0.0.1"
FIXED_CLOCK = "2026-07-22T20:00:00+10:00"
JUNIT_FIXED_CLOCK = "2026-07-19T00:00:00+10:00"

CONFIG_PATH = Path("infra/cloudflared.yml")
POLICY_PATH = Path("access_policy.md")
DEGRADED_PAGE_PATH = Path("degraded_page.html")
FIXTURE_PATH = Path("machine/tests/fixtures/S04_P02.json")
TEST_PATH = Path("tests/S04/P02_test.py")
JUNIT_PATH = Path("machine/evidence/S04/P02/pytest.xml")
FULL_JUNIT_PATH = Path("machine/evidence/S04/P02/full_regression.xml")
PACK_REPORT_PATH = Path("machine/evidence/validation_report.json")
SCAN_REPORT_PATH = Path("machine/evidence/S00/P03/paid_dependency_scan.txt")
P01_EVIDENCE_PATH = Path("machine/evidence/EVD-S04-P01.json")
P01_ROLLBACK_PATH = Path("machine/evidence/EVD-S04-P01_rollback.json")
EVIDENCE_PATH = Path("machine/evidence/EVD-S04-P02.json")
ROLLBACK_EVIDENCE_PATH = Path("machine/evidence/EVD-S04-P02_rollback.json")
EVIDENCE_INDEX_PATH = Path("machine/evidence/evidence_index.jsonl")
WORKFLOW_PATH = Path(".github/workflows/abd-stage0-validation.yml")

PLACEHOLDER_TUNNEL_ID = "00000000-0000-4000-8000-000000000000"
PLACEHOLDER_HOSTNAME = "abd.example.invalid"
OWNER_PLACEHOLDER = "${ABD_OWNER_EMAIL}"
ALLOWED_NUMERIC_BOUNDARY_DELTAS = {"-0.0001", "0", "0.0001"}

STRUCTURAL_SELF_NORMALIZED_SHA256 = "e6c9aa9a344269b1a2754c5d124503311d33f043968a963ccbfcb5f7c2532e32"
PHASE_COMMIT = "52e85f6626cde511c9b9679e126cfb536d612ddd"
PINNED_PHASE_CODE_HASH = "e30dbd30561188059b1cf7d528f5651d95f3cc7065c82de05644d56ea40a45a4"
SUCCESSOR_EVOLVABLE_SIGNED_INPUTS = {
    "abd_acceptance/cloudflare_edge.py",
    "tests/S04/P02_test.py",
}
SUCCESSOR_UNIT_PROFILE_HASHES: Dict[str, str] = {
    "tests/S04/P02_test.py": "003b56b6a4706e58894123229d3c34933d3b516f9f1e8bee654d372e8eaf2a86",
}
PINNED_PHASE_HASHES: Dict[str, str] = {
    CONFIG_PATH.as_posix(): "7f3855b637a020b3769d93bcbaa2539a692ab6eec314a8b722d29c6e0f5118f1",
    POLICY_PATH.as_posix(): "2fcbaaaaecdfc361d695caad6c1924cfaaa9ceb98538cb5c2f7c1930af99bbc7",
    DEGRADED_PAGE_PATH.as_posix(): "29c49f3388f8b7214c1d75869ebc2c8434d502972cb74a2883595c10d89f6b40",
    FIXTURE_PATH.as_posix(): "1bb8196810d33b9947d6b2988c07936eff8198743af5663ca9b8cd6b8e25dbff",
    TEST_PATH.as_posix(): "3046bb914d4a8482bd29936fd6f3e08ac5f91ebd7f8109f1829c39a507fb01a4",
}
PINNED_BASELINE_HASHES: Dict[str, str] = {
    "machine/facts/canonical_facts.json": "f7008c057f317c704daca041e1f85c81c1f77b23dcdd70d38ce828aca8000385",
    "machine/facts/costs.json": "bf753ab094133102b31496f8f05150883b8fce94aaf6927ff85bfbf5a37d0e65",
    "machine/facts/parameters.json": "ac8dc796247fe4b0074e5ccb722af9661c0228f13cbd44c9ffda2d8d3804d63d",
    "machine/facts/roadmap.json": "75e2d62e734488c7c4128642dc28872edcb0160e2705dc2ccb363f69845aefeb",
    "machine/facts/requirements.json": "54d4a849ebb1266e8a01c99259f0a54728e901007657ec44e04178dcbc8bea12",
    "machine/facts/acceptance_contracts.json": "b91a48288cc3fec26233a5a0c8170d164cfec0e66e9b0f28f2012c96128d1342",
    "machine/facts/task_graph.json": "78ae36747193003a24a0d15a620664b1cb406609356242a003bf821b775cd778",
    "machine/facts/traceability_matrix.json": "e2e703bb8bd6db6bc44d0597b496d7fd5dac4a6f3c633e464c40348175a1ad1a",
    P01_EVIDENCE_PATH.as_posix(): "57c81a3d5807389237fe78b596b6251bd585e58e0925a829ec4a81da3b0957a6",
    P01_ROLLBACK_PATH.as_posix(): "438b0f42396afd8ab399d46b588d470453eca2ea20bda6bee83a6f9acc84ce34",
    STAGE3_DELIVERY_RECEIPT_PATH.as_posix(): STAGE3_DELIVERY_RECEIPT_SHA256,
}
PINNED_REPO_HASHES = {
    WORKFLOW_PATH.as_posix(): "e1ed7245f525cea1489932337e18fe8abbe13d3a8d45cfcf11aa2235b444a25d",
}

EXTERNAL_EFFECT_BOUNDARY = {
    "network_accessed": False,
    "cloudflare_account_api_or_dashboard_accessed": False,
    "cloudflare_tunnel_created_configured_or_run": False,
    "cloudflare_dns_changed": False,
    "cloudflare_access_application_or_policy_applied": False,
    "ovh_account_or_host_accessed": False,
    "public_business_inbound_opened": False,
    "secret_value_read_or_stored": False,
    "production_activated": False,
    "real_order_submitted": False,
    "return_or_roi_verified": False,
    "incremental_cash_spent_aud": "0.00",
}

POLICY_START = "<!-- ABD_ACCESS_POLICY_JSON_START -->"
POLICY_END = "<!-- ABD_ACCESS_POLICY_JSON_END -->"
SECRET_PATTERNS = [
    re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----"),
    re.compile(r"\bghp_[A-Za-z0-9]{20,}\b"),
    re.compile(r"\bAKIA[A-Z0-9]{16}\b"),
    re.compile(r"(?i)\b(?:api[_-]?token|client[_-]?secret|password)\s*[:=]\s*['\"]?[A-Za-z0-9_./+\-=]{12,}"),
]
LOCAL_PATH_FRAGMENTS = ["/" + "Users/", "/private/" + "var/", "file" + "://", "C:" + "\\Users\\"]


class CloudflareEdgeContractError(ValueError):
    """Raised when the S04/P02 edge contract fails closed."""


def _json_bytes(value: Any) -> bytes:
    return (json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2) + "\n").encode("utf-8")


def _sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _contains_float(value: Any) -> bool:
    if isinstance(value, float):
        return True
    if isinstance(value, Mapping):
        return any(_contains_float(item) for item in value.values())
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        return any(_contains_float(item) for item in value)
    return False


def _add(checks: List[Dict[str, Any]], check_id: str, passed: bool, detail: Any) -> None:
    checks.append({"id": check_id, "passed": bool(passed), "detail": detail})


def _safe_load(path: Path, checks: List[Dict[str, Any]], check_id: str) -> Any:
    try:
        value = strict_json_load(path)
    except Exception as exc:
        _add(checks, check_id, False, "%s: %s" % (type(exc).__name__, exc))
        return None
    _add(checks, check_id, True, path.name)
    return value


def _strict_json_text(text: str) -> Any:
    def reject_duplicates(pairs: List[tuple[str, Any]]) -> Dict[str, Any]:
        result: Dict[str, Any] = {}
        for key, value in pairs:
            if key in result:
                raise DuplicateKeyError("duplicate JSON key: %s" % key)
            result[key] = value
        return result

    return json.loads(text, object_pairs_hook=reject_duplicates, parse_constant=lambda value: (_ for _ in ()).throw(ValueError("non-finite JSON value: %s" % value)))


def _current_code_hash(root: Path) -> str:
    digest = hashlib.sha256()
    for path in sorted((root / "abd_acceptance").glob("*.py")):
        digest.update(path.relative_to(root).as_posix().encode("utf-8"))
        digest.update(b"\0")
        digest.update(path.read_bytes())
        digest.update(b"\0")
    return digest.hexdigest()


def _phase_commit_is_ancestor(root: Path) -> bool:
    result = subprocess.run(
        ["git", "-C", str(root.parent), "merge-base", "--is-ancestor", PHASE_COMMIT, "HEAD"],
        check=False,
        capture_output=True,
        text=True,
    )
    return result.returncode == 0


def _historical_file_matches(root: Path, relative: str, expected_sha256: str, verify_git_history: bool) -> bool:
    if relative not in SUCCESSOR_EVOLVABLE_SIGNED_INPUTS:
        return False
    if verify_git_history:
        if not _phase_commit_is_ancestor(root):
            return False
        result = subprocess.run(
            ["git", "-C", str(root.parent), "show", "%s:ABD/%s" % (PHASE_COMMIT, relative)],
            check=False,
            capture_output=True,
        )
        return result.returncode == 0 and _sha256_bytes(result.stdout) == expected_sha256
    if relative == "abd_acceptance/cloudflare_edge.py":
        try:
            return _structural_self_hash(root) == STRUCTURAL_SELF_NORMALIZED_SHA256
        except Exception:
            return False
    successor = SUCCESSOR_UNIT_PROFILE_HASHES.get(relative)
    return successor not in {None, "TO_BE_FILLED"} and (root / relative).is_file() and sha256_file(root / relative) == successor


def _historical_code_hash(root: Path, verify_git_history: bool) -> str:
    if not verify_git_history:
        return "UNVERIFIED_UNIT_TEST_HISTORY"
    if not _phase_commit_is_ancestor(root):
        return "INVALID_PHASE_COMMIT_ANCESTRY"
    listing = subprocess.run(
        ["git", "-C", str(root.parent), "ls-tree", "-r", "--name-only", PHASE_COMMIT, "--", "ABD/abd_acceptance"],
        check=False,
        capture_output=True,
        text=True,
    )
    if listing.returncode != 0:
        return "UNAVAILABLE_PHASE_COMMIT_TREE"
    digest = hashlib.sha256()
    repo_paths = sorted(line for line in listing.stdout.splitlines() if line.startswith("ABD/abd_acceptance/") and line.endswith(".py"))
    for repo_path in repo_paths:
        blob = subprocess.run(
            ["git", "-C", str(root.parent), "show", "%s:%s" % (PHASE_COMMIT, repo_path)],
            check=False,
            capture_output=True,
        )
        if blob.returncode != 0:
            return "UNAVAILABLE_PHASE_COMMIT_BLOB"
        digest.update(repo_path.removeprefix("ABD/").encode("utf-8"))
        digest.update(b"\0")
        digest.update(blob.stdout)
        digest.update(b"\0")
    return digest.hexdigest()


def _structural_self_hash(root: Path) -> str:
    text = (root / "abd_acceptance/cloudflare_edge.py").read_text(encoding="utf-8")
    normalized = re.sub(
        r'(?m)^(STRUCTURAL_SELF_NORMALIZED_SHA256 = ")[^"]+("\s*)$',
        r"\1<NORMALIZED>\2",
        text,
        count=1,
    )
    if normalized == text:
        return "NORMALIZATION_FAILED"
    return _sha256_bytes(normalized.encode("utf-8"))


def _load_index(root: Path) -> List[Dict[str, Any]]:
    return [
        json.loads(line)
        for line in (root / EVIDENCE_INDEX_PATH).read_text(encoding="utf-8-sig").splitlines()
        if line
    ]


def parse_access_policy(text: str) -> Dict[str, Any]:
    if text.count(POLICY_START) != 1 or text.count(POLICY_END) != 1:
        raise CloudflareEdgeContractError("access policy must contain exactly one machine-readable contract block")
    start = text.index(POLICY_START) + len(POLICY_START)
    end = text.index(POLICY_END, start)
    block = text[start:end].strip()
    try:
        value = _strict_json_text(block)
    except Exception as exc:
        raise CloudflareEdgeContractError("invalid access policy JSON: %s" % exc) from exc
    if not isinstance(value, dict):
        raise CloudflareEdgeContractError("access policy JSON must be an object")
    return value


def _recursive_keys(value: Any) -> List[str]:
    keys: List[str] = []
    if isinstance(value, Mapping):
        for key, item in value.items():
            keys.append(str(key))
            keys.extend(_recursive_keys(item))
    elif isinstance(value, list):
        for item in value:
            keys.extend(_recursive_keys(item))
    return keys


def validate_cloudflared_config(config: Any) -> List[str]:
    errors: List[str] = []
    if not isinstance(config, Mapping):
        return ["configuration must be an object"]
    expected_keys = {"tunnel", "credentials-file", "no-autoupdate", "metrics", "ingress"}
    if set(config) != expected_keys:
        errors.append("top-level keys must be the frozen minimal set")
    if config.get("tunnel") != PLACEHOLDER_TUNNEL_ID:
        errors.append("repository tunnel identifier must remain the inert UUID placeholder")
    expected_credentials = "/etc/cloudflared/%s.json" % PLACEHOLDER_TUNNEL_ID
    if config.get("credentials-file") != expected_credentials:
        errors.append("credentials-file must be an external restricted-path reference")
    if config.get("no-autoupdate") is not True:
        errors.append("automatic connector updates must be disabled")
    if config.get("metrics") != "127.0.0.1:49312":
        errors.append("metrics must bind only to loopback")
    ingress = config.get("ingress")
    if not isinstance(ingress, list) or len(ingress) != 2:
        errors.append("ingress must contain one named route and one final catch-all")
    else:
        route, catch_all = ingress
        if not isinstance(route, Mapping) or set(route) != {"hostname", "service", "originRequest"}:
            errors.append("named ingress route has unexpected shape")
        else:
            if route.get("hostname") != PLACEHOLDER_HOSTNAME:
                errors.append("repository hostname must remain under example.invalid")
            if route.get("service") != "http://127.0.0.1:8080":
                errors.append("origin business service must use loopback only")
            if route.get("originRequest") != {"connectTimeout": "10s"}:
                errors.append("origin request settings must remain the frozen minimal safe set")
        if catch_all != {"service": "http_status:404"}:
            errors.append("last ingress rule must be the rejecting HTTP 404 catch-all")
    forbidden_keys = {
        "token",
        "api-token",
        "api_token",
        "password",
        "client-secret",
        "client_secret",
        "noTLSVerify",
        "warp-routing",
    }
    found = sorted(forbidden_keys.intersection(_recursive_keys(config)))
    if found:
        errors.append("forbidden secret, TLS-bypass or private-routing keys: %s" % found)
    if _contains_float(config):
        errors.append("binary floats are not permitted")
    return errors


def validate_access_policy(policy: Any) -> List[str]:
    errors: List[str] = []
    if not isinstance(policy, Mapping):
        return ["policy must be an object"]
    if set(policy) != {"schema_version", "contract_id", "application", "enforcement", "network_boundary", "activation", "claims", "budget"}:
        errors.append("policy top-level keys do not match the frozen contract")
    if policy.get("schema_version") != "1.0.0" or policy.get("contract_id") != CONTRACT_ID:
        errors.append("policy identity mismatch")
    application = policy.get("application", {})
    if application != {"type": "SELF_HOSTED", "hostname": PLACEHOLDER_HOSTNAME, "status": "NOT_CREATED_OR_INSPECTED"}:
        errors.append("self-hosted application must remain an uncreated placeholder")
    enforcement = policy.get("enforcement", {})
    policies = enforcement.get("allow_policies", []) if isinstance(enforcement, Mapping) else []
    if enforcement.get("default_action") != "DENY":
        errors.append("Access must remain deny by default")
    if not isinstance(policies, list) or len(policies) != 1:
        errors.append("exactly one owner allow policy is required")
    else:
        allow = policies[0]
        include = allow.get("include", {}) if isinstance(allow, Mapping) else {}
        require = allow.get("require", {}) if isinstance(allow, Mapping) else {}
        if allow.get("action") != "ALLOW":
            errors.append("owner policy action must be ALLOW")
        if include != {"selector": "EMAIL", "value": OWNER_PLACEHOLDER, "exact_owner_count": 1}:
            errors.append("owner policy must use one exact external email placeholder")
        if require != {"mfa": True, "mfa_mode": "INDEPENDENT_OR_IDP_MFA_MUST_BE_VERIFIED"}:
            errors.append("MFA must be explicitly required and later verified")
        if allow.get("session_duration") != "1h":
            errors.append("session duration must remain one hour")
    if enforcement.get("forbidden_actions") != ["BYPASS", "SERVICE_AUTH"]:
        errors.append("Bypass and Service Auth must be explicitly forbidden")
    if enforcement.get("everyone_selector_allowed") is not False or enforcement.get("email_domain_wildcard_allowed") is not False:
        errors.append("Everyone and wildcard email-domain selectors are forbidden")
    if enforcement.get("audit_logging_required") is not True:
        errors.append("Access audit logging must be required")
    network = policy.get("network_boundary", {})
    expected_network = {
        "origin_service": "http://127.0.0.1:8080",
        "origin_business_inbound_required": False,
        "tunnel_connector_direction": "OUTBOUND_ONLY",
        "catch_all_action": "HTTP_404",
        "metrics_bind": "127.0.0.1:49312",
    }
    if network != expected_network:
        errors.append("network boundary is not the frozen outbound-only contract")
    activation = policy.get("activation", {})
    prerequisites = activation.get("prerequisites", {}) if isinstance(activation, Mapping) else {}
    if activation.get("requested") is not False or activation.get("status") != "BLOCKED_EXTERNAL_PREREQUISITES_NOT_VERIFIED":
        errors.append("repository policy must remain blocked and not requested")
    if not isinstance(prerequisites, Mapping) or len(prerequisites) != 8 or any(value == "VERIFIED" for value in prerequisites.values()):
        errors.append("all eight external activation prerequisites must remain unverified")
    claims = policy.get("claims", {})
    if claims.get("mainland_china_acceleration_availability_or_reach") != "NOT_IN_ZERO_CASH_SCOPE_NO_CLAIM":
        errors.append("mainland China acceleration, availability and reach must fail closed")
    if claims.get("ovh_7x24") != "UNVERIFIED_REQUIRES_RUNTIME_EVIDENCE" or claims.get("returns") != "UNVERIFIED_NOT_GUARANTEED":
        errors.append("runtime and return claims must remain unverified")
    budget = policy.get("budget", {})
    if budget != {"incremental_cash_aud": "0.00", "paid_upgrade_allowed": False, "china_network_subscription_allowed": False, "automatic_overage_allowed": False}:
        errors.append("A$0 and no-paid-upgrade budget gate mismatch")
    if _contains_float(policy):
        errors.append("binary floats are not permitted")
    return errors


class _DegradedPageParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.tags: List[str] = []
        self.attrs: List[tuple[str, str, str]] = []
        self.text: List[str] = []
        self.html_lang: str | None = None
        self.csp: str | None = None

    def handle_starttag(self, tag: str, attrs: List[tuple[str, str | None]]) -> None:
        lowered = tag.lower()
        self.tags.append(lowered)
        for name, value in attrs:
            current = value or ""
            self.attrs.append((lowered, name.lower(), current))
            if lowered == "html" and name.lower() == "lang":
                self.html_lang = current
            if lowered == "meta" and name.lower() == "http-equiv" and current.lower() == "content-security-policy":
                values = {key.lower(): (item or "") for key, item in attrs}
                self.csp = values.get("content")

    def handle_data(self, data: str) -> None:
        if data.strip():
            self.text.append(data.strip())


def analyze_degraded_page(text: str) -> Dict[str, Any]:
    parser = _DegradedPageParser()
    try:
        parser.feed(text)
        parser.close()
    except Exception as exc:
        return {"status": "FAIL", "issues": ["HTML parse failure: %s" % exc]}
    issues: List[str] = []
    forbidden_tags = {"script", "form", "iframe", "object", "embed", "link", "img", "video", "audio", "source", "input", "button", "select", "textarea", "a"}
    present_forbidden = sorted(forbidden_tags.intersection(parser.tags))
    if present_forbidden:
        issues.append("forbidden active or external tags: %s" % present_forbidden)
    event_attrs = sorted({name for _, name, _ in parser.attrs if name.startswith("on")})
    if event_attrs:
        issues.append("event handler attributes are forbidden: %s" % event_attrs)
    reference_attrs = [(tag, name, value) for tag, name, value in parser.attrs if name in {"href", "src", "action", "formaction"} and value]
    if reference_attrs:
        issues.append("external or interactive references are forbidden")
    expected_csp_tokens = {"default-src 'none'", "style-src 'unsafe-inline'", "base-uri 'none'", "form-action 'none'", "frame-ancestors 'none'"}
    if parser.csp is None or not expected_csp_tokens.issubset({item.strip() for item in parser.csp.split(";") if item.strip()}):
        issues.append("fail-closed CSP is missing or incomplete")
    if parser.html_lang != "zh-CN":
        issues.append("document language must be zh-CN")
    visible = " ".join(parser.text)
    required_text = [
        "服务暂不可用",
        "停止新建议",
        "不要使用任何旧建议下单",
        "所有先前建议立即失效",
        "下一步",
        "才由你自行完成最终下单",
        "不是随机收益保证",
        "不代表中国大陆境内加速、可用性或可达性保证",
    ]
    missing = [item for item in required_text if item not in visible]
    if missing:
        issues.append("required Chinese fail-closed guidance missing: %s" % missing)
    if re.search(r"(?i)https?://|javascript:|data:", text):
        issues.append("embedded URL or active URI scheme is forbidden")
    return {
        "status": "PASS" if not issues else "FAIL",
        "issues": issues,
        "lang": parser.html_lang,
        "csp": parser.csp,
        "visible_text_sha256": _sha256_bytes(visible.encode("utf-8")),
        "forbidden_tags": present_forbidden,
        "external_references": reference_attrs,
    }


def activation_gate(config: Mapping[str, Any], policy: Mapping[str, Any]) -> str:
    activation = policy.get("activation", {})
    prerequisites = activation.get("prerequisites", {}) if isinstance(activation, Mapping) else {}
    tunnel = config.get("tunnel")
    hostname = config.get("ingress", [{}])[0].get("hostname") if isinstance(config.get("ingress"), list) and config.get("ingress") else None
    ready = (
        isinstance(prerequisites, Mapping)
        and len(prerequisites) == 8
        and set(prerequisites.values()) == {"VERIFIED"}
        and activation.get("requested") is True
        and isinstance(tunnel, str)
        and tunnel != PLACEHOLDER_TUNNEL_ID
        and isinstance(hostname, str)
        and hostname != PLACEHOLDER_HOSTNAME
        and hostname.endswith(".invalid") is False
    )
    return "READY_FOR_EXPLICIT_P03_ACTIVATION" if ready else "BLOCKED_EXTERNAL_PREREQUISITES_NOT_VERIFIED"


def edge_disposition(
    config: Mapping[str, Any],
    policy: Mapping[str, Any],
    degraded_page: str,
    *,
    numeric_boundary_delta: str = "0",
    adverse_odds_tick: bool = False,
) -> Dict[str, Any]:
    if numeric_boundary_delta not in ALLOWED_NUMERIC_BOUNDARY_DELTAS:
        raise CloudflareEdgeContractError("numeric boundary delta is not frozen")
    if type(adverse_odds_tick) is not bool:
        raise CloudflareEdgeContractError("adverse odds tick must be boolean")
    config_errors = validate_cloudflared_config(config)
    policy_errors = validate_access_policy(policy)
    degraded = analyze_degraded_page(degraded_page)
    passed = not config_errors and not policy_errors and degraded["status"] == "PASS"
    return {
        "status": "PASS" if passed else "FAIL",
        "decision": "OUTBOUND_ONLY_EDGE_CONFIGURATION_CONTRACT_FROZEN" if passed else "EDGE_CONFIGURATION_BLOCKED_FAIL_CLOSED",
        "activation_gate": activation_gate(config, policy),
        "numeric_boundary_delta": numeric_boundary_delta,
        "adverse_odds_tick": adverse_odds_tick,
        "config_errors": config_errors,
        "policy_errors": policy_errors,
        "degraded_page": degraded,
        "public_business_inbound_required": False if passed else None,
        "runtime_access_verified": False,
    }


def materialize_edge_bundle(root: Path, destination: Path) -> Dict[str, Any]:
    root = root.resolve()
    destination = destination.resolve()
    if destination.exists() or destination.is_symlink():
        raise CloudflareEdgeContractError("destination must not already exist")
    config = strict_json_load(root / CONFIG_PATH)
    policy = parse_access_policy((root / POLICY_PATH).read_text(encoding="utf-8"))
    page = (root / DEGRADED_PAGE_PATH).read_text(encoding="utf-8")
    result = edge_disposition(config, policy, page)
    if result["status"] != "PASS":
        raise CloudflareEdgeContractError("edge artifacts rejected: %s" % json.dumps(result, ensure_ascii=False, sort_keys=True))
    destination.mkdir(parents=True, mode=0o750)
    files: Dict[str, str] = {}
    for relative in [CONFIG_PATH, POLICY_PATH, DEGRADED_PAGE_PATH]:
        target = destination / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(root / relative, target)
        files[relative.as_posix()] = sha256_file(target)
    manifest = {
        "schema_version": "1.0.0",
        "product_version": VERSION,
        "phase_id": "%s/%s" % (STAGE_ID, PHASE_ID),
        "fixed_clock": FIXED_CLOCK,
        "files": files,
        "configuration_mode": "LOCALLY_MANAGED_NAMED_TUNNEL_TEMPLATE",
        "activation_gate": result["activation_gate"],
        "production_activation_performed": False,
        "runtime_access_verified": False,
        "external_effect_boundary": EXTERNAL_EFFECT_BOUNDARY,
    }
    (destination / "edge_manifest.json").write_bytes(_json_bytes(manifest))
    return manifest


def _tree_hash(root: Path) -> str:
    digest = hashlib.sha256()
    for path in sorted(item for item in root.rglob("*") if item.is_file()):
        digest.update(path.relative_to(root).as_posix().encode("utf-8"))
        digest.update(b"\0")
        digest.update(path.read_bytes())
        digest.update(b"\0")
    return digest.hexdigest()


def _set_or_delete_path(value: Any, path: Sequence[Any], replacement: Any = None, *, delete: bool = False) -> None:
    cursor = value
    for part in path[:-1]:
        cursor = cursor[part]
    final = path[-1]
    if delete:
        if isinstance(cursor, list):
            del cursor[final]
        else:
            del cursor[final]
    else:
        cursor[final] = replacement


def _check_pins(root: Path, checks: List[Dict[str, Any]], hashes: MutableMapping[str, str]) -> None:
    for relative, expected in PINNED_PHASE_HASHES.items():
        path = root / relative
        actual = sha256_file(path) if path.is_file() else "MISSING"
        hashes[relative] = actual
        successor = SUCCESSOR_UNIT_PROFILE_HASHES.get(relative)
        _add(checks, "S04P02-PIN-%s" % relative.upper().replace("/", "-").replace(".", "-"), actual == expected or (successor not in {None, "TO_BE_FILLED"} and actual == successor), {"expected": expected, "accepted_successor": successor, "actual": actual})
    self_hash = _structural_self_hash(root)
    hashes["abd_acceptance/cloudflare_edge.py"] = sha256_file(root / "abd_acceptance/cloudflare_edge.py")
    _add(checks, "S04P02-ORACLE-SELF-INTEGRITY", self_hash == STRUCTURAL_SELF_NORMALIZED_SHA256, {"expected": STRUCTURAL_SELF_NORMALIZED_SHA256, "actual": self_hash})
    for relative, expected in PINNED_BASELINE_HASHES.items():
        path = root / relative
        actual = sha256_file(path) if path.is_file() else "MISSING"
        hashes[relative] = actual
        _add(checks, "S04P02-BASELINE-%s" % relative.upper().replace("/", "-").replace(".", "-"), actual == expected, {"expected": expected, "actual": actual})
    for relative, expected in PINNED_REPO_HASHES.items():
        path = root.parent / relative
        actual = sha256_file(path) if path.is_file() else "MISSING"
        hashes[relative] = actual
        _add(checks, "S04P02-REPO-%s" % relative.upper().replace("/", "-").replace(".", "-"), actual == expected, {"expected": expected, "actual": actual})


def _check_taskpack(root: Path, fixture: Mapping[str, Any], checks: List[Dict[str, Any]]) -> None:
    requirements = strict_json_load(root / "machine/facts/requirements.json")
    acceptance = strict_json_load(root / "machine/facts/acceptance_contracts.json")
    graph = strict_json_load(root / "machine/facts/task_graph.json")
    traceability = strict_json_load(root / "machine/facts/traceability_matrix.json")
    roadmap = strict_json_load(root / "machine/facts/roadmap.json")
    requirement = [row for row in requirements if row.get("id") == REQUIREMENT_ID]
    _add(checks, "S04P02-TASKPACK-REQUIREMENT", len(requirement) == 1 and requirement[0].get("scope") == list(fixture["expected_artifacts"].values()) and requirement[0].get("target") == "OVH无需公开业务入站端口即可访问。", requirement)
    contract = [row for row in acceptance if row.get("id") == CONTRACT_ID]
    _add(checks, "S04P02-TASKPACK-ACCEPTANCE", len(contract) == 1 and contract[0].get("oracle", {}).get("command") == "python -m abd_acceptance --contract AC-S04-P02 --evidence machine/evidence" and [row.get("id") for row in contract[0].get("tests", [])] == fixture["expected_test_ids"], contract)
    tasks = graph.get("tasks", []) if isinstance(graph, Mapping) else []
    selected = [row for row in tasks if row.get("id") in fixture["expected_task_ids"]]
    _add(checks, "S04P02-TASKPACK-TASK-IDS", [row.get("id") for row in selected] == fixture["expected_task_ids"], [row.get("id") for row in selected])
    expected_outputs = [
        list(fixture["expected_artifacts"].values()),
        [TEST_PATH.as_posix(), FIXTURE_PATH.as_posix()],
        [EVIDENCE_PATH.as_posix(), ROLLBACK_EVIDENCE_PATH.as_posix()],
    ]
    _add(checks, "S04P02-TASKPACK-TASK-OUTPUTS", [row.get("outputs") for row in selected] == expected_outputs, [row.get("outputs") for row in selected])
    _add(checks, "S04P02-TASKPACK-TASK-DEPENDENCIES", [row.get("depends_on") for row in selected] == [["T-S04-P01-03"], ["T-S04-P02-01"], ["T-S04-P02-02"]], [row.get("depends_on") for row in selected])
    trace = [row for row in traceability if row.get("requirement_id") == REQUIREMENT_ID]
    _add(checks, "S04P02-TASKPACK-TRACE", len(trace) == 1 and trace[0].get("acceptance_criteria_id") == CONTRACT_ID and trace[0].get("task_ids") == fixture["expected_task_ids"] and trace[0].get("test_ids") == fixture["expected_test_ids"] and trace[0].get("evidence_id") == "EVD-S04-P02", trace)
    stages = [row for row in roadmap.get("stages", []) if row.get("id") == STAGE_ID] if isinstance(roadmap, Mapping) else []
    phase = [row for row in stages[0].get("phases", []) if row.get("id") == PHASE_ID] if len(stages) == 1 else []
    _add(checks, "S04P02-TASKPACK-ROADMAP", len(phase) == 1 and phase[0].get("outputs") == list(fixture["expected_artifacts"].values()) and phase[0].get("pass_gate") == "OVH无需公开业务入站端口即可访问。", phase)


def _check_sources(fixture: Mapping[str, Any], checks: List[Dict[str, Any]]) -> None:
    expected_ids = ["S04P02-SRC-TUNNEL-CONFIG", "S04P02-SRC-OUTBOUND-ONLY", "S04P02-SRC-ACCESS-POLICIES", "S04P02-SRC-MFA", "S04P02-SRC-CHINA-NETWORK"]
    sources = fixture.get("official_sources", [])
    _add(checks, "S04P02-SOURCE-IDS", [row.get("id") for row in sources] == expected_ids, [row.get("id") for row in sources])
    for source in sources:
        parsed = urlsplit(str(source.get("url", "")))
        ok = source.get("publisher") == "Cloudflare" and source.get("retrieved_at") == "2026-07-22" and parsed.scheme == "https" and parsed.netloc == "developers.cloudflare.com" and bool(source.get("fact"))
        _add(checks, "S04P02-SOURCE-%s" % source.get("id", "UNKNOWN"), ok, source)


def _check_artifacts(root: Path, fixture: Mapping[str, Any], config: Mapping[str, Any], policy: Mapping[str, Any], page: str, checks: List[Dict[str, Any]]) -> None:
    config_errors = validate_cloudflared_config(config)
    _add(checks, "S04P02-CONFIG-VALID", not config_errors, config_errors or "valid")
    _add(checks, "S04P02-CONFIG-FROZEN", config == fixture.get("expected_config"), config)
    _add(checks, "S04P02-CONFIG-NAMED-TUNNEL", config.get("tunnel") == PLACEHOLDER_TUNNEL_ID and config.get("credentials-file") == "/etc/cloudflared/%s.json" % PLACEHOLDER_TUNNEL_ID, {"tunnel": config.get("tunnel"), "credentials-file": config.get("credentials-file")})
    _add(checks, "S04P02-CONFIG-LOOPBACK-ORIGIN", config.get("ingress", [{}])[0].get("service") == "http://127.0.0.1:8080", config.get("ingress"))
    _add(checks, "S04P02-CONFIG-CATCH-ALL-LAST", config.get("ingress", [{}])[-1] == {"service": "http_status:404"}, config.get("ingress"))
    _add(checks, "S04P02-CONFIG-METRICS-LOOPBACK", config.get("metrics") == "127.0.0.1:49312", config.get("metrics"))
    _add(checks, "S04P02-CONFIG-NO-AUTOUPDATE", config.get("no-autoupdate") is True, config.get("no-autoupdate"))
    _add(checks, "S04P02-CONFIG-NO-TLS-BYPASS-OR-PRIVATE-ROUTING", not {"noTLSVerify", "warp-routing"}.intersection(_recursive_keys(config)), _recursive_keys(config))
    mutation_results: Dict[str, bool] = {}
    for mutation in fixture.get("invalid_config_mutations", []):
        candidate = deepcopy(config)
        try:
            _set_or_delete_path(candidate, mutation["path"], mutation.get("value"), delete=mutation.get("delete") is True)
            mutation_results[mutation["id"]] = bool(validate_cloudflared_config(candidate))
        except Exception:
            mutation_results[mutation.get("id", "UNKNOWN")] = True
    _add(checks, "S04P02-CONFIG-ALL-MUTATIONS-FAIL-CLOSED", len(mutation_results) == len(fixture.get("invalid_config_mutations", [])) and all(mutation_results.values()), mutation_results)

    policy_errors = validate_access_policy(policy)
    _add(checks, "S04P02-POLICY-VALID", not policy_errors, policy_errors or "valid")
    enforcement = policy.get("enforcement", {})
    allow = enforcement.get("allow_policies", [{}])[0]
    _add(checks, "S04P02-POLICY-DENY-DEFAULT", enforcement.get("default_action") == "DENY", enforcement.get("default_action"))
    _add(checks, "S04P02-POLICY-EXACT-OWNER", allow.get("include") == {"selector": "EMAIL", "value": OWNER_PLACEHOLDER, "exact_owner_count": 1}, allow.get("include"))
    _add(checks, "S04P02-POLICY-MFA", allow.get("require", {}).get("mfa") is True, allow.get("require"))
    _add(checks, "S04P02-POLICY-NO-BYPASS-SERVICE-AUTH", enforcement.get("forbidden_actions") == ["BYPASS", "SERVICE_AUTH"], enforcement.get("forbidden_actions"))
    _add(checks, "S04P02-POLICY-NO-EVERYONE-OR-WILDCARD", enforcement.get("everyone_selector_allowed") is False and enforcement.get("email_domain_wildcard_allowed") is False, enforcement)
    _add(checks, "S04P02-POLICY-AUDIT-LOGS", enforcement.get("audit_logging_required") is True, enforcement.get("audit_logging_required"))
    _add(checks, "S04P02-POLICY-ACTIVATION-BLOCKED", activation_gate(config, policy) == fixture.get("expected_activation_gate"), activation_gate(config, policy))
    _add(checks, "S04P02-POLICY-MAINLAND-CLAIM-REJECTED", policy.get("claims", {}).get("mainland_china_acceleration_availability_or_reach") == "NOT_IN_ZERO_CASH_SCOPE_NO_CLAIM", policy.get("claims"))
    _add(checks, "S04P02-POLICY-A0", policy.get("budget", {}).get("incremental_cash_aud") == "0.00" and policy.get("budget", {}).get("china_network_subscription_allowed") is False, policy.get("budget"))

    degraded = analyze_degraded_page(page)
    _add(checks, "S04P02-DEGRADED-PAGE-VALID", degraded.get("status") == "PASS", degraded)
    _add(checks, "S04P02-DEGRADED-PAGE-ZH", degraded.get("lang") == "zh-CN", degraded.get("lang"))
    _add(checks, "S04P02-DEGRADED-PAGE-CSP", isinstance(degraded.get("csp"), str) and "default-src 'none'" in degraded.get("csp", ""), degraded.get("csp"))
    _add(checks, "S04P02-DEGRADED-PAGE-NO-ACTIVE-TAGS", degraded.get("forbidden_tags") == [], degraded.get("forbidden_tags"))
    _add(checks, "S04P02-DEGRADED-PAGE-NO-EXTERNAL-REFERENCES", degraded.get("external_references") == [], degraded.get("external_references"))
    _add(checks, "S04P02-DEGRADED-PAGE-STOP-AND-INVALIDATE", all(token in page for token in ["停止新建议", "所有先前建议立即失效", "不要使用任何旧建议下单"]), "fail-closed guidance")
    _add(checks, "S04P02-DEGRADED-PAGE-NEXT-ACTION", "下一步" in page and "才由你自行完成最终下单" in page, "explicit safe next action")
    _add(checks, "S04P02-DEGRADED-PAGE-NO-GUARANTEE", "不是随机收益保证" in page, "30% target is not a guarantee")

    baseline = edge_disposition(config, policy, page)
    _add(checks, "S04P02-DISPOSITION-PASS", baseline.get("status") == "PASS" and baseline.get("public_business_inbound_required") is False and baseline.get("runtime_access_verified") is False, baseline)
    for delta in fixture.get("allowed_numeric_boundary_deltas", []):
        for adverse in [False, True]:
            result = edge_disposition(config, policy, page, numeric_boundary_delta=delta, adverse_odds_tick=adverse)
            _add(checks, "S04P02-NUMERIC-%s-%s" % (delta.replace("-", "NEG").replace(".", "_"), "ADVERSE" if adverse else "BASE"), result["status"] == baseline["status"] and result["decision"] == baseline["decision"] and result["activation_gate"] == baseline["activation_gate"], {"delta": delta, "adverse": adverse, "result": result["status"]})

    with tempfile.TemporaryDirectory(prefix="abd-s04-p02-bundle-") as temporary:
        first = Path(temporary) / "first"
        second = Path(temporary) / "second"
        first_manifest = materialize_edge_bundle(root, first)
        second_manifest = materialize_edge_bundle(root, second)
        _add(checks, "S04P02-BUNDLE-FILES", sorted(path.relative_to(first).as_posix() for path in first.rglob("*") if path.is_file()) == fixture.get("expected_bundle_files"), sorted(path.relative_to(first).as_posix() for path in first.rglob("*") if path.is_file()))
        _add(checks, "S04P02-BUNDLE-DETERMINISTIC-REPLAY", first_manifest == second_manifest and _tree_hash(first) == _tree_hash(second), {"first": _tree_hash(first), "second": _tree_hash(second)})


def _p03_candidate_contract(root: Path) -> Dict[str, Any]:
    try:
        from .release_control import (
            PINNED_PHASE_HASHES as P03_PHASE_HASHES,
            STRUCTURAL_SELF_NORMALIZED_SHA256 as P03_SELF_HASH,
            _structural_self_hash as p03_structural_self_hash,
            validate_feature_flags,
            validate_release_slots,
        )

        mismatches: Dict[str, Dict[str, str]] = {}
        for relative, expected in P03_PHASE_HASHES.items():
            path = root / relative
            actual = sha256_file(path) if path.is_file() else "MISSING"
            if actual != expected:
                mismatches[relative] = {"expected": expected, "actual": actual}
        slots = strict_json_load(root / "release_slots.json")
        flags = strict_json_load(root / "feature_flags.json")
        policy = strict_json_load(root / "machine/facts/release_policy.json")
        slot_errors = validate_release_slots(slots, policy)
        flag_errors = validate_feature_flags(flags, policy)
        self_actual = p03_structural_self_hash(root)
        ok = not mismatches and not slot_errors and not flag_errors and self_actual == P03_SELF_HASH
        return {
            "status": "PASS" if ok else "FAIL",
            "mismatches": mismatches,
            "slot_errors": slot_errors,
            "flag_errors": flag_errors,
            "self_expected": P03_SELF_HASH,
            "self_actual": self_actual,
        }
    except Exception as exc:
        return {"status": "FAIL", "error": "%s: %s" % (type(exc).__name__, exc)}


def _p03_signed_contract(root: Path, index_row: Mapping[str, Any]) -> Dict[str, Any]:
    try:
        evidence_path = root / "machine/evidence/EVD-S04-P03.json"
        rollback_path = root / "machine/evidence/EVD-S04-P03_rollback.json"
        evidence = strict_json_load(evidence_path)
        rollback = strict_json_load(rollback_path)
        unsigned = deepcopy(evidence)
        decision_sha256 = unsigned.pop("decision_sha256", None)
        evidence_hash = sha256_file(evidence_path)
        rollback_hash = sha256_file(rollback_path)
        ok = (
            evidence.get("evidence_id") == "EVD-S04-P03"
            and evidence.get("contract_id") == "AC-S04-P03"
            and evidence.get("status") == "PASS"
            and evidence.get("decision") == "SAME_HOST_BLUE_GREEN_RELEASE_CONTRACT_FROZEN"
            and evidence.get("next") == "S04/P04_READY_NOT_STARTED"
            and decision_sha256 == _sha256_bytes(_json_bytes(unsigned))
            and evidence.get("hashes", {}).get("rollback_evidence") == rollback_hash
            and rollback.get("evidence_id") == "EVD-S04-P03-ROLLBACK"
            and rollback.get("status") == "PASS"
            and rollback.get("production_state_changed") is False
            and rollback.get("external_state_changed") is False
            and index_row.get("status") == "PASS"
            and index_row.get("actual_artifact") == "machine/evidence/EVD-S04-P03.json"
            and index_row.get("artifact_sha256") == evidence_hash
            and index_row.get("next") == "S04/P04_READY_NOT_STARTED"
        )
        return {"status": "PASS" if ok else "FAIL", "evidence_sha256": evidence_hash, "rollback_sha256": rollback_hash}
    except Exception as exc:
        return {"status": "FAIL", "error": "%s: %s" % (type(exc).__name__, exc)}


def _check_progression(root: Path, checks: List[Dict[str, Any]]) -> None:
    candidate_paths = [
        Path("release_slots.json"),
        Path("feature_flags.json"),
        Path("rollback.sh"),
        Path("tests/S04/P03_test.py"),
        Path("machine/tests/fixtures/S04_P03.json"),
        Path("abd_acceptance/release_control.py"),
    ]
    signed_paths = [
        Path("machine/evidence/EVD-S04-P03.json"),
        Path("machine/evidence/EVD-S04-P03_rollback.json"),
    ]
    p04_paths = [
        Path("capacity_budget.json"),
        Path("resource_shedding.json"),
        Path("load_baseline.json"),
        Path("tests/S04/P04_test.py"),
        Path("machine/tests/fixtures/S04_P04.json"),
        Path("machine/evidence/EVD-S04-P04.json"),
        Path("machine/evidence/EVD-S04-P04_rollback.json"),
    ]
    candidate_present = [path.as_posix() for path in candidate_paths if (root / path).exists()]
    signed_present = [path.as_posix() for path in signed_paths if (root / path).exists()]
    p04_present = [path.as_posix() for path in p04_paths if (root / path).exists()]
    rows = _load_index(root)
    p03 = [row for row in rows if row.get("id") == "INDEX-AC-S04-P03"]
    p04 = [row for row in rows if row.get("id") == "INDEX-AC-S04-P04"]
    p03_planned = len(p03) == 1 and p03[0].get("status") == "PLANNED" and "actual_artifact" not in p03[0] and "artifact_sha256" not in p03[0]
    p03_signed = len(p03) == 1 and p03[0].get("status") == "PASS"
    p04_planned = not p04_present and len(p04) == 1 and p04[0].get("status") == "PLANNED" and "actual_artifact" not in p04[0] and "artifact_sha256" not in p04[0]
    successor: Dict[str, Any] = {}
    mode = "INVALID_PARTIAL_S04_P03_SUCCESSOR"
    if not candidate_present and not signed_present and p03_planned:
        progression_ok = True
        mode = "S04_P03_NOT_STARTED"
    elif len(candidate_present) == len(candidate_paths) and not signed_present and p03_planned:
        successor = _p03_candidate_contract(root)
        progression_ok = successor.get("status") == "PASS"
        mode = "VERIFIED_S04_P03_CANDIDATE" if progression_ok else "INVALID_S04_P03_CANDIDATE"
    elif len(candidate_present) == len(candidate_paths) and len(signed_present) == len(signed_paths) and p03_signed:
        candidate = _p03_candidate_contract(root)
        signed = _p03_signed_contract(root, p03[0])
        successor = {"candidate": candidate, "signed": signed}
        progression_ok = candidate.get("status") == "PASS" and signed.get("status") == "PASS"
        mode = "VERIFIED_S04_P03_SIGNED_SUCCESSOR" if progression_ok else "INVALID_S04_P03_SIGNED_SUCCESSOR"
    else:
        progression_ok = False
    progression_ok = progression_ok and p04_planned
    _add(checks, "S04P02-P03-PROGRESSION", progression_ok, {"mode": mode, "candidate_present": candidate_present, "signed_present": signed_present, "p03_index": p03, "p04_present": p04_present, "p04_index": p04, "successor": successor})


def _check_no_leaks(root: Path, checks: List[Dict[str, Any]]) -> None:
    paths = [CONFIG_PATH, POLICY_PATH, DEGRADED_PAGE_PATH, FIXTURE_PATH, TEST_PATH, Path("abd_acceptance/cloudflare_edge.py")]
    leaks: List[Dict[str, str]] = []
    for relative in paths:
        path = root / relative
        if not path.is_file():
            leaks.append({"path": relative.as_posix(), "kind": "missing"})
            continue
        text = path.read_text(encoding="utf-8", errors="replace")
        if any(pattern.search(text) for pattern in SECRET_PATTERNS):
            leaks.append({"path": relative.as_posix(), "kind": "secret-pattern"})
        if any(fragment in text for fragment in LOCAL_PATH_FRAGMENTS):
            leaks.append({"path": relative.as_posix(), "kind": "absolute-local-path"})
    _add(checks, "S04P02-NO-SECRET-OR-LOCAL-PATH", not leaks, leaks or "none")


def _junit_summary(path: Path) -> Dict[str, int]:
    root = ET.parse(str(path)).getroot()
    suites = [root] if root.tag == "testsuite" else list(root.findall("testsuite"))
    return {key: sum(int(suite.attrib.get(key, "0")) for suite in suites) for key in ("tests", "failures", "errors", "skipped")}


def _junit_is_normalized(path: Path) -> bool:
    root = ET.parse(str(path)).getroot()
    suites = [root] if root.tag == "testsuite" else list(root.findall("testsuite"))
    return all(suite.attrib.get("timestamp") == JUNIT_FIXED_CLOCK and suite.attrib.get("time") == "0.000" for suite in suites)


def _check_external_reports(root: Path, fixture: Mapping[str, Any], checks: List[Dict[str, Any]], hashes: MutableMapping[str, str]) -> None:
    for check_id, relative, minimum in [
        ("S04P02-TARGETED-PYTEST", JUNIT_PATH, int(fixture.get("minimum_targeted_pytest_cases", 0))),
        ("S04P02-FULL-REGRESSION", FULL_JUNIT_PATH, int(fixture.get("minimum_full_pytest_cases", 0))),
    ]:
        try:
            summary = _junit_summary(root / relative)
            ok = summary["tests"] >= minimum and summary["failures"] == 0 and summary["errors"] == 0 and _junit_is_normalized(root / relative)
            _add(checks, check_id, ok, summary)
            hashes[relative.as_posix()] = sha256_file(root / relative)
        except Exception as exc:
            _add(checks, check_id, False, "%s: %s" % (type(exc).__name__, exc))
    try:
        report = strict_json_load(root / PACK_REPORT_PATH)
        summary = report.get("summary", {})
        ok = report.get("status") == "PASS" and summary.get("checks") == 49 and summary.get("passed") == 49 and summary.get("failed") == 0
        _add(checks, "S04P02-TASKPACK-49-PASS", ok, summary)
        hashes[PACK_REPORT_PATH.as_posix()] = sha256_file(root / PACK_REPORT_PATH)
    except Exception as exc:
        _add(checks, "S04P02-TASKPACK-49-PASS", False, "%s: %s" % (type(exc).__name__, exc))
    try:
        text = (root / SCAN_REPORT_PATH).read_text(encoding="utf-8")
        required = {"STATUS: PASS", "MAX_INCREMENTAL_CASH_AUD: 0.00", "PAID_OR_UNKNOWN_DEPENDENCIES: 0", "EXTERNAL_NETWORK_ACCESS_PERFORMED: false", "EXTERNAL_ACCOUNT_OR_BILLING_ACCESS_PERFORMED: false"}
        _add(checks, "S04P02-PAID-DEPENDENCY-SCAN", required.issubset(set(text.splitlines())), text.splitlines()[:10])
        hashes[SCAN_REPORT_PATH.as_posix()] = sha256_file(root / SCAN_REPORT_PATH)
    except Exception as exc:
        _add(checks, "S04P02-PAID-DEPENDENCY-SCAN", False, "%s: %s" % (type(exc).__name__, exc))


def evaluate_contract(root: Path, require_external_reports: bool = False, *, _verify_git_history: bool = True) -> Dict[str, Any]:
    root = root.resolve()
    checks: List[Dict[str, Any]] = []
    hashes: Dict[str, str] = {}
    fixture = _safe_load(root / FIXTURE_PATH, checks, "S04P02-FIXTURE-STRICT-JSON")
    config = _safe_load(root / CONFIG_PATH, checks, "S04P02-CONFIG-STRICT-JSON-YAML-SUBSET")
    try:
        policy = parse_access_policy((root / POLICY_PATH).read_text(encoding="utf-8"))
        _add(checks, "S04P02-POLICY-STRICT-JSON-BLOCK", True, POLICY_PATH.as_posix())
    except Exception as exc:
        policy = None
        _add(checks, "S04P02-POLICY-STRICT-JSON-BLOCK", False, "%s: %s" % (type(exc).__name__, exc))
    try:
        page = (root / DEGRADED_PAGE_PATH).read_text(encoding="utf-8")
        _add(checks, "S04P02-DEGRADED-PAGE-UTF8", True, DEGRADED_PAGE_PATH.as_posix())
    except Exception as exc:
        page = ""
        _add(checks, "S04P02-DEGRADED-PAGE-UTF8", False, "%s: %s" % (type(exc).__name__, exc))
    _check_pins(root, checks, hashes)
    if isinstance(fixture, Mapping) and isinstance(config, Mapping) and isinstance(policy, Mapping) and page:
        _check_taskpack(root, fixture, checks)
        _check_sources(fixture, checks)
        try:
            predecessor = verify_infrastructure_iac_evidence(root, verify_git_history=_verify_git_history)
            predecessor_ok = predecessor.get("status") == "PASS" and predecessor.get("decision") == "S04_P01_EVIDENCE_VERIFIED" and predecessor.get("next") == "S04/P02_READY_NOT_STARTED"
            _add(checks, "S04P02-P01-PREREQUISITE", predecessor_ok, predecessor.get("summary"))
        except Exception as exc:
            _add(checks, "S04P02-P01-PREREQUISITE", False, "%s: %s" % (type(exc).__name__, exc))
        _check_artifacts(root, fixture, config, policy, page, checks)
        _check_progression(root, checks)
        _check_no_leaks(root, checks)
        canonical = strict_json_load(root / "machine/facts/canonical_facts.json")
        costs = strict_json_load(root / "machine/facts/costs.json")
        parameters = strict_json_load(root / "machine/facts/parameters.json")
        product = canonical.get("product", {})
        baseline_ok = product.get("initial_bankroll_aud") == "300.00" and product.get("incremental_cash_budget_aud") == "0.00" and product.get("monthly_target_return") == "0.30" and canonical.get("scope", {}).get("order_submission_module_present") is False and parameters.get("target_30pct", {}).get("guaranteed") is False and set(costs.get("incremental_cash_budget", {}).values()) == {"0.00"}
        _add(checks, "S04P02-A300-A0-NO-ORDER-NO-GUARANTEE", baseline_ok, {"product": product, "target": parameters.get("target_30pct")})
        _add(checks, "S04P02-EXTERNAL-EFFECT-BOUNDARY", EXTERNAL_EFFECT_BOUNDARY == fixture.get("expected_external_effect_boundary"), EXTERNAL_EFFECT_BOUNDARY)
        _add(checks, "S04P02-NO-FLOAT", not _contains_float(fixture) and not _contains_float(config) and not _contains_float(policy), "all frozen numeric values avoid binary floats")
        if require_external_reports:
            _check_external_reports(root, fixture, checks, hashes)
    else:
        _add(checks, "S04P02-INPUTS-AVAILABLE", False, "fixture, config, policy or degraded page unavailable")
    minimum = int(fixture.get("minimum_oracle_checks", 0)) if isinstance(fixture, Mapping) else 0
    if len(checks) < minimum:
        _add(checks, "S04P02-ORACLE-CHECK-COUNT-MINIMUM", False, {"actual": len(checks), "minimum": minimum})
    failed = [row["id"] for row in checks if not row["passed"]]
    status = "PASS" if not failed else "FAIL"
    return {
        "schema_version": "1.0.0",
        "contract_id": CONTRACT_ID,
        "requirement_id": REQUIREMENT_ID,
        "stage_id": STAGE_ID,
        "phase_id": PHASE_ID,
        "product_version": VERSION,
        "fixed_clock": FIXED_CLOCK,
        "status": status,
        "decision": "OUTBOUND_ONLY_EDGE_CONFIGURATION_CONTRACT_FROZEN" if status == "PASS" else "EDGE_CONFIGURATION_BLOCKED_FAIL_CLOSED",
        "phase_status": "S04_P02_PASS" if status == "PASS" else "S04_P02_FAIL",
        "summary": {"checks": len(checks), "passed": len(checks) - len(failed), "failed": len(failed), "failed_check_ids": failed},
        "checks": checks,
        "hashes": hashes,
        "pass_gate_interpretation": "OFFLINE_CONFIGURATION_PROVES_NO_PUBLIC_BUSINESS_INBOUND_REQUIRED; RUNTIME_ACCESS_REMAINS_UNVERIFIED",
        "activation_gate": "BLOCKED_EXTERNAL_PREREQUISITES_NOT_VERIFIED",
        "production_status": "NOT_DEPLOYED_OR_ACTIVATED",
        "runtime_access_status": "NOT_EXECUTED_OR_VERIFIED",
        "release_status": "NOT_READY_S04_P03_TO_P04_AND_STAGE_REVIEW_REQUIRED",
        "financial_target_status": "UNVERIFIED_NOT_GUARANTEED",
        "external_effect_boundary": EXTERNAL_EFFECT_BOUNDARY,
        "next": "S04/P03_READY_NOT_STARTED" if status == "PASS" else "S04/P02_REMEDIATION_REQUIRED",
    }


def perform_rollback_drill(root: Path) -> Dict[str, Any]:
    root = root.resolve()
    artifacts = [CONFIG_PATH, POLICY_PATH, DEGRADED_PAGE_PATH, FIXTURE_PATH, TEST_PATH, Path("abd_acceptance/cloudflare_edge.py")]
    results: Dict[str, Any] = {}
    with tempfile.TemporaryDirectory(prefix="abd-s04-p02-rollback-") as temporary:
        base = Path(temporary)
        for relative in artifacts:
            source = root / relative
            original = source.read_bytes()
            target = base / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(original)
            signed = _sha256_bytes(original)
            target.write_bytes(original + b"\nCORRUPTED")
            corrupted = sha256_file(target)
            target.write_bytes(original)
            restored = sha256_file(target)
            results[relative.as_posix()] = {"signed_sha256": signed, "corrupted_sha256": corrupted, "restored_sha256": restored, "status": "PASS" if signed == restored and corrupted != signed else "FAIL"}
    status = "PASS" if all(row["status"] == "PASS" for row in results.values()) else "FAIL"
    return {
        "schema_version": "1.0.0",
        "evidence_id": "EVD-S04-P02-ROLLBACK",
        "contract_id": CONTRACT_ID,
        "fixed_clock": FIXED_CLOCK,
        "mode": "EPHEMERAL_EDGE_ARTIFACT_RESTORE",
        "status": status,
        "artifacts": results,
        "production_state_changed": False,
        "external_state_changed": False,
    }


def build_evidence(root: Path, require_external_reports: bool = True, *, _verify_git_history: bool = True) -> tuple[Dict[str, Any], Dict[str, Any]]:
    root = root.resolve()
    validation = evaluate_contract(root, require_external_reports, _verify_git_history=_verify_git_history)
    rollback = perform_rollback_drill(root)
    if rollback["status"] != "PASS":
        validation = deepcopy(validation)
        validation["status"] = "FAIL"
        validation["decision"] = "EDGE_CONFIGURATION_BLOCKED_FAIL_CLOSED"
        validation["phase_status"] = "S04_P02_FAIL"
        validation["next"] = "S04/P02_REMEDIATION_REQUIRED"
    inputs: Dict[str, str] = {}
    for relative in sorted({*PINNED_BASELINE_HASHES, *PINNED_PHASE_HASHES, "abd_acceptance/cloudflare_edge.py"}):
        inputs[relative] = sha256_file(root / relative)
    for relative in PINNED_REPO_HASHES:
        inputs[relative] = sha256_file(root.parent / relative)
    evidence = {
        "schema_version": "1.0.0",
        "evidence_id": "EVD-S04-P02",
        "contract_id": CONTRACT_ID,
        "requirement_id": REQUIREMENT_ID,
        "stage_id": STAGE_ID,
        "phase_id": PHASE_ID,
        "product_version": VERSION,
        "fixed_clock": FIXED_CLOCK,
        "status": validation["status"],
        "decision": validation["decision"],
        "phase_status": validation["phase_status"],
        "artifacts": strict_json_load(root / FIXTURE_PATH)["expected_artifacts"],
        "validation": validation,
        "replay_proof": {
            "mode": "DETERMINISTIC_OFFLINE_EDGE_BUNDLE_MATERIALIZATION",
            "production_activation_performed": False,
            "runtime_access_verified": False,
            "activation_gate": validation["activation_gate"],
        },
        "scope_boundary": {
            "p02_delivers_configuration_contract_not_account_configuration": True,
            "p03_activation_not_started": True,
            "cloudflare_account_dns_access_and_tunnel_not_inspected_or_changed": True,
            "ovh_host_and_firewall_not_accessed_or_changed": True,
            "mainland_china_acceleration_availability_or_reach_not_claimed": True,
            "ordinary_global_chinese_access_not_runtime_verified": True,
        },
        "external_effect_boundary": EXTERNAL_EFFECT_BOUNDARY,
        "hashes": {
            "inputs": inputs,
            "parameters": sha256_file(root / "machine/facts/parameters.json"),
            "model": sha256_file(root / "machine/facts/model_system_card.json"),
            "model_not_executed_reason": "S04/P02 validates an offline Cloudflare edge configuration contract; it executes no model, network, account, host, DNS, tunnel, Access policy, order or return evaluation.",
            "code": _current_code_hash(root),
            "rollback_evidence": _sha256_bytes(_json_bytes(rollback)),
        },
        "pass_gate_interpretation": validation["pass_gate_interpretation"],
        "production_status": validation["production_status"],
        "runtime_access_status": validation["runtime_access_status"],
        "release_status": validation["release_status"],
        "financial_target_status": validation["financial_target_status"],
        "next": validation["next"],
    }
    unsigned = deepcopy(evidence)
    evidence["decision_sha256"] = _sha256_bytes(_json_bytes(unsigned))
    return evidence, rollback


def _atomic_write(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + ".tmp")
    temporary.write_bytes(data)
    temporary.replace(path)


def _update_evidence_index(root: Path, status: str, artifact_sha256: str) -> None:
    rows = _load_index(root)
    matching = [row for row in rows if row.get("id") == "INDEX-AC-S04-P02"]
    if len(matching) != 1:
        raise CloudflareEdgeContractError("expected exactly one INDEX-AC-S04-P02 row")
    matching[0].update({
        "status": status,
        "actual_artifact": EVIDENCE_PATH.as_posix(),
        "artifact_sha256": artifact_sha256,
        "verified_at": FIXED_CLOCK,
        "next": "S04/P03_READY_NOT_STARTED" if status == "PASS" else "S04/P02_REMEDIATION_REQUIRED",
    })
    _atomic_write(root / EVIDENCE_INDEX_PATH, "".join(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n" for row in rows).encode("utf-8"))


def write_phase_evidence(root: Path, evidence_dir: Path) -> Dict[str, Any]:
    root = root.resolve()
    evidence_dir = evidence_dir.resolve()
    try:
        evidence_dir.relative_to(root)
    except ValueError as exc:
        raise CloudflareEdgeContractError("evidence directory must be inside the ABD project root") from exc
    evidence, rollback = build_evidence(root, require_external_reports=True)
    evidence_path = evidence_dir / EVIDENCE_PATH.name
    rollback_path = evidence_dir / ROLLBACK_EVIDENCE_PATH.name
    _atomic_write(rollback_path, _json_bytes(rollback))
    _atomic_write(evidence_path, _json_bytes(evidence))
    evidence_hash = sha256_file(evidence_path)
    _update_evidence_index(root, evidence["status"], evidence_hash)
    return {"contract_id": CONTRACT_ID, "status": evidence["status"], "evidence_path": evidence_path.relative_to(root).as_posix(), "evidence_sha256": evidence_hash, "next": evidence["next"]}


def _decision_hash_matches(evidence: Mapping[str, Any]) -> bool:
    unsigned = deepcopy(dict(evidence))
    expected = unsigned.pop("decision_sha256", None)
    return isinstance(expected, str) and expected == _sha256_bytes(_json_bytes(unsigned))


def verify_existing_phase_evidence(root: Path, *, verify_git_history: bool = True) -> Dict[str, Any]:
    root = root.resolve()
    checks: List[Dict[str, Any]] = []
    evidence = _safe_load(root / EVIDENCE_PATH, checks, "S04P02-RECEIPT-EVIDENCE-STRICT-JSON")
    rollback = _safe_load(root / ROLLBACK_EVIDENCE_PATH, checks, "S04P02-RECEIPT-ROLLBACK-STRICT-JSON")
    evidence_hash = sha256_file(root / EVIDENCE_PATH) if (root / EVIDENCE_PATH).is_file() else "MISSING"
    rollback_hash = sha256_file(root / ROLLBACK_EVIDENCE_PATH) if (root / ROLLBACK_EVIDENCE_PATH).is_file() else "MISSING"
    if isinstance(evidence, Mapping):
        shape_ok = evidence.get("schema_version") == "1.0.0" and evidence.get("evidence_id") == "EVD-S04-P02" and evidence.get("contract_id") == CONTRACT_ID and evidence.get("requirement_id") == REQUIREMENT_ID and evidence.get("stage_id") == STAGE_ID and evidence.get("phase_id") == PHASE_ID and evidence.get("fixed_clock") == FIXED_CLOCK and evidence.get("status") == "PASS" and evidence.get("decision") == "OUTBOUND_ONLY_EDGE_CONFIGURATION_CONTRACT_FROZEN" and evidence.get("phase_status") == "S04_P02_PASS" and evidence.get("next") == "S04/P03_READY_NOT_STARTED" and _decision_hash_matches(evidence)
        _add(checks, "S04P02-RECEIPT-INTEGRITY", shape_ok, evidence.get("status"))
        validation = evidence.get("validation", {})
        validation_ok = isinstance(validation, Mapping) and validation.get("status") == "PASS" and validation.get("summary", {}).get("failed") == 0 and validation.get("next") == "S04/P03_READY_NOT_STARTED" and all(row.get("passed") is True for row in validation.get("checks", []))
        _add(checks, "S04P02-RECEIPT-VALIDATION-ALL-PASS", validation_ok, validation.get("summary") if isinstance(validation, Mapping) else validation)
        input_errors: List[Dict[str, str]] = []
        for relative, expected in evidence.get("hashes", {}).get("inputs", {}).items():
            candidate = Path(relative)
            if candidate.is_absolute() or ".." in candidate.parts:
                input_errors.append({"path": relative, "actual": "UNSAFE_PATH"})
                continue
            path = root.parent / candidate if relative.startswith(".github/") else root / candidate
            actual = sha256_file(path) if path.is_file() else "MISSING"
            if actual != expected and not _historical_file_matches(root, relative, expected, verify_git_history):
                input_errors.append({"path": relative, "expected": expected, "actual": actual})
        _add(checks, "S04P02-RECEIPT-SIGNED-INPUTS-CURRENT", not input_errors, input_errors or "all inputs match current files or the exact signed phase commit")
        current_code = _current_code_hash(root)
        code_expected = evidence.get("hashes", {}).get("code")
        code_historical = _historical_code_hash(root, verify_git_history) if code_expected != current_code else current_code
        code_ok = code_expected == current_code or (code_expected == PINNED_PHASE_CODE_HASH and code_historical in {PINNED_PHASE_CODE_HASH, "UNVERIFIED_UNIT_TEST_HISTORY"})
        _add(checks, "S04P02-RECEIPT-CODE-HASH-CURRENT", code_ok, {"expected": code_expected, "current": current_code, "historical": code_historical})
        _add(checks, "S04P02-RECEIPT-ROLLBACK-HASH-BINDING", evidence.get("hashes", {}).get("rollback_evidence") == rollback_hash, {"expected": evidence.get("hashes", {}).get("rollback_evidence"), "actual": rollback_hash})
        boundary_ok = evidence.get("external_effect_boundary") == EXTERNAL_EFFECT_BOUNDARY and evidence.get("production_status") == "NOT_DEPLOYED_OR_ACTIVATED" and evidence.get("runtime_access_status") == "NOT_EXECUTED_OR_VERIFIED"
        _add(checks, "S04P02-RECEIPT-BOUNDARY", boundary_ok, evidence.get("external_effect_boundary"))
    else:
        for check_id in ["S04P02-RECEIPT-INTEGRITY", "S04P02-RECEIPT-VALIDATION-ALL-PASS", "S04P02-RECEIPT-SIGNED-INPUTS-CURRENT", "S04P02-RECEIPT-CODE-HASH-CURRENT", "S04P02-RECEIPT-ROLLBACK-HASH-BINDING", "S04P02-RECEIPT-BOUNDARY"]:
            _add(checks, check_id, False, "evidence unavailable")
    rollback_ok = isinstance(rollback, Mapping) and rollback.get("evidence_id") == "EVD-S04-P02-ROLLBACK" and rollback.get("contract_id") == CONTRACT_ID and rollback.get("fixed_clock") == FIXED_CLOCK and rollback.get("status") == "PASS" and rollback.get("production_state_changed") is False and rollback.get("external_state_changed") is False and len(rollback.get("artifacts", {})) == 6 and all(row.get("status") == "PASS" for row in rollback.get("artifacts", {}).values())
    _add(checks, "S04P02-RECEIPT-ROLLBACK-INTEGRITY", rollback_ok, rollback.get("status") if isinstance(rollback, Mapping) else "unavailable")
    try:
        matching = [row for row in _load_index(root) if row.get("id") == "INDEX-AC-S04-P02"]
        index_ok = len(matching) == 1 and matching[0].get("status") == "PASS" and matching[0].get("actual_artifact") == EVIDENCE_PATH.as_posix() and matching[0].get("artifact_sha256") == evidence_hash and matching[0].get("next") == "S04/P03_READY_NOT_STARTED"
        _add(checks, "S04P02-RECEIPT-EVIDENCE-INDEX-BINDING", index_ok, matching)
    except Exception as exc:
        _add(checks, "S04P02-RECEIPT-EVIDENCE-INDEX-BINDING", False, "%s: %s" % (type(exc).__name__, exc))
    try:
        predecessor = verify_infrastructure_iac_evidence(root, verify_git_history=verify_git_history)
        _add(checks, "S04P02-RECEIPT-P01-PREREQUISITE", predecessor.get("status") == "PASS", predecessor.get("summary"))
    except Exception as exc:
        _add(checks, "S04P02-RECEIPT-P01-PREREQUISITE", False, "%s: %s" % (type(exc).__name__, exc))
    _check_progression(root, checks)
    failed = [row["id"] for row in checks if not row["passed"]]
    return {
        "schema_version": "1.0.0",
        "contract_id": CONTRACT_ID,
        "status": "PASS" if not failed else "FAIL",
        "decision": "S04_P02_EVIDENCE_VERIFIED" if not failed else "S04_P02_EVIDENCE_INVALID_FAIL_CLOSED",
        "summary": {"checks": len(checks), "passed": len(checks) - len(failed), "failed": len(failed), "failed_check_ids": failed},
        "checks": checks,
        "evidence_path": EVIDENCE_PATH.as_posix(),
        "evidence_sha256": evidence_hash,
        "rollback_sha256": rollback_hash,
        "next": "S04/P03_READY_NOT_STARTED" if not failed else "S04/P02_REMEDIATION_REQUIRED",
    }
