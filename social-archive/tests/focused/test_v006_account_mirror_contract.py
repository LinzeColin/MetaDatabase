import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
TASKPACK_ROOT = ROOT.parents[2]

EXPECTED_PLATFORM_IDS = [
    "generic-web",
    "x",
    "reddit",
    "instagram",
    "xiaohongshu",
    "douyin",
    "kuaishou",
    "bilibili",
]


def _load_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def test_platform_capability_contract_is_account_level_and_exact():
    machine = _load_json(ROOT / "machine/platform_capabilities.json")
    canonical = _load_json(TASKPACK_ROOT / "04_CONNECTORS/PLATFORM_CAPABILITY_MATRIX.json")
    assert machine == canonical
    assert machine["active_platform_ids"] == EXPECTED_PLATFORM_IDS
    assert [item["id"] for item in machine["platforms"]] == EXPECTED_PLATFORM_IDS
    assert machine["golden_path"] == (
        "connect_account_once -> first_full_mirror -> platform_grouped_table -> automatic_incremental_sync"
    )
    assert machine["single_page_capture"] == "fallback_only"
    assert machine["paid_paths"] == "disabled_fail_closed"
    assert machine["default_archive_levels"] == ["L0", "L1", "L3"]
    assert machine["manual_archive_levels"] == ["L2"]
    for platform in machine["platforms"]:
        assert platform["account_source"]
        assert platform["relations"]
        assert platform["full_sync_oracle"]
        assert platform["incremental_oracle"]
        assert platform["canary"]
        assert platform["completion_proof"]
        assert platform["single_page_capture"] == "fallback_only"
        assert "one" in platform["full_sync_oracle"].lower() or "一次" in platform["full_sync_oracle"]
    assert "tiktok" not in machine["active_platform_ids"]


def test_extension_scope_excludes_standalone_tiktok_and_keeps_account_mirror_primary():
    manifest = _load_json(ROOT / "apps/browser-extension/manifest.json")
    serialized = json.dumps(manifest, ensure_ascii=False).lower()
    assert "tiktok.com" not in serialized
    assert "cookies" not in {str(item).lower() for item in manifest.get("permissions", [])}
    assert "bookmarks" in manifest.get("optional_permissions", [])
    scripts = [
        script
        for entry in manifest.get("content_scripts", [])
        for script in entry.get("js", [])
    ]
    assert "content/account-mirror-core.js" in scripts
    assert "content/account-mirror.js" in scripts


def test_account_mirror_requires_terminal_proof_and_collection_scope_finalization():
    core = (ROOT / "apps/browser-extension/content/account-mirror-core.js").read_text(encoding="utf-8")
    scanner = (ROOT / "apps/browser-extension/content/account-mirror.js").read_text(encoding="utf-8")
    background = (ROOT / "apps/browser-extension/background.js").read_text(encoding="utf-8")
    assert "explicit_terminal_or_total_match_only" in core
    assert "TRUSTED_TOTAL_MATCH" in core
    assert "TERMINAL_NOT_PROVEN" in core
    assert "discoverCollectionScopes" in core
    assert "STABLE_END_WITHOUT_PROOF" in scanner
    assert 'completeness: complete ? "complete" : "partial"' in scanner
    assert "SA_MIRROR_DISCOVER_COLLECTIONS" in scanner
    assert "scope_type: \"collection\"" in background
    assert "scope_type: \"relation\"" in background
    assert "every" in background or "allScopesComplete" in background


def test_owner_approved_table_contract_is_frozen_in_product_surface():
    html = (ROOT / "apps/pwa/index.html").read_text(encoding="utf-8")
    contract = (TASKPACK_ROOT / "08_UIUX/TABLE_LIBRARY_CONTRACT.md").read_text(encoding="utf-8")
    for label in ["平台", "时间", "主题分类", "关键词", "内容", "链接"]:
        assert label in html or label in contract
    for phrase in ["按平台分组", "立即同步全部", "账号同步中心", "默认按收藏、点赞或书签时间从新到旧"]:
        assert phrase in html
