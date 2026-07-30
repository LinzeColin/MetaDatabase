from __future__ import annotations

import argparse
import json
from pathlib import Path

from common import atomic_json, repo_identity, sha, taskpack_root

ALLOWED = ("satisfied", "apply", "adapt", "equivalent", "conflict", "blocked", "obsolete")
ARCHITECTURE_DECISION = "PRESERVE_TRANSACTION_CORE_REBUILD_PRODUCT_SHELL_AND_CONNECTORS"
CONTROLLED_FALLBACK = "CONTROLLED_PRODUCT_REBUILD_WITH_LEGACY_DATA_MIGRATION"
BLOCKED_DUAL_CORE = "BLOCKED_DUAL_TRANSACTION_CORE"

# These are prebuilt Social Archive candidates.  They are never copied over a
# proven legacy transaction core without the SA-003 focused proof.
PRESERVED_CORE_CANDIDATES = {
    "src/social_archive/db.py",
    "src/social_archive/models.py",
    "src/social_archive/repository.py",
    "src/social_archive/service.py",
    "src/social_archive/sql/runtime_schema.sql",
}


def contains(root: Path, relative: str, needles: tuple[str, ...]) -> bool:
    path = root / relative
    if not path.is_file() or path.is_symlink():
        return False
    try:
        text = path.read_text(encoding="utf-8", errors="ignore")
    except OSError:
        return False
    return all(needle in text for needle in needles)


def _present(root: Path, paths: tuple[str, ...]) -> list[str]:
    return [path for path in paths if (root / path).is_file() and not (root / path).is_symlink()]


def _layout_report(root: Path, *, name: str, transaction: tuple[str, ...], service: tuple[str, ...], recovery: tuple[str, ...]) -> dict[str, object]:
    transaction_present = _present(root, transaction)
    service_present = _present(root, service)
    recovery_present = _present(root, recovery)
    reusable = bool(transaction_present and service_present)
    focused_proven = reusable and bool(recovery_present)
    return {
        "name": name,
        "transaction_files": transaction_present,
        "service_files": service_present,
        "focused_recovery_tests": recovery_present,
        "reusable": reusable,
        "focused_proven": focused_proven,
    }


def core_layouts(target: Path) -> list[dict[str, object]]:
    """Detect actual core layouts; never infer one from a product name alone."""
    return [
        _layout_report(
            target,
            name="social_archive",
            transaction=("src/social_archive/db.py", "src/social_archive/repository.py"),
            service=("src/social_archive/service.py",),
            recovery=("tests/focused/test_runtime_store.py", "tests/focused/test_core_capture.py", "tests/focused/test_legacy_migration.py"),
        ),
        _layout_report(
            target,
            name="x2n_companion",
            transaction=("apps/companion/src/x2n_companion/canonical_store.py",),
            service=("apps/companion/src/x2n_companion/orchestrator.py",),
            recovery=("apps/companion/tests/test_canonical_store.py", "apps/companion/tests/test_orchestrator.py", "apps/companion/tests/test_operations.py"),
        ),
        _layout_report(
            target,
            name="legacy_flat_package",
            transaction=("src/x2n/db.py", "src/xhs_douyin_2notion/db.py"),
            service=("src/x2n/service.py", "src/xhs_douyin_2notion/service.py"),
            recovery=("tests/test_idempotency.py", "tests/test_outbox.py", "tests/test_recovery.py"),
        ),
    ]


