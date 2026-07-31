from __future__ import annotations

import hashlib
import json
import os
import shutil
import subprocess
import tempfile
import urllib.error
import urllib.request
import uuid
from dataclasses import dataclass, asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

from .builtin_skills import PROFILES
from .config import CANONICAL_STOCK_SKILL_SPARSE_PATH, Settings


class RegistryError(RuntimeError):
    pass


@dataclass(frozen=True)
class RuntimeManifest:
    skill_id: str
    display_name: str
    skill_version: str
    runtime_profile: str
    source_repository: str
    source_path: str
    source_commit: str
    source_sha256: str
    lifecycle_state: str = "ACTIVE"
    compatibility_state: str = "BUNDLED_ADAPTER"
    adapter_contract_version: str = "1.0.0"
    horizon_days: int = 20
    lineage: tuple[str, ...] = ()
    engine: str = "builtin_v1"

    def as_json(self) -> dict[str, Any]:
        value = asdict(self)
        value["lineage"] = list(self.lineage)
        return value

    @property
    def manifest_sha256(self) -> str:
        return canonical_sha256(self.as_json())


DEFAULT_PROFILE_BY_SKILL = {
    "stock-commercial-opportunities": "commercial_opportunity",
    "stock-commercial-opportunities-skill": "commercial_opportunity",
    "bottleneck-serenity-skill": "bottleneck",
    "equity-foresight-signal": "equity_foresight",
    "equity-foresight-signal-skill": "equity_foresight",
    "global-equity-lead-lag-atlas": "lead_lag",
    "global-equity-lead-lag-atlas-skill": "lead_lag",
    "equity-event-atlas": "event_atlas",
    "equity-event-atlas-skill": "event_atlas",
    "serenity-skill": "serenity",
}

DEFAULT_DISPLAY_NAME = {
    "stock-commercial-opportunities": "商业机会独立判断",
    "bottleneck-serenity-skill": "瓶颈与稀缺性独立判断",
    "equity-foresight-signal": "股票前瞻信号独立判断",
    "global-equity-lead-lag-atlas": "全球股票领先滞后独立判断",
    "equity-event-atlas": "股票事件独立判断",
    "serenity-skill": "Serenity 独立判断",
}


def utcnow() -> str:
    return datetime.now(timezone.utc).isoformat()


def canonical_json(payload: object) -> bytes:
    return json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")


def canonical_sha256(payload: object) -> str:
    return hashlib.sha256(canonical_json(payload)).hexdigest()


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _safe_json(path: Path, max_bytes: int = 2_000_000) -> Any:
    if not path.is_file() or path.is_symlink() or path.stat().st_size > max_bytes:
        raise RegistryError(f"INVALID_JSON_FILE:{path}")
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise RegistryError(f"INVALID_JSON:{path}") from exc


def _run_git(args: list[str], cwd: Path | None = None, timeout: int = 30) -> subprocess.CompletedProcess[str]:
    env = {
        "PATH": os.environ.get("PATH", "/usr/bin:/bin"),
        "HOME": str(Path.home()),
        "LANG": "C.UTF-8",
        "LC_ALL": "C.UTF-8",
        "GIT_TERMINAL_PROMPT": "0",
        "GIT_CONFIG_NOSYSTEM": "1",
    }
    return subprocess.run(
        ["git", *args],
        cwd=str(cwd) if cwd else None,
        env=env,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        timeout=timeout,
        check=False,
    )


