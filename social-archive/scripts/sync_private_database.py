from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any

from social_archive.config import Settings
from social_archive.db import RuntimeStore
from social_archive.private_facts import (
    PRIVATE_DATABASE_EVENT,
    completed_content_facts,
    fact_bytes,
    fact_sha256,
)
from social_archive.utils import read_secret, redact, sha256_file, utcnow


PRIVATE_DATABASE_AREA = "Private-MetaDatabase"
PRIVATE_DATABASE_DOMAIN = "SocialArchive"
_VERIFY_SUMMARY = re.compile(
    r"Private-MetaDatabase:\s*账本\s*(?P<total>\d+)\s*条，\s*对象在仓\s*(?P<present>\d+)\s*，\s*缺\s*(?P<missing>\d+)",
)
_SHA256 = re.compile(r"^[0-9a-f]{64}$")


def _private_database_client() -> tuple[Path | None, str | None]:
    raw = os.getenv("SOCIAL_ARCHIVE_PRIVATE_DB_CLIENT", "").strip()
    if not raw:
        return None, "缺少 SOCIAL_ARCHIVE_PRIVATE_DB_CLIENT；禁止回退到本地 Private-Database 工作树"
    candidate = Path(raw).expanduser()
    try:
        client = candidate.resolve(strict=True)
    except OSError:
        return None, "配置的 Private-Database API client 不存在"
    if not client.is_file() or client.name != "private_db_client.py":
        return None, "Private-Database API client 必须是可读的 private_db_client.py"
    return client, None


def _private_database_github_environment() -> tuple[dict[str, str] | None, str | None]:
    """Build a process-local GitHub environment from the dedicated credential.

    The official client shells out to ``gh``.  A systemd credential is a file,
    not a token value, so it must be read only by this short-lived process and
    passed as ``GH_TOKEN`` to its child.  The Vault-only archive token is never
    a fallback for the Private-Database facts authority.
    """
    token_file = os.getenv("SOCIAL_ARCHIVE_PRIVATE_DB_TOKEN_FILE", "").strip()
    if not token_file:
        return None, "缺少 SOCIAL_ARCHIVE_PRIVATE_DB_TOKEN_FILE；禁止复用 GitHub Vault 凭据"
    try:
        token = read_secret(token_file)
    except (OSError, UnicodeError):
        return None, "Private-Database Token 文件不可读或权限不符合合同"
    if not token:
        return None, "Private-Database Token 文件为空或不存在"
    environment = dict(os.environ)
    environment.pop("GITHUB_TOKEN", None)
    environment["GH_TOKEN"] = token
    return environment, None


def _run_client(client: Path, argv: list[str]) -> tuple[int, str]:
    environment, credential_error = _private_database_github_environment()
    if credential_error or environment is None:
        return 3, credential_error or "Private-Database Token 不可用"
    result = subprocess.run(
        [sys.executable, str(client), *argv],
        cwd=client.parent,
        text=True,
        capture_output=True,
        check=False,
        env=environment,
    )
    detail = redact((result.stderr or result.stdout or "").strip()[-500:])
    return int(result.returncode), detail


def _verify_summary_counts(output: str) -> tuple[int, int, int] | None:
    """Return the official client's ledger counts when its summary is parseable."""
    match = _VERIFY_SUMMARY.search(output)
    if not match:
        return None
    total = int(match.group("total"))
    present = int(match.group("present"))
    missing = int(match.group("missing"))
    return total, present, missing


def _verify_summary_is_complete(output: str) -> bool:
    """Reject incomplete or malformed results from the official verifier."""
    counts = _verify_summary_counts(output)
    if counts is None:
        return False
    total, present, missing = counts
    return total > 0 and missing == 0 and total == present


def _normalized_manifest_object_path(entry: dict[str, Any]) -> tuple[str, bool]:
    """Validate one immutable ledger row and normalize its legacy path form.

    The canonical client stores ``objects/<sha-prefix>/<sha>_<name>``. Five
    historical EEI rows instead stored the same path prefixed with their area.
    The prefix is a read compatibility issue, not a second authority: require
    the full content-addressed shape before accepting either representation.
    """
    digest = entry.get("sha256")
    name = entry.get("original_name")
    raw_path = entry.get("object_path")
    size = entry.get("size_bytes")
    if not isinstance(digest, str) or not _SHA256.fullmatch(digest):
        raise ValueError("manifest sha256 非法")
    if not isinstance(name, str) or not name or Path(name).name != name or "/" in name or "\\" in name:
        raise ValueError("manifest original_name 非法")
    if not isinstance(raw_path, str):
        raise ValueError("manifest object_path 非法")
    if not isinstance(size, int) or isinstance(size, bool) or size < 0:
        raise ValueError("manifest size_bytes 非法")

    area_prefix = f"{PRIVATE_DATABASE_AREA}/"
    if raw_path.startswith("objects/"):
        relative = raw_path
        legacy_prefixed = False
    elif raw_path.startswith(f"{area_prefix}objects/"):
        relative = raw_path[len(area_prefix):]
        legacy_prefixed = True
    else:
        raise ValueError("manifest object_path 不属于允许的内容寻址路径")

    expected = f"objects/{digest[:2]}/{digest}_{name}"
    if relative != expected:
        raise ValueError("manifest object_path 与 sha256/original_name 不一致")
    return relative, legacy_prefixed


