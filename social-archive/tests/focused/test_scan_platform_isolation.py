import json
import subprocess
from pathlib import Path

import pytest

from social_archive.models import CaptureRequest


ROOT = Path(__file__).resolve().parents[2]
MIRROR_CORE = ROOT / "apps/browser-extension/content/account-mirror-core.js"


def test_complete_scan_only_changes_the_scanned_platform(service, store):
    x_item = service.capture(CaptureRequest(
        platform="x", url="https://x.com/example/status/100", relation_type="bookmark",
        requested_levels=["L0", "L1"],
    ))
    reddit_item = service.capture(CaptureRequest(
        platform="reddit", url="https://www.reddit.com/r/example/comments/100/item/", relation_type="saved",
        requested_levels=["L0", "L1"],
    ))
    store.apply_complete_scan("x", set(), relation_type="bookmark")
    store.apply_complete_scan("x", set(), relation_type="bookmark")
    x_relation = store.get_content(x_item.content_id)["relations"][0]
    reddit_relation = store.get_content(reddit_item.content_id)["relations"][0]
    assert x_relation["status"] == "closed"
    assert x_relation["missing_complete_scan_count"] == 2
    assert reddit_relation["status"] == "active"
    assert reddit_relation["missing_complete_scan_count"] == 0


@pytest.mark.parametrize(("platform", "relation_type", "url"), (
    ("xiaohongshu", "favorite", "https://www.xiaohongshu.com/explore/100"),
    ("douyin", "favorite", "https://www.douyin.com/video/100"),
    ("kuaishou", "favorite", "https://www.kuaishou.com/short-video/100"),
    ("bilibili", "favorite", "https://www.bilibili.com/video/BV1fixture"),
))
def test_domestic_complete_scan_never_changes_another_platform(service, store, platform, relation_type, url):
    domestic_item = service.capture(CaptureRequest(
        platform=platform, url=url, relation_type=relation_type, requested_levels=["L0", "L1"],
    ))
    x_item = service.capture(CaptureRequest(
        platform="x", url="https://x.com/example/status/101", relation_type="bookmark",
        requested_levels=["L0", "L1"],
    ))

    store.apply_complete_scan(platform, set(), relation_type=relation_type)
    store.apply_complete_scan(platform, set(), relation_type=relation_type)

    domestic_relation = store.get_content(domestic_item.content_id)["relations"][0]
    x_relation = store.get_content(x_item.content_id)["relations"][0]
    assert domestic_relation["status"] == "closed"
    assert domestic_relation["missing_complete_scan_count"] == 2
    assert x_relation["status"] == "active"
    assert x_relation["missing_complete_scan_count"] == 0


def test_douyin_browser_mirror_keeps_video_and_note_collection_candidates():
    script = f"""
const core = require({json.dumps(str(MIRROR_CORE))});
function card(label) {{
  return {{
    innerText: label,
    textContent: label,
    querySelector: () => null,
    querySelectorAll: () => [],
    closest: () => null,
  }};
}}
function anchor(href, label) {{
  const parent = card(label);
  return {{
    href,
    textContent: label,
    title: label,
    getAttribute: () => '',
    closest: () => parent,
  }};
}}
const root = {{
  querySelectorAll: () => [
    anchor('https://www.douyin.com/video/1001?share=1', '视频收藏'),
    anchor('https://www.douyin.com/note/1002?share=1', '图文收藏'),
  ],
}};
const items = core.extractCandidates('douyin', root, {{
  relationType: 'favorite',
  collectionKey: 'douyin:collection:tech',
  collectionName: '技术收藏夹',
  pageUrl: 'https://www.douyin.com/user/self?showTab=collection',
}});
console.log(JSON.stringify(items.map(item => ({{
  external_content_id: item.external_content_id,
  url: item.url,
  relation_type: item.relation_type,
  collection_key: item.collection_key,
  collection_name: item.collection_name,
}}))));
"""
    completed = subprocess.run(
        ["node", "-e", script],
        cwd=ROOT,
        check=True,
        text=True,
        capture_output=True,
    )
    assert json.loads(completed.stdout) == [
        {
            "external_content_id": "1001",
            "url": "https://www.douyin.com/video/1001?share=1",
            "relation_type": "favorite",
            "collection_key": "douyin:collection:tech",
            "collection_name": "技术收藏夹",
        },
        {
            "external_content_id": "1002",
            "url": "https://www.douyin.com/note/1002?share=1",
            "relation_type": "favorite",
            "collection_key": "douyin:collection:tech",
            "collection_name": "技术收藏夹",
        },
    ]


