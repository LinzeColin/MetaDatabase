import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]

# SHA-256 of 04_CONNECTORS/PLATFORM_CAPABILITY_MATRIX.json in the sealed
# Social Archive v0.0.0.6 Task Pack.  Keeping the sealed payload identity in
# the test avoids a non-portable dependency on a local Task Pack extraction.
FROZEN_PLATFORM_CAPABILITY_SHA256 = "5a0636d8e45b2e411589645fe102daf48f1eddee9f32997f6ce976408271a02f"

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
    path = ROOT / "machine/platform_capabilities.json"
    payload = path.read_bytes()
    machine = json.loads(payload.decode("utf-8"))
    assert hashlib.sha256(payload).hexdigest() == FROZEN_PLATFORM_CAPABILITY_SHA256
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
    # v0.0.0.7 / T03(a)：原先这里还断言 manifest 注入了两个抓取器脚本。
    # 抓取器已删，那两条反转成守卫（test_superseded_paths_stay_removed.py 的
    # test_manifest_no_longer_injects_scrapers_into_platform_pages）。
    # 上面这几条边界（不碰 tiktok、不要 cookies 权限、书签走可选权限）与取数方式无关，
    # 是 L0 硬边界的一部分，原样保留。
    scripts = [
        script
        for entry in manifest.get("content_scripts", [])
        for script in entry.get("js", [])
    ]
    assert "bridge.js" in scripts, "PWA 桥接脚本不该被顺手删掉"


def test_account_mirror_requires_terminal_proof_and_collection_scope_finalization():
    """v0.0.0.7 / T03(a) 之后，这条只剩**服务端批次协议**那一半。

    原测试的另一半打在抓取器的"终态证明"上（TRUSTED_TOTAL_MATCH / TERMINAL_NOT_PROVEN
    / STABLE_END_WITHOUT_PROOF）——那是"滚到底了算不算扫完"的判据，
    随抓取器一起废止。T08 用 API 分页游标判终态，不再靠猜页面滚没滚到底。

    留下的这几条是**批次上传协议**：分 collection / relation 两级 scope、
    整体完成度取所有 scope 的合取。它与取数方式无关，T08 会继续用同一套。
    """
    background = (ROOT / "apps/browser-extension/background.js").read_text(encoding="utf-8")
    assert "scope_type: \"collection\"" in background
    assert "scope_type: \"relation\"" in background
    assert "every" in background or "allScopesComplete" in background
    # 完成度必须是"每个 scope 都完成"才算完成，不许有一个 scope 成功就报完成。
    assert "scopeResults.every(item => item.completeness === \"complete\")" in background


def test_owner_approved_table_contract_is_frozen_in_product_surface():
    html = (ROOT / "apps/pwa/index.html").read_text(encoding="utf-8")
    for label in ["平台", "时间", "主题分类", "关键词", "内容", "链接"]:
        assert label in html
    for phrase in ["按平台分组", "立即同步全部", "账号同步中心", "默认按收藏、点赞或书签时间从新到旧"]:
        assert phrase in html