def ensure_git_sparse_checkout(
    repo_url: str,
    branch: str,
    sparse_path: str,
    target: Path,
) -> tuple[Path | None, str | None, str | None]:
    """Read-only sparse checkout with last-known-good fallback. Never pushes upstream."""
    target.parent.mkdir(parents=True, exist_ok=True)
    git_marker = target / ".git"
    if target.exists() and not git_marker.exists():
        return None, None, "UPSTREAM_CHECKOUT_PATH_NOT_GIT"
    try:
        if not target.exists():
            result = _run_git([
                "clone", "--filter=blob:none", "--no-checkout", "--depth=1",
                "--branch", branch, repo_url, str(target),
            ], timeout=45)
            if result.returncode != 0:
                shutil.rmtree(target, ignore_errors=True)
                return None, None, "UPSTREAM_CLONE_FAILED"
            sparse = _run_git(["sparse-checkout", "init", "--cone"], cwd=target)
            if sparse.returncode != 0:
                return None, None, "UPSTREAM_SPARSE_INIT_FAILED"
            sparse = _run_git(["sparse-checkout", "set", sparse_path], cwd=target)
            if sparse.returncode != 0:
                return None, None, "UPSTREAM_SPARSE_SET_FAILED"
        fetch = _run_git([
            "fetch", "--prune", "--depth=1", "origin", branch,
        ], cwd=target, timeout=40)
        if fetch.returncode != 0:
            head = _run_git(["rev-parse", "HEAD"], cwd=target)
            if head.returncode == 0:
                return target, head.stdout.strip(), "UPSTREAM_FETCH_DEGRADED_USE_LKG"
            return None, None, "UPSTREAM_FETCH_FAILED"
        checkout = _run_git(["checkout", "--detach", "FETCH_HEAD"], cwd=target)
        if checkout.returncode != 0:
            return None, None, "UPSTREAM_CHECKOUT_FAILED"
        head = _run_git(["rev-parse", "HEAD"], cwd=target)
        if head.returncode != 0:
            return None, None, "UPSTREAM_HEAD_UNAVAILABLE"
        return target, head.stdout.strip(), None
    except (OSError, subprocess.TimeoutExpired):
        return None, None, "UPSTREAM_GIT_RUNTIME_ERROR"


def ensure_sparse_checkout(settings: Settings) -> tuple[Path | None, str | None, str | None]:
    if settings.upstream_sparse_path != CANONICAL_STOCK_SKILL_SPARSE_PATH:
        return None, None, "NON_CANONICAL_STOCK_SKILL_SPARSE_PATH"
    return ensure_git_sparse_checkout(
        settings.upstream_repo_url, settings.upstream_branch, settings.upstream_sparse_path,
        settings.upstream_checkout_dir,
    )


def ensure_agent_checkout(settings: Settings) -> tuple[Path | None, str | None, str | None]:
    return ensure_git_sparse_checkout(
        settings.agent_upstream_repo_url, settings.agent_upstream_branch, settings.agent_upstream_sparse_path,
        settings.agent_upstream_checkout_dir,
    )


def _normalise_registry_entries(raw: Any) -> list[dict[str, Any]]:
    if isinstance(raw, dict):
        for key in ("skills", "entries", "items", "registry"):
            value = raw.get(key)
            if isinstance(value, list):
                raw = value
                break
        else:
            if all(isinstance(v, dict) for v in raw.values()):
                raw = [{"skill_id": key, **value} for key, value in raw.items()]
    if not isinstance(raw, list):
        raise RegistryError("REGISTRY_ENTRIES_NOT_ARRAY")
    entries: list[dict[str, Any]] = []
    for item in raw:
        if not isinstance(item, dict):
            continue
        skill_id = str(item.get("skill_id") or item.get("id") or item.get("slug") or item.get("name") or "").strip()
        if not skill_id:
            continue
        path = str(item.get("path") or item.get("source_path") or item.get("directory") or "").strip()
        version = str(item.get("version") or item.get("skill_version") or "UNKNOWN").strip()
        entries.append({**item, "skill_id": skill_id, "path": path, "version": version})
    return entries


def _find_registry(checkout: Path, sparse_path: str) -> Path | None:
    if sparse_path != CANONICAL_STOCK_SKILL_SPARSE_PATH:
        return None
    candidate = checkout / CANONICAL_STOCK_SKILL_SPARSE_PATH / "REGISTRY.json"
    return candidate if candidate.is_file() else None


def _find_skill_root(checkout: Path, sparse_path: str, entry: dict[str, Any]) -> Path | None:
    if sparse_path != CANONICAL_STOCK_SKILL_SPARSE_PATH:
        return None
    path_value = str(entry.get("path", "")).strip().lstrip("/")
    candidates: list[Path] = []
    if path_value:
        candidates.extend([checkout / path_value, checkout / sparse_path / path_value])
    skill_id = str(entry["skill_id"])
    variants = {skill_id, f"{skill_id}-skill"}
    if skill_id.endswith("-skill"):
        variants.add(skill_id[:-6])
    for variant in variants:
        candidates.extend([
            checkout / CANONICAL_STOCK_SKILL_SPARSE_PATH / variant,
        ])
    return next((p for p in candidates if p.is_dir()), None)