def test_kuaishou_browser_mirror_requires_confirmed_scope_and_keeps_video_photo_candidates():
    script = f"""
const core = require({json.dumps(str(MIRROR_CORE))});
function tab(text, selected = false) {{
  const attrs = {{ 'aria-selected': selected ? 'true' : 'false' }};
  return {{
    textContent: text,
    className: '',
    getAttribute: key => attrs[key] || '',
    click: () => {{ attrs['aria-selected'] = 'true'; }},
  }};
}}
function card(label) {{
  return {{
    innerText: label,
    textContent: label,
    querySelector: () => null,
    querySelectorAll: () => [],
    closest: () => null,
  }};
}}
function anchor(href, label) {{
  const parent = card(label);
  return {{
    href,
    textContent: label,
    title: label,
    getAttribute: () => '',
    closest: () => parent,
  }};
}}
const favorite = tab('收藏', true);
const like = tab('点赞');
const scopeRoot = {{ querySelectorAll: () => [favorite, like] }};
const root = {{
  querySelectorAll: () => [
    anchor('https://www.kuaishou.com/short-video/short-1?share=1', '视频收藏'),
    anchor('https://www.kuaishou.com/photo/photo-2?share=1', '图文收藏'),
  ],
}};
const items = core.extractCandidates('kuaishou', root, {{
  relationType: 'favorite',
  pageUrl: 'https://www.kuaishou.com/profile',
}});
console.log(JSON.stringify({{
  activeFavorite: core.ensureRelationScope('kuaishou', 'favorite', scopeRoot),
  missingLike: core.ensureRelationScope('kuaishou', 'like', {{ querySelectorAll: () => [] }}),
  items: items.map(item => ({{
    external_content_id: item.external_content_id,
    url: item.url,
    relation_type: item.relation_type,
  }})),
}}));
"""
    completed = subprocess.run(
        ["node", "-e", script],
        cwd=ROOT,
        check=True,
        text=True,
        capture_output=True,
    )
    assert json.loads(completed.stdout) == {
        "activeFavorite": {
            "confirmed": True,
            "reason": "TAB_ALREADY_SELECTED",
            "clicked": False,
        },
        "missingLike": {
            "confirmed": False,
            "reason": "RELATION_TAB_NOT_FOUND",
            "clicked": False,
        },
        "items": [
            {
                "external_content_id": "short-1",
                "url": "https://www.kuaishou.com/short-video/short-1?share=1",
                "relation_type": "favorite",
            },
            {
                "external_content_id": "photo-2",
                "url": "https://www.kuaishou.com/photo/photo-2?share=1",
                "relation_type": "favorite",
            },
        ],
    }


def test_bilibili_browser_mirror_requires_confirmed_like_scope_and_keeps_video_ids():
    script = f"""
const core = require({json.dumps(str(MIRROR_CORE))});
function tab(text, selected = false) {{
  const attrs = {{ 'aria-selected': selected ? 'true' : 'false' }};
  return {{
    textContent: text,
    className: '',
    getAttribute: key => attrs[key] || '',
    click: () => {{ attrs['aria-selected'] = 'true'; }},
  }};
}}
function card(label) {{
  return {{
    innerText: label,
    textContent: label,
    querySelector: () => null,
    querySelectorAll: () => [],
    closest: () => null,
  }};
}}
function anchor(href, label) {{
  const parent = card(label);
  return {{
    href,
    textContent: label,
    title: label,
    getAttribute: () => '',
    closest: () => parent,
  }};
}}
const like = tab('点赞', true);
const scopeRoot = {{ querySelectorAll: () => [like] }};
const root = {{
  querySelectorAll: () => [
    anchor('https://www.bilibili.com/video/BV1fixture?spm_id_from=333.1', '收藏视频'),
    anchor('https://www.bilibili.com/video/av170001', '历史视频'),
  ],
}};
const items = core.extractCandidates('bilibili', root, {{
  relationType: 'favorite',
  collectionKey: 'bilibili:fav:1',
  collectionName: '默认收藏夹',
  pageUrl: 'https://space.bilibili.com/0/favlist',
}});
console.log(JSON.stringify({{
  activeLike: core.ensureRelationScope('bilibili', 'like', scopeRoot),
  missingLike: core.ensureRelationScope('bilibili', 'like', {{ querySelectorAll: () => [] }}),
  routeScopedHistory: core.ensureRelationScope('bilibili', 'history', {{ querySelectorAll: () => [] }}),
  items: items.map(item => ({{
    external_content_id: item.external_content_id,
    url: item.url,
    relation_type: item.relation_type,
    collection_key: item.collection_key,
  }})),
}}));
"""
    completed = subprocess.run(
        ["node", "-e", script],
        cwd=ROOT,
        check=True,
        text=True,
        capture_output=True,
    )
    assert json.loads(completed.stdout) == {
        "activeLike": {
            "confirmed": True,
            "reason": "TAB_ALREADY_SELECTED",
            "clicked": False,
        },
        "missingLike": {
            "confirmed": False,
            "reason": "RELATION_TAB_NOT_FOUND",
            "clicked": False,
        },
        "routeScopedHistory": {
            "confirmed": True,
            "reason": "ROUTE_SCOPED",
            "clicked": False,
        },
        "items": [
            {
                "external_content_id": "BV1fixture",
                "url": "https://www.bilibili.com/video/BV1fixture?spm_id_from=333.1",
                "relation_type": "favorite",
                "collection_key": "bilibili:fav:1",
            },
            {
                "external_content_id": "av170001",
                "url": "https://www.bilibili.com/video/av170001",
                "relation_type": "favorite",
                "collection_key": "bilibili:fav:1",
            },
        ],
    }