def _verify_legacy_prefixed_manifest(client: Path, verify_output: str) -> tuple[bool, str]:
    """Strictly read back only legacy-prefixed rows rejected by an old verifier.

    The official client already verifies canonical relative rows. This fallback
    activates only when its own count summary exactly matches the historical
    prefix mismatch, then fetches each affected object through that same
    clone-free client and checks both byte length and SHA-256.
    """
    counts = _verify_summary_counts(verify_output)
    if counts is None:
        return False, "Private-Database verify 未给出可解析账本摘要"
    total, present, missing = counts
    if total <= 0 or missing <= 0 or total != present + missing:
        return False, "Private-Database verify 账本计数不自洽"

    with tempfile.TemporaryDirectory(prefix="social-archive-private-db-verify-") as temp_dir:
        root = Path(temp_dir)
        manifest = root / "manifest.jsonl"
        code, detail = _run_client(
            client,
            ["get", PRIVATE_DATABASE_AREA, "manifest.jsonl", str(manifest)],
        )
        if code or not manifest.is_file() or manifest.is_symlink():
            return False, detail or "无法只读取得 Private-Database manifest"

        try:
            entries = [
                json.loads(line)
                for line in manifest.read_text(encoding="utf-8").splitlines()
                if line.strip()
            ]
        except (OSError, json.JSONDecodeError) as exc:
            return False, redact(f"Private-Database manifest 不可解析：{exc}")
        if len(entries) != total or not all(isinstance(entry, dict) for entry in entries):
            return False, "Private-Database manifest 条数或行类型与官方摘要不一致"

        relative_count = 0
        legacy_entries: list[tuple[str, str, int]] = []
        seen_paths: set[str] = set()
        seen_digests: set[str] = set()
        try:
            for entry in entries:
                relative, legacy_prefixed = _normalized_manifest_object_path(entry)
                digest = str(entry["sha256"])
                size = int(entry["size_bytes"])
                if relative in seen_paths or digest in seen_digests:
                    raise ValueError("manifest 存在重复内容寻址对象")
                seen_paths.add(relative)
                seen_digests.add(digest)
                if legacy_prefixed:
                    legacy_entries.append((relative, digest, size))
                else:
                    relative_count += 1
        except (KeyError, TypeError, ValueError) as exc:
            return False, redact(f"Private-Database manifest 合同不成立：{exc}")

        if relative_count != present or len(legacy_entries) != missing:
            return False, "Private-Database legacy 路径数量与官方摘要不一致"

        for index, (relative, digest, size) in enumerate(legacy_entries):
            object_file = root / f"legacy-object-{index}.bin"
            code, detail = _run_client(
                client,
                ["get", PRIVATE_DATABASE_AREA, relative, str(object_file)],
            )
            if code or not object_file.is_file() or object_file.is_symlink():
                return False, detail or "无法读回 legacy 内容寻址对象"
            if object_file.stat().st_size != size:
                return False, "legacy 内容寻址对象字节数与 manifest 不一致"
            if sha256_file(object_file) != digest:
                return False, "legacy 内容寻址对象 SHA-256 与 manifest 不一致"

    return True, (
        f"Private-Database legacy manifest 兼容核验通过：账本 {total} 条，"
        f"canonical {relative_count} 条，历史前缀对象 {len(legacy_entries)} 条均已读回并核哈希"
    )


def _blocked(message: str, *, error_code: str = "PRIVATE_DATABASE_CLIENT_UNAVAILABLE") -> int:
    print(json.dumps({
        "schema_version": "1.0",
        "generated_at": utcnow(),
        "status": "BLOCKED_ENVIRONMENT",
        "error_code": error_code,
        "message": message,
    }, ensure_ascii=False))
    return 3