def _tree_digest(root: Path, max_files: int = 2000, max_bytes: int = 30_000_000) -> tuple[str, int]:
    rows: list[dict[str, Any]] = []
    total = 0
    for path in sorted(root.rglob("*")):
        if not path.is_file() or path.is_symlink():
            continue
        rel = path.relative_to(root).as_posix()
        if any(part in {".git", "__pycache__", ".pytest_cache"} for part in path.parts):
            continue
        size = path.stat().st_size
        total += size
        if len(rows) >= max_files or total > max_bytes:
            raise RegistryError("SKILL_TREE_BUDGET_EXCEEDED")
        rows.append({"path": rel, "size": size, "sha256": file_sha256(path)})
    if not rows:
        raise RegistryError("SKILL_TREE_EMPTY")
    return canonical_sha256(rows), len(rows)


def load_local_manifests(settings: Settings) -> dict[str, dict[str, Any]]:
    result: dict[str, dict[str, Any]] = {}
    if not settings.runtime_manifest_dir.is_dir():
        return result
    for path in sorted(settings.runtime_manifest_dir.glob("*.json")):
        data = _safe_json(path)
        if not isinstance(data, dict):
            raise RegistryError(f"RUNTIME_MANIFEST_NOT_OBJECT:{path.name}")
        skill_id = str(data.get("skill_id", "")).strip()
        if not skill_id or skill_id in result:
            raise RegistryError(f"RUNTIME_MANIFEST_ID_INVALID:{path.name}")
        data["_manifest_path"] = path.as_posix()
        result[skill_id] = data
    return result


def _runtime_profile(skill_id: str, entry: dict[str, Any], local: dict[str, dict[str, Any]]) -> tuple[str | None, dict[str, Any]]:
    local_value = local.get(skill_id)
    if local_value:
        profile = str(local_value.get("runtime_profile", "")).strip()
        return (profile if profile in PROFILES else None), local_value
    profile = DEFAULT_PROFILE_BY_SKILL.get(skill_id)
    return profile, {}