def capability_report(target: Path) -> dict[str, dict[str, object]]:
    layouts = core_layouts(target)
    reusable_layouts = [str(layout["name"]) for layout in layouts if layout["reusable"]]
    proven_layouts = [str(layout["name"]) for layout in layouts if layout["focused_proven"]]
    probes: dict[str, dict[str, object]] = {
        "social_archive_identity": {"satisfied": contains(target, "pyproject.toml", ('name = "social-archive"',)) and contains(target, "VERSION", ("0.0.0.4",))},
        "reusable_transaction_assets": {"satisfied": bool(reusable_layouts), "layouts": reusable_layouts},
        "preserved_transaction_core": {"satisfied": len(proven_layouts) == 1, "layouts": proven_layouts},
        "core_authority_conflict": {"satisfied": len(reusable_layouts) > 1, "layouts": reusable_layouts},
        "core_layouts": {"satisfied": False, "layouts": layouts},
        "cloud_first_pairing": {"satisfied": contains(target, "apps/browser-extension/runtime-config.json", ("https://social-archive.linzezhang.com", '"managed": true')) and contains(target, "src/social_archive/api.py", ("/v1/pairing/status", "/v1/pairing/exchange"))},
        "e2n_extension_surfaces": {"satisfied": all((target / p).is_file() for p in ("apps/browser-extension/popup.html", "apps/browser-extension/options.html", "apps/browser-extension/sidepanel.html", "apps/browser-extension/content/fab.js"))},
        "obsidian_local_bridge": {"satisfied": contains(target, "apps/obsidian-plugin/main.js", ('listen(this.settings.port, "127.0.0.1"', "timingSafeEqual", 'request.url !== "/vault"'))},
        "generic_capture": {"satisfied": contains(target, "src/social_archive/api.py", ("/v1/captures",))},
        "western_connectors": {"satisfied": all(contains(target, "src/social_archive/registry.py", (name,)) for name in ("reddit", "instagram"))},
        "eastern_connector_boundary": {"satisfied": (target / "src/social_archive/connectors").is_dir()},
        "unified_library": {"satisfied": contains(target, "src/social_archive/api.py", ("/v1/library", "/v1/search")) and (target / "apps/pwa/index.html").is_file()},
        "destinations": {"satisfied": contains(target, "src/social_archive/destinations.py", ("Notion", "Obsidian", "GitHub"))},
        "encrypted_three_replica": {"satisfied": contains(target, "src/social_archive/encryption.py", ("AgeEncryptor", "cipher_sha256")) and contains(target, "src/social_archive/db.py", ('{"r2", "oci", "github"}',))},
        "free_only_guard": {"satisfied": contains(target, "src/social_archive/config.py", ("SOCIAL_ARCHIVE_PAID_API_ALLOWED", "零费用合同"))},
        "runtime_ops": {"satisfied": (target / "deploy/systemd/social-archive.service").is_file() and (target / "scripts/restore.py").is_file()},
    }
    return probes


def _met(caps: dict[str, dict[str, object]]) -> set[str]:
    return {key for key, value in caps.items() if value.get("satisfied")}


def _has_core_conflict(caps: dict[str, dict[str, object]]) -> bool:
    return bool(caps.get("core_authority_conflict", {}).get("satisfied"))


def decide_mode(target: Path, legacy: Path, target_capabilities: dict[str, dict[str, object]], legacy_capabilities: dict[str, dict[str, object]] | None = None) -> str:
    legacy_capabilities = legacy_capabilities or {}
    target_met, legacy_met = _met(target_capabilities), _met(legacy_capabilities)
    if _has_core_conflict(target_capabilities) or _has_core_conflict(legacy_capabilities):
        return BLOCKED_DUAL_CORE
    complete = {"social_archive_identity", "cloud_first_pairing", "e2n_extension_surfaces", "encrypted_three_replica"}
    if target.exists() and complete.issubset(target_met):
        return "ADAPT_CURRENT_UPSTREAM"
    if "reusable_transaction_assets" in target_met or "reusable_transaction_assets" in legacy_met:
        return ARCHITECTURE_DECISION
    return CONTROLLED_FALLBACK


def file_rows(overlay: Path, target: Path, mode: str) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    for src in sorted(path for path in overlay.rglob("*") if path.is_file() and not path.is_symlink()):
        rel = src.relative_to(overlay)
        rel_text = rel.as_posix()
        dst = target / rel
        if mode == ARCHITECTURE_DECISION and rel_text in PRESERVED_CORE_CANDIDATES:
            classification, reason = "adapt", "候选事务核心不得覆盖已聚焦证明的唯一核心；留待 SA-003 逐文件适配"
        elif not dst.exists():
            classification, reason = "apply", "目标缺少冻结能力"
        elif not dst.is_file() or dst.is_symlink():
            classification, reason = "conflict", "目标不是普通文件或为符号链接"
        elif sha(src) == sha(dst):
            classification, reason = "satisfied", "内容哈希一致"
        elif mode == "ADAPT_CURRENT_UPSTREAM":
            classification, reason = "adapt", "保留更强 current-upstream，仅合并冻结语义差异"
        elif mode == ARCHITECTURE_DECISION:
            classification, reason = "adapt", "重建产品壳、连接器、目的地、UI 或运维边界"
        else:
            classification, reason = "adapt", "缺少可证明事务核心；只读迁移后受控重建受影响纵向切片"
        rows.append({"path": rel_text, "classification": classification, "reason": reason, "overlay_sha256": sha(src), "target_sha256": sha(dst) if dst.is_file() and not dst.is_symlink() else None})
    return rows