def _dry_run(store: RuntimeStore, *, limit: int) -> int:
    facts = completed_content_facts(store, limit=limit)
    delivered = 0
    for fact in facts:
        event = store.get_outbox_event(
            event_type=PRIVATE_DATABASE_EVENT,
            aggregate_id=str(fact["content"]["id"]),
            payload_sha256=fact_sha256(fact),
        )
        delivered += int(bool(event and event.get("status") == "delivered"))
    print(json.dumps({
        "schema_version": "1.0",
        "generated_at": utcnow(),
        "status": "READY",
        "dry_run": True,
        "candidate_fact_count": len(facts),
        "already_delivered_count": delivered,
        "pending_count": len(facts) - delivered,
        "transport": "Private-Database API client",
        "local_checkout": False,
    }, ensure_ascii=False))
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Synchronize completed Social Archive facts through the official clone-free Private-Database API client."
    )
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--once", action="store_true", help="run one bounded, idempotent pass")
    parser.add_argument("--limit", type=int, default=100)
    args = parser.parse_args()

    settings = Settings.from_env()
    client, client_error = _private_database_client()
    if client_error or client is None:
        return _blocked(client_error or "Private-Database API client 不可用")

    limit = min(max(args.limit, 1), 1000)
    if args.dry_run:
        if not settings.runtime_db.is_file():
            print(json.dumps({
                "schema_version": "1.0",
                "generated_at": utcnow(),
                "status": "NO_CHANGE",
                "dry_run": True,
                "candidate_fact_count": 0,
                "message": "Runtime Journal 尚未初始化；dry-run 不创建本地状态",
                "transport": "Private-Database API client",
                "local_checkout": False,
            }, ensure_ascii=False))
            return 0
        try:
            return _dry_run(RuntimeStore(settings.runtime_db), limit=limit)
        except Exception as exc:  # noqa: BLE001 - malformed runtime is an environment boundary
            return _blocked(redact(f"Runtime Journal 不可读：{exc}"), error_code="RUNTIME_JOURNAL_UNREADABLE")

    _, credential_error = _private_database_github_environment()
    if credential_error:
        return _blocked(credential_error, error_code="PRIVATE_DATABASE_TOKEN_UNAVAILABLE")

    settings.ensure_directories()
    store = RuntimeStore(settings.runtime_db)
    store.initialize()
    facts = completed_content_facts(store, limit=limit)
    if not facts:
        print(json.dumps({
            "schema_version": "1.0",
            "generated_at": utcnow(),
            "status": "NO_CHANGE",
            "candidate_fact_count": 0,
            "transport": "Private-Database API client",
            "local_checkout": False,
        }, ensure_ascii=False))
        return 0

    pending: list[tuple[dict[str, Any], dict[str, Any]]] = []
    delivered = 0
    for fact in facts:
        event = store.ensure_outbox_event(
            event_type=PRIVATE_DATABASE_EVENT,
            aggregate_id=str(fact["content"]["id"]),
            payload=fact,
        )
        if event.get("status") == "delivered":
            delivered += 1
        else:
            pending.append((fact, event))
    if not pending:
        print(json.dumps({
            "schema_version": "1.0",
            "generated_at": utcnow(),
            "status": "NO_CHANGE",
            "candidate_fact_count": len(facts),
            "already_delivered_count": delivered,
            "transport": "Private-Database API client",
            "local_checkout": False,
        }, ensure_ascii=False))
        return 0

    failures: list[dict[str, str]] = []
    attempted_events: list[dict[str, Any]] = []
    with tempfile.TemporaryDirectory(prefix="social-archive-facts-") as temp_dir:
        temporary_root = Path(temp_dir)
        for fact, event in pending:
            content_id = str(fact["content"]["id"])
            digest = fact_sha256(fact)
            source = temporary_root / f"social-archive-fact-{content_id}-{digest[:12]}.json"
            source.write_bytes(fact_bytes(fact))
            code, detail = _run_client(
                client,
                ["ingest", PRIVATE_DATABASE_AREA, str(source), "--domain", PRIVATE_DATABASE_DOMAIN, "--batch", digest],
            )
            attempted_events.append(event)
            if code:
                store.mark_outbox_failed(str(event["id"]), "PRIVATE_DATABASE_INGEST_FAILED")
                failures.append({"content_id": content_id, "error_code": "PRIVATE_DATABASE_INGEST_FAILED", "detail": detail})

        if not failures:
            code, detail = _run_client(client, ["verify", PRIVATE_DATABASE_AREA])
            if code == 0 and not _verify_summary_is_complete(detail):
                compatible, compatibility_detail = _verify_legacy_prefixed_manifest(client, detail)
                if compatible:
                    detail = compatibility_detail
                else:
                    code = 1
                    detail = compatibility_detail
            if code:
                for event in attempted_events:
                    store.mark_outbox_failed(str(event["id"]), "PRIVATE_DATABASE_VERIFY_FAILED")
                failures.append({"content_id": "*", "error_code": "PRIVATE_DATABASE_VERIFY_FAILED", "detail": detail})
            else:
                for event in attempted_events:
                    store.mark_outbox_delivered(str(event["id"]))
        else:
            for event in attempted_events:
                current = store.get_outbox_event(
                    event_type=PRIVATE_DATABASE_EVENT,
                    aggregate_id=str(event["aggregate_id"]),
                    payload_sha256=str(event["payload_sha256"]),
                )
                if current and current.get("status") != "pending":
                    store.mark_outbox_failed(str(event["id"]), "PRIVATE_DATABASE_BATCH_INCOMPLETE")

    status = "PASS" if not failures else "DEGRADED"
    report = {
        "schema_version": "1.0",
        "generated_at": utcnow(),
        "status": status,
        "candidate_fact_count": len(facts),
        "attempted_fact_count": len(pending),
        "already_delivered_count": delivered,
        "delivered_this_run": len(pending) if status == "PASS" else 0,
        "failures": failures,
        "transport": "Private-Database API client",
        "local_checkout": False,
    }
    print(json.dumps(report, ensure_ascii=False))
    return 0 if status == "PASS" else 4


if __name__ == "__main__":
    raise SystemExit(main())