def build_manifests_from_checkout(
    checkout: Path,
    source_commit: str,
    settings: Settings,
) -> tuple[list[RuntimeManifest], list[dict[str, Any]], str]:
    registry_path = _find_registry(checkout, settings.upstream_sparse_path)
    if not registry_path:
        raise RegistryError("STOCK_SKILL_REGISTRY_NOT_FOUND")
    registry_raw = _safe_json(registry_path)
    entries = _normalise_registry_entries(registry_raw)
    if not entries:
        raise RegistryError("STOCK_SKILL_REGISTRY_EMPTY")
    local = load_local_manifests(settings)
    manifests: list[RuntimeManifest] = []
    quarantined: list[dict[str, Any]] = []
    seen: set[str] = set()
    for entry in entries:
        original_id = str(entry["skill_id"])
        canonical_id = original_id[:-6] if original_id.endswith("-skill") and original_id[:-6] in DEFAULT_PROFILE_BY_SKILL else original_id
        if canonical_id in seen:
            quarantined.append({"skill_id": original_id, "reason": "DUPLICATE_CANONICAL_ID"})
            continue
        seen.add(canonical_id)
        root = _find_skill_root(checkout, settings.upstream_sparse_path, entry)
        if root is None:
            quarantined.append({"skill_id": canonical_id, "reason": "SKILL_TREE_NOT_FOUND"})
            continue
        try:
            tree_sha, _ = _tree_digest(root)
        except RegistryError as exc:
            quarantined.append({"skill_id": canonical_id, "reason": str(exc)})
            continue
        profile, local_value = _runtime_profile(canonical_id, entry, local)
        compatibility_state = "BUNDLED_ADAPTER" if profile is not None else "UNSUPPORTED"
        runtime_file = root / "signal-lattice-runtime.json"
        if runtime_file.is_file():
            runtime_data = _safe_json(runtime_file)
            if (
                isinstance(runtime_data, dict)
                and runtime_data.get("schema_version") in {"1.0.0", "2.0.0"}
                and runtime_data.get("engine") in {"builtin_v1", "factor_v1"}
                and runtime_data.get("runtime_profile") in PROFILES
            ):
                profile = str(runtime_data["runtime_profile"])
                local_value = {**local_value, **runtime_data}
                compatibility_state = "MACHINE_CONTRACT"
            elif profile is None:
                quarantined.append({"skill_id": canonical_id, "reason": "INVALID_RUNTIME_MACHINE_CONTRACT", "tree_sha256": tree_sha})
                continue
        if profile is None:
            quarantined.append({"skill_id": canonical_id, "reason": "NO_DETERMINISTIC_RUNTIME_ADAPTER", "tree_sha256": tree_sha})
            continue
        manifests.append(RuntimeManifest(
            skill_id=canonical_id,
            display_name=str(local_value.get("display_name") or DEFAULT_DISPLAY_NAME.get(canonical_id) or entry.get("display_name") or canonical_id),
            skill_version=str(local_value.get("skill_version") or entry.get("version") or "UNKNOWN"),
            runtime_profile=profile,
            source_repository=settings.upstream_repo_url,
            source_path=root.relative_to(checkout).as_posix(),
            source_commit=source_commit,
            source_sha256=tree_sha,
            compatibility_state=compatibility_state,
            adapter_contract_version=str(local_value.get("adapter_contract_version", "1.0.0")),
            horizon_days=int(local_value.get("horizon_days", 20)),
            lineage=tuple(str(x) for x in local_value.get("lineage", []) if str(x).strip()),
        ))
    # Serenity is a peer method source even when it is not present in Stock_Skill registry.
    serenity = local.get("serenity-skill")
    if serenity and "serenity-skill" not in {m.skill_id for m in manifests}:
        source_url = str(serenity.get("source_url", ""))
        source_sha = str(serenity.get("source_sha256", "")) or canonical_sha256(serenity)
        manifests.append(RuntimeManifest(
            skill_id="serenity-skill",
            display_name=str(serenity.get("display_name", DEFAULT_DISPLAY_NAME["serenity-skill"])),
            skill_version=str(serenity.get("skill_version", "UNKNOWN")),
            runtime_profile="serenity",
            source_repository=source_url or "https://github.com/LinzeColin/AgentDatabase",
            source_path=str(serenity.get("source_path", "CodexSkills/registry/codex/serenity-skill")),
            source_commit=str(serenity.get("source_commit", "DYNAMIC_READ_ONLY")),
            source_sha256=source_sha,
            compatibility_state="BUNDLED_ADAPTER",
            adapter_contract_version=str(serenity.get("adapter_contract_version", "1.0.0")),
            horizon_days=int(serenity.get("horizon_days", 20)),
        ))
    return sorted(manifests, key=lambda x: x.skill_id), quarantined, file_sha256(registry_path)


def observe_serenity_source(settings: Settings) -> tuple[RuntimeManifest | None, str | None]:
    checkout, commit, error = ensure_agent_checkout(settings)
    if not checkout or not commit:
        return None, error
    root = checkout / settings.agent_upstream_sparse_path
    if not root.is_dir():
        return None, "SERENITY_SKILL_TREE_NOT_FOUND"
    local = load_local_manifests(settings).get("serenity-skill", {})
    try:
        tree_sha, _ = _tree_digest(root)
    except RegistryError as exc:
        return None, str(exc)
    runtime_file = root / "signal-lattice-runtime.json"
    compatibility = "BUNDLED_ADAPTER"
    profile = "serenity"
    runtime_data: dict[str, Any] = {}
    if runtime_file.is_file():
        raw = _safe_json(runtime_file)
        if (
            isinstance(raw, dict)
            and raw.get("schema_version") in {"1.0.0", "2.0.0"}
            and raw.get("engine") in {"builtin_v1", "factor_v1"}
            and raw.get("runtime_profile") in PROFILES
        ):
            runtime_data = raw
            profile = str(raw["runtime_profile"])
            compatibility = "MACHINE_CONTRACT"
        else:
            return None, "SERENITY_RUNTIME_MACHINE_CONTRACT_INVALID"
    data = {**local, **runtime_data}
    return RuntimeManifest(
        skill_id="serenity-skill",
        display_name=str(data.get("display_name", DEFAULT_DISPLAY_NAME["serenity-skill"])),
        skill_version=str(data.get("skill_version", "UNKNOWN")),
        runtime_profile=profile,
        source_repository=settings.agent_upstream_repo_url,
        source_path=settings.agent_upstream_sparse_path,
        source_commit=commit,
        source_sha256=tree_sha,
        compatibility_state=compatibility,
        adapter_contract_version=str(data.get("adapter_contract_version", "1.0.0")),
        horizon_days=int(data.get("horizon_days", 20)),
        lineage=tuple(str(x) for x in data.get("lineage", [])),
    ), error


