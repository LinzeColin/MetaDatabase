#!/usr/bin/env python3
"""Private-Database client — clone-free read/write against the authoritative store.

`LinzeColin/Private-Database` is the single authoritative home for long-term
structured facts across every project. This is MetaDatabase/EEI's implementation
of `Private-Database/PROTOCOL.md` — written to the protocol document rather than
copied from another repo, so nothing here reaches across repository boundaries.

Iron rules enforced here (Private-Database README):
  1. Never clone. Every operation is a single GitHub REST call.
  2. Data only, never code.
  3. Nothing lands locally beyond the file being moved.
  4. Credentials never enter the repo — refused by filename AND by content.
  5. Objects are never overwritten — content-addressed, manifest append-only.
  6. Single file < 95MB (GitHub's hard limit is 100MB).

Usage:
  python -m scripts.private_db_client ingest <zone> <file> --domain EEI [--batch b]
  python -m scripts.private_db_client get    <zone> <object-path> <dest>
  python -m scripts.private_db_client list   <zone> [--prefix objects/]
  python -m scripts.private_db_client exists <zone> <sha256>
"""
from __future__ import annotations

import argparse
import base64
import hashlib
import json
import os
import re
import subprocess
import sys
from pathlib import Path
from typing import Any

REPO = "LinzeColin/Private-Database"
BRANCH = "main"
ZONES = ("Private-KMDatabase", "Private-AgentDatabase", "Private-MetaDatabase")

# Red line 6: GitHub's hard cap is 100MB; the protocol's working ceiling is 95MB.
MAX_FILE_BYTES = 95 * 1024 * 1024

# Red line 4, by filename.
_CREDENTIAL_NAME_RE = re.compile(
    r"(^|[._-])(env|key|pem|p12|pfx|token|secret|secrets|credential|credentials|"
    r"cookie|cookies|id_rsa|id_ed25519)($|[._-])",
    re.I,
)
# Red line 4, by content. Deliberately broad: a false positive costs one manual
# look, a false negative puts a live credential in a repo forever (git remembers
# even after a delete).
_CREDENTIAL_CONTENT_RES = tuple(
    re.compile(p, re.I)
    for p in (
        rb"-----BEGIN [A-Z ]*PRIVATE KEY-----",
        rb"\baws_secret_access_key\b",
        rb"\bAKIA[0-9A-Z]{16}\b",
        rb"\bghp_[A-Za-z0-9]{30,}\b",
        rb"\bgithub_pat_[A-Za-z0-9_]{30,}\b",
        rb"\bxox[baprs]-[A-Za-z0-9-]{10,}\b",
        rb"\bsk-[A-Za-z0-9]{32,}\b",
        rb"\bnskey_live_[A-Za-z0-9]{10,}\b",
        rb"\bBearer\s+[A-Za-z0-9._-]{24,}",
    )
)
# The store holds facts, not databases: a SQLite file is runtime state that
# belongs on the compute node (rebuildable) or in R2 (cold), never here.
_REFUSED_SUFFIXES = (".sqlite", ".sqlite3", ".db", ".pem", ".key", ".p12", ".pfx")


class PrivateDbError(RuntimeError):
    pass


def _gh(args: list[str], *, stdin: str | None = None, raw: bool = False) -> Any:
    proc = subprocess.run(
        ["gh", "api", *args],
        input=stdin,
        capture_output=True,
        text=not raw,
        check=False,
    )
    if proc.returncode != 0:
        err = proc.stderr if isinstance(proc.stderr, str) else proc.stderr.decode()
        raise PrivateDbError(f"gh api failed: {err[-400:]}")
    return proc.stdout


def _contents_path(zone: str, path: str) -> str:
    if zone not in ZONES:
        raise PrivateDbError(f"unknown zone {zone!r}; expected one of {ZONES}")
    return f"repos/{REPO}/contents/{zone}/{path.lstrip('/')}"