def task_rows(root: Path, caps: dict[str, dict[str, object]]) -> list[dict[str, str]]:
    graph = json.loads((root / "../09_ROADMAP/TASK_GRAPH.json").resolve().read_text(encoding="utf-8"))
    rows: list[dict[str, str]] = []
    for task in graph["tasks"]:
        key = task.get("capability_key")
        classification = "satisfied" if task.get("status") == "COMPLETE_PREBUILT" else ("equivalent" if key and caps.get(key, {}).get("satisfied") else "apply")
        rows.append({"task_id": task["id"], "classification": classification, "capability_key": key or ""})
    return rows


def _combined_capabilities(target: dict[str, dict[str, object]], legacy: dict[str, dict[str, object]]) -> dict[str, dict[str, object]]:
    keys = set(target) | set(legacy)
    return {
        key: {"satisfied": bool(target.get(key, {}).get("satisfied")) or bool(legacy.get(key, {}).get("satisfied"))}
        for key in keys
    }


def _redacted_identity(repo: Path) -> dict[str, object]:
    identity = dict(repo_identity(repo))
    dirty = identity.pop("dirty", [])
    identity["dirty_count"] = len(dirty)
    return identity


def main() -> int:
    parser = argparse.ArgumentParser(description="Classify moving main against Social Archive v0.0.0.4 semantic goals")
    parser.add_argument("--repo", required=True)
    args = parser.parse_args()
    repo = Path(args.repo).resolve()
    root = taskpack_root()
    overlay = root / "overlay/social-archive"
    target = repo / "social-archive"
    legacy = repo / "xhs-douyin-2notion"
    target_caps = capability_report(target)
    legacy_caps = capability_report(legacy)
    mode = decide_mode(target, legacy, target_caps, legacy_caps)
    files = file_rows(overlay, target, mode)
    tasks = task_rows(root, _combined_capabilities(target_caps, legacy_caps))
    all_rows = files + tasks
    summary = {status: sum(1 for row in all_rows if row["classification"] == status) for status in ALLOWED}
    report = {
        "schema_version": "4.1",
        "repository_identity": _redacted_identity(repo),
        "target_tree": str(target),
        "legacy_stage0_tree": str(legacy),
        "decision": mode,
        "architecture_decision": ARCHITECTURE_DECISION,
        "controlled_fallback": CONTROLLED_FALLBACK,
        "decision_rule": "Preserve a focused-proven single transaction/recovery core. Rebuild product identity, E2N shell, real connectors, destination probe/binding/receipt, aggregation UI and operations. Retain stronger current-upstream equivalents. Use controlled read-only migration/rebuild only for an affected slice when focused evidence proves the core absent, locally unrepairable or irreconcilably dual-authoritative.",
        "target_capabilities": target_caps,
        "legacy_candidate_capabilities": legacy_caps,
        "reusable_transaction_assets": {"target": target_caps.get("reusable_transaction_assets"), "legacy": legacy_caps.get("reusable_transaction_assets")},
        "preserved_transaction_core": {"target": target_caps.get("preserved_transaction_core"), "legacy": legacy_caps.get("preserved_transaction_core")},
        "files": files,
        "tasks": tasks,
        "summary": summary,
    }
    atomic_json(repo / ".social-archive-migration/SEMANTIC_CLASSIFICATION.json", report)
    print(json.dumps({"decision": mode, "summary": summary}, ensure_ascii=False, indent=2))
    return 2 if mode == BLOCKED_DUAL_CORE or summary["conflict"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