def fallback_manifests(settings: Settings) -> list[RuntimeManifest]:
    local = load_local_manifests(settings)
    manifests: list[RuntimeManifest] = []
    for skill_id, data in sorted(local.items()):
        profile = str(data.get("runtime_profile", ""))
        if profile not in PROFILES:
            continue
        manifests.append(RuntimeManifest(
            skill_id=skill_id,
            display_name=str(data.get("display_name") or DEFAULT_DISPLAY_NAME.get(skill_id) or skill_id),
            skill_version=str(data.get("skill_version", "UNKNOWN")),
            runtime_profile=profile,
            source_repository=str(data.get("source_url", settings.upstream_repo_url)),
            source_path=str(data.get("source_path", "")),
            source_commit=str(data.get("source_commit", "BUNDLED_LAST_KNOWN_GOOD")),
            source_sha256=str(data.get("source_sha256", "")) or canonical_sha256(data),
            compatibility_state="BUNDLED_LAST_KNOWN_GOOD",
            adapter_contract_version=str(data.get("adapter_contract_version", "1.0.0")),
            horizon_days=int(data.get("horizon_days", 20)),
            lineage=tuple(str(x) for x in data.get("lineage", [])),
        ))
    return manifests


def reconcile_runtime_registry(db: Any, settings: Settings, now: str | None = None) -> dict[str, Any]:
    """Reconcile the dynamic upstream registry without sacrificing last-known-good Skills.

    A transient Git/registry failure never retires a previously active Skill.  A Skill whose
    newly observed version is incompatible is quarantined while the prior active manifest
    remains in service.  Retirement occurs only after a successfully parsed upstream
    registry explicitly omits the Skill.
    """
    now = now or utcnow()
    previous = {item["skill_id"]: item for item in db.runtime_skill_registry()}
    previous_active = [item for item in previous.values() if item.get("lifecycle_state") == "ACTIVE"]
    checkout, commit, git_error = ensure_sparse_checkout(settings)
    quarantined: list[dict[str, Any]] = []
    registry_sha = None
    source_validated = False

    if checkout and commit:
        try:
            manifests, quarantined, registry_sha = build_manifests_from_checkout(checkout, commit, settings)
            source_validated = True
        except RegistryError as exc:
            git_error = str(exc)
            manifests = [] if previous_active else fallback_manifests(settings)
    else:
        manifests = [] if previous_active else fallback_manifests(settings)

    agent_git_error = None
    observed_serenity, agent_git_error = observe_serenity_source(settings)
    if observed_serenity is not None:
        manifests = [m for m in manifests if m.skill_id != "serenity-skill"] + [observed_serenity]
        manifests = sorted(manifests, key=lambda item: item.skill_id)

    if not manifests and not previous_active:
        raise RegistryError("NO_LAST_KNOWN_GOOD_RUNTIME_MANIFESTS")
    if not manifests and previous_active:
        active = db.active_runtime_skills()
        return {
            "state": "DEGRADED_USE_LAST_KNOWN_GOOD",
            "source_commit": "LAST_KNOWN_GOOD",
            "source_commits": {"MetaDatabase": commit, "AgentDatabase": None},
            "registry_sha256": registry_sha,
            "git_error": git_error,
            "agent_git_error": agent_git_error,
            "active_skill_count": len(active),
            "events": [],
            "quarantined": [],
            "last_known_good_preserved": True,
            "runtime_agent_dependency": 0,
            "runtime_llm_tokens": 0,
        }

    current_ids = {m.skill_id for m in manifests}
    quarantine_ids = {str(item.get("skill_id", "")) for item in quarantined if item.get("skill_id")}
    events: list[dict[str, Any]] = []
    promoted_ids: set[str] = set()
    fallback_commits = {"BUNDLED_LAST_KNOWN_GOOD", "DYNAMIC_READ_ONLY", "UNAVAILABLE", "LAST_KNOWN_GOOD"}
    for manifest in manifests:
        existing = previous.get(manifest.skill_id)
        # A changed natural-language/source tree is detected immediately, but an existing
        # production adapter is not silently reinterpreted.  Only an explicit supported
        # machine contract may auto-promote a semantic update.  The first observation may
        # bind a bundled last-known-good adapter to the live source tree.
        source_changed = bool(existing and existing.get("source_sha256") != manifest.source_sha256)
        existing_is_bootstrap = bool(existing and str(existing.get("source_commit")) in fallback_commits)
        if source_changed and not existing_is_bootstrap and manifest.compatibility_state != "MACHINE_CONTRACT":
            item = {
                "skill_id": manifest.skill_id,
                "reason": "SOURCE_CHANGED_WITHOUT_MACHINE_COMPATIBILITY_CONTRACT",
                "candidate_source_sha256": manifest.source_sha256,
                "active_source_sha256": existing.get("source_sha256"),
            }
            quarantined.append(item)
            event = {
                "event_id": str(uuid.uuid4()),
                "source_commit": manifest.source_commit,
                "event_type": "UPDATE_QUARANTINED_KEEP_LKG",
                "skill_id": manifest.skill_id,
                "previous": existing,
                "current": manifest.as_json(),
                "state": "QUARANTINED_KEEP_LAST_KNOWN_GOOD",
                "created_at": now,
            }
            db.record_source_reconcile_event(event)
            events.append(event)
            continue
        event_type = "UNCHANGED"
        if existing is None:
            lineage = list(manifest.lineage)
            event_type = "MERGED_FROM" if len(lineage) > 1 else ("SPLIT_FROM" if len(lineage) == 1 else "ADDED")
        elif existing.get("manifest_sha256") != manifest.manifest_sha256:
            event_type = "UPDATED"
        db.upsert_runtime_skill(manifest.as_json(), manifest.manifest_sha256, now)
        promoted_ids.add(manifest.skill_id)
        if event_type != "UNCHANGED":
            event = {
                "event_id": str(uuid.uuid4()),
                "source_commit": manifest.source_commit,
                "event_type": event_type,
                "skill_id": manifest.skill_id,
                "previous": existing,
                "current": manifest.as_json(),
                "state": "PROMOTED",
                "created_at": now,
            }
            db.record_source_reconcile_event(event)
            events.append(event)

    # Only a fully validated upstream registry can retire a Skill.  An incompatible update
    # keeps the previous active version while the candidate is quarantined.
    quarantine_ids = {str(item.get("skill_id", "")) for item in quarantined if item.get("skill_id")}
    if source_validated:
        for skill_id, existing in previous.items():
            if skill_id in current_ids or existing.get("lifecycle_state") != "ACTIVE":
                continue
            if skill_id in quarantine_ids:
                events.append({
                    "event_id": str(uuid.uuid4()),
                    "source_commit": commit or "UNAVAILABLE",
                    "event_type": "UPDATE_QUARANTINED_KEEP_LKG",
                    "skill_id": skill_id,
                    "previous": existing,
                    "current": None,
                    "state": "QUARANTINED_KEEP_LAST_KNOWN_GOOD",
                    "created_at": now,
                })
                db.record_source_reconcile_event(events[-1])
                continue
            db.retire_runtime_skill(skill_id, now)
            event = {
                "event_id": str(uuid.uuid4()),
                "source_commit": commit or "UNAVAILABLE",
                "event_type": "REMOVED",
                "skill_id": skill_id,
                "previous": existing,
                "current": None,
                "state": "RETIRED",
                "created_at": now,
            }
            db.record_source_reconcile_event(event)
            events.append(event)

    for item in quarantined:
        db.record_quarantined_skill(item, commit or "UNAVAILABLE", now)
    active = db.active_runtime_skills()
    agent_commit = observed_serenity.source_commit if observed_serenity is not None else None
    source_commits = {"MetaDatabase": commit, "AgentDatabase": agent_commit}
    combined_commit = ";".join(f"{key}:{value or 'LKG'}" for key, value in sorted(source_commits.items()))
    return {
        "state": "PASS" if source_validated and agent_git_error in {None, "UPSTREAM_FETCH_DEGRADED_USE_LKG"} and len(active) >= settings.minimum_active_skills else "DEGRADED",
        "source_commit": combined_commit,
        "source_commits": source_commits,
        "registry_sha256": registry_sha,
        "git_error": git_error,
        "agent_git_error": agent_git_error,
        "active_skill_count": len(active),
        "events": events,
        "quarantined": quarantined,
        "last_known_good_preserved": bool(quarantine_ids & set(previous)),
        "runtime_agent_dependency": 0,
        "runtime_llm_tokens": 0,
    }