def check_red_lines(name: str, payload: bytes) -> None:
    """Refuse anything that must never enter the authoritative store."""
    if len(payload) > MAX_FILE_BYTES:
        raise PrivateDbError(
            f"{name}: {len(payload)} bytes exceeds the {MAX_FILE_BYTES} byte ceiling"
            " — shard it, or put the blob in R2 and store only its reference here"
        )
    if name.lower().endswith(_REFUSED_SUFFIXES):
        raise PrivateDbError(
            f"{name}: refused by suffix — databases and key material never enter"
            " the fact store (rebuildable state stays on the compute node; cold"
            " blobs go to R2)"
        )
    if _CREDENTIAL_NAME_RE.search(Path(name).name):
        raise PrivateDbError(f"{name}: refused — filename looks like a credential")
    head = payload[: 2 * 1024 * 1024]
    for pattern in _CREDENTIAL_CONTENT_RES:
        if pattern.search(head):
            raise PrivateDbError(
                f"{name}: refused — content matches a credential signature"
                f" ({pattern.pattern.decode(errors='replace')[:40]})"
            )


def sha256_hex(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def object_path(digest: str, original_name: str) -> str:
    return f"objects/{digest[:2]}/{digest}_{Path(original_name).name}"


def blob_sha(zone: str, path: str) -> str | None:
    """Current blob sha, or None when the path does not exist."""
    try:
        out = _gh([_contents_path(zone, path), "--jq", ".sha"])
    except PrivateDbError as exc:
        if "404" in str(exc) or "Not Found" in str(exc):
            return None
        raise
    return (out or "").strip() or None


def get_object(zone: str, path: str, dest: Path) -> int:
    raw = _gh(
        [_contents_path(zone, path), "-H", "Accept: application/vnd.github.raw"],
        raw=True,
    )
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_bytes(raw)
    return len(raw)


def put_file(zone: str, path: str, payload: bytes, *, message: str) -> dict[str, Any]:
    """Create or overwrite one path. Overwrites carry the old sha (optimistic
    concurrency); a 409 means someone else wrote first — re-read and retry."""
    body: dict[str, Any] = {
        "message": message,
        "content": base64.b64encode(payload).decode("ascii"),
        "branch": BRANCH,
    }
    existing = blob_sha(zone, path)
    if existing:
        body["sha"] = existing
    out = _gh(
        [_contents_path(zone, path), "--method", "PUT", "--input", "-"],
        stdin=json.dumps(body),
    )
    return json.loads(out) if out else {}


def manifest_identity(entry: dict[str, Any]) -> tuple[str, str, str]:
    """What makes two ledger lines the same fact.

    Deliberately excludes `ingested_at` and `batch`: those describe the *run*,
    not the fact. Comparing whole lines would treat a re-ingest one second later
    as new, appending a duplicate line and manufacturing a commit for facts that
    did not change — exactly what the data contract forbids.
    """
    return (
        str(entry.get("sha256", "")),
        str(entry.get("domain", "")),
        str(entry.get("object_path", "")),
    )


def _manifest_has(current: bytes, entry: dict[str, Any]) -> bool:
    wanted = manifest_identity(entry)
    for raw in current.splitlines():
        raw = raw.strip()
        if not raw:
            continue
        try:
            existing = json.loads(raw)
        except json.JSONDecodeError:
            continue  # a hand-edited line must not block an honest append
        if isinstance(existing, dict) and manifest_identity(existing) == wanted:
            return True
    return False


def append_manifest(zone: str, entry: dict[str, Any], *, retries: int = 4) -> bool:
    """Append one line to the zone ledger. Returns True only if a line was
    actually written (i.e. this call created a commit)."""
    line = json.dumps(entry, ensure_ascii=False, sort_keys=True) + "\n"
    for attempt in range(retries):
        try:
            current = b""
            try:
                current = _gh(
                    [
                        _contents_path(zone, "manifest.jsonl"),
                        "-H",
                        "Accept: application/vnd.github.raw",
                    ],
                    raw=True,
                )
            except PrivateDbError as exc:
                if "404" not in str(exc) and "Not Found" not in str(exc):
                    raise
            if _manifest_has(current, entry):
                return False  # already recorded — ingest is idempotent
            put_file(
                zone,
                "manifest.jsonl",
                current + line.encode("utf-8"),
                message=f"manifest: {entry.get('domain', '?')} {entry.get('original_name', '?')}",
            )
            return True
        except PrivateDbError as exc:
            if attempt == retries - 1 or "409" not in str(exc):
                raise
    raise PrivateDbError("manifest append exhausted retries")


def ingest(
    zone: str, source: Path, *, domain: str, batch: str | None = None
) -> dict[str, Any]:
    """The standard write: content-address, upload once, record in the ledger.

    Idempotent by construction — the same bytes always land on the same object
    path, and an already-present object is skipped rather than rewritten.
    """
    payload = source.read_bytes()
    check_red_lines(source.name, payload)
    digest = sha256_hex(payload)
    path = object_path(digest, source.name)

    already = blob_sha(zone, path) is not None
    if not already:
        put_file(zone, path, payload, message=f"ingest: {domain}/{source.name}")

    entry = {
        "sha256": digest,
        "original_name": source.name,
        "size_bytes": len(payload),
        "domain": domain,
        "batch": batch,
        "object_path": f"{zone}/{path}",
        "ingested_at": _utc_now(),
    }
    appended = append_manifest(zone, entry)
    # `skipped_upload` only ever described the object write. The judge for
    # "no new facts => no commit" is `created_commit`: appending a ledger line
    # is a commit too, so an already-present object does not by itself mean
    # this call was a no-op.
    return {
        **entry,
        "uploaded_object": not already,
        "appended_manifest": appended,
        "created_commit": (not already) or appended,
        "skipped_upload": already,
    }


def _utc_now() -> str:
    from datetime import UTC, datetime

    return datetime.now(UTC).replace(microsecond=0).isoformat()


def list_zone(zone: str, prefix: str = "") -> list[dict[str, Any]]:
    out = _gh(
        [
            f"repos/{REPO}/git/trees/{BRANCH}?recursive=1",
            "--jq",
            f'.tree[] | select(.path | startswith("{zone}/{prefix}")) '
            "| {path: .path, size: .size, sha: .sha}",
        ]
    )
    return [json.loads(line) for line in (out or "").splitlines() if line.strip()]


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    sub = p.add_subparsers(dest="cmd", required=True)

    p_ing = sub.add_parser("ingest")
    p_ing.add_argument("zone")
    p_ing.add_argument("file", type=Path)
    p_ing.add_argument("--domain", required=True)
    p_ing.add_argument("--batch", default=None)

    p_get = sub.add_parser("get")
    p_get.add_argument("zone")
    p_get.add_argument("path")
    p_get.add_argument("dest", type=Path)

    p_list = sub.add_parser("list")
    p_list.add_argument("zone")
    p_list.add_argument("--prefix", default="")

    p_ex = sub.add_parser("exists")
    p_ex.add_argument("zone")
    p_ex.add_argument("sha256")
    p_ex.add_argument("--name", default="")

    args = p.parse_args()
    if args.cmd == "ingest":
        print(json.dumps(ingest(args.zone, args.file, domain=args.domain,
                                batch=args.batch), ensure_ascii=False))
    elif args.cmd == "get":
        size = get_object(args.zone, args.path, args.dest)
        print(json.dumps({"path": args.path, "bytes": size, "dest": str(args.dest)}))
    elif args.cmd == "list":
        for row in list_zone(args.zone, args.prefix):
            print(json.dumps(row, ensure_ascii=False))
    elif args.cmd == "exists":
        path = object_path(args.sha256, args.name or args.sha256)
        print(json.dumps({"path": path, "exists": blob_sha(args.zone, path) is not None}))
    return 0


if __name__ == "__main__":
    if not os.environ.get("GH_TOKEN") and not os.environ.get("GITHUB_TOKEN"):
        # gh's own keyring auth also works; this is only a hint, not a gate.
        print("[private-db] note: using gh CLI auth (no GH_TOKEN in env)",
              file=sys.stderr)
    raise SystemExit(main())