def test_relation_tab_active_matches_real_world_class_spellings(tmp_path):
    # The class test used to require a standalone "active" token, so the
    # ordinary BEM and utility spellings every Chinese SPA ships never matched.
    # The selected tab could then never be confirmed and the scan imported
    # nothing -- the "sync always reports 0" symptom. Negated spellings must
    # still fail, or likes would be mislabelled as favorites.
    import json
    import subprocess
    from pathlib import Path

    root = Path(__file__).resolve().parents[2]
    cases = {
        "active": True, "is-active": True, "tab--selected": True, "active_tab": True,
        "channel is-active": True, "nav-item current": True, "is_selected": True,
        "inactive": False, "deactivated": False, "unselected": False,
        "non-current": False, "in-active": False, "un_selected": False,
        "tab": False, "reactive": False,
    }
    script = """
const core = require(process.argv[1]);
const cases = JSON.parse(process.argv[2]);
const out = {};
for (const cls of Object.keys(cases)) {
  const root = { querySelectorAll: () => [ { className: cls, textContent: "收藏", getAttribute: () => "", tagName: "DIV", click(){} } ] };
  out[cls] = core.ensureRelationScope("xiaohongshu", "favorite", root, { allowClick: false }).reason === "TAB_ALREADY_SELECTED";
}
console.log(JSON.stringify(out));
"""
    result = subprocess.run(
        ["node", "-e", script, str(root / "apps/browser-extension/content/account-mirror-core.js"), json.dumps(cases)],
        capture_output=True, text=True, check=True,
    )
    assert json.loads(result.stdout) == cases


def test_unconfirmed_relation_scope_reports_the_real_tab_markup():
    # A stale selector must be repairable against what the page actually ships,
    # not guessed at.
    from pathlib import Path

    root = Path(__file__).resolve().parents[2]
    core = (root / "apps/browser-extension/content/account-mirror-core.js").read_text(encoding="utf-8")
    mirror = (root / "apps/browser-extension/content/account-mirror.js").read_text(encoding="utf-8")
    assert "relationTabDiagnostic" in core
    assert "observed_tabs" in core
    assert "observed_tabs: relationScope.observed_tabs" in mirror


def test_profile_scoped_relations_use_the_stored_profile_url():
    # The spec placeholder https://www.xiaohongshu.com/user/profile carries no
    # user id and is nobody's profile, so navigating there found no relation
    # tabs and every run imported nothing. The connect flow already stores the
    # real profile URL; resolveRelationUrl must prefer it.
    from pathlib import Path

    background = (Path(__file__).resolve().parents[2] / "apps/browser-extension/background.js").read_text(encoding="utf-8")
    resolver = background.split("function resolveRelationUrl", 1)[1].split("\n}", 1)[0]
    assert "sameOriginUrl(profileUrl, url)" in resolver
    assert "url = profileUrl" in resolver
    # The narrower per-platform overrides must still win over the generic swap.
    assert resolver.index("url = profileUrl") < resolver.index('platform === "x"')


def test_scan_failures_record_a_readable_error_not_object_object():
    # String() on a thrown array or plain object produced "[object Object]"
    # repeated, which is what earlier real failures recorded, leaving them
    # undiagnosable.
    from pathlib import Path

    background = (Path(__file__).resolve().parents[2] / "apps/browser-extension/background.js").read_text(encoding="utf-8")
    assert "function describeScanError" in background
    assert "cursor: { error: describeScanError(error) }" in background
    assert "String(error?.message || error).slice(0, 300)" not in background


def test_sync_all_uses_the_account_profile_url_not_the_callers():
    # enqueueAllAccounts -- the "sync everything" button, the primary path --
    # never threaded a profileUrl through, so resolveRelationUrl fell back to
    # the userless placeholder and the scan found no relation tabs at all. The
    # account record already carries the real profile URL, so read it there
    # instead of trusting the caller.
    from pathlib import Path

    background = (Path(__file__).resolve().parents[2] / "apps/browser-extension/background.js").read_text(encoding="utf-8")
    assert "function accountProfileUrl(account)" in background
    assert "profileUrl: options.profileUrl || accountProfileUrl(account)" in background
    resolver = background.split("function accountProfileUrl", 1)[1].split("\n}", 1)[0]
    for source in ("metadata?.profile_url", "profile_url", "external_account_id"):
        assert source in resolver


def test_a_closed_mirror_tab_does_not_kill_the_remaining_relations():
    # One closed tab took out every later relation with "No tab with id", so a
    # single Bilibili tab disappearing wiped favourites, watch-later and
    # history in one go.
    from pathlib import Path

    background = (Path(__file__).resolve().parents[2] / "apps/browser-extension/background.js").read_text(encoding="utf-8")
    loop = background.split("for (let index = 0; index < spec.relations.length; index += 1) {", 1)[1][:600]
    assert "chrome.tabs.get(tab.id).catch(() => null)" in loop
    assert "if (!live) tab = await chrome.tabs.create(" in loop
