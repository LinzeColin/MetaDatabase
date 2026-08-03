import json
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
CORE = ROOT / "apps/browser-extension/content/account-mirror-core.js"
MIRROR = ROOT / "apps/browser-extension/content/account-mirror.js"


def _run_node(script: str) -> dict:
    completed = subprocess.run(
        ["node", "-e", script],
        cwd=ROOT,
        check=True,
        text=True,
        capture_output=True,
    )
    return json.loads(completed.stdout)


def test_bookmark_tree_flattening_preserves_folder_relation_time_and_stable_id():
    script = f"""
const core = require({json.dumps(str(CORE))});
const result = core.flattenBookmarksTree([{{
  id: 'root', title: '', children: [{{
    id: 'f1', title: '研究', children: [{{
      id: 'f2', title: 'AI', children: [
        {{ id: 'b1', parentId: 'f2', title: '示例', url: 'https://www.rfc-editor.org/rfc/rfc3986?utm_source=test&x=1#section-3', dateAdded: 1700000000000 }},
        {{ id: 'bad', parentId: 'f2', title: '危险', url: 'javascript:alert(1)', dateAdded: 1700000000000 }}
      ]
    }}]
  }}]
}}]);
console.log(JSON.stringify({{ result, chunks: core.chunk([1,2,3,4,5], 2) }}));
"""
    payload = _run_node(script)
    assert len(payload["result"]) == 1
    item = payload["result"][0]
    assert item["platform"] == "generic-web"
    assert item["relation_type"] == "bookmark"
    assert item["collection_key"] == "研究 / AI"
    assert item["external_content_id"] == "chrome-bookmark:b1"
    assert item["url"] == "https://www.rfc-editor.org/rfc/rfc3986?x=1"
    assert item["relation_observed_at"].startswith("2023-")
    assert [len(chunk) for chunk in payload["chunks"]] == [2, 2, 1]


def test_platform_relation_inference_and_canonical_ids_are_deterministic():
    script = f"""
const core = require({json.dumps(str(CORE))});
console.log(JSON.stringify({{
  xBookmark: core.relationFromUrl('x', 'https://x.com/i/bookmarks'),
  redditUpvoted: core.relationFromUrl('reddit', 'https://www.reddit.com/user/me/upvoted/'),
  biliWatchLater: core.relationFromUrl('bilibili', 'https://www.bilibili.com/watchlater/list'),
  xId: core.externalId('x', 'https://x.com/user/status/123456?utm_source=x'),
  xhsId: core.externalId('xiaohongshu', 'https://www.xiaohongshu.com/explore/abc-123')
}}));
"""
    payload = _run_node(script)
    assert payload == {
        "xBookmark": "bookmark",
        "redditUpvoted": "upvoted",
        "biliWatchLater": "watch_later",
        "xId": "123456",
        "xhsId": "abc-123",
    }


def test_xhs_shared_profile_requires_a_confirmed_relation_tab_before_labeling():
    script = f"""
const core = require({json.dumps(str(CORE))});
function tab(text, selected = false) {{
  const attrs = {{ 'aria-selected': selected ? 'true' : 'false' }};
  return {{
    textContent: text,
    className: '',
    getAttribute: key => attrs[key] || '',
    click: () => {{ attrs['aria-selected'] = 'true'; }}
  }};
}}
const favorite = tab('收藏', true);
const like = tab('赞过', false);
const root = {{ querySelectorAll: () => [favorite, like] }};
const selectedLike = core.ensureRelationScope('xiaohongshu', 'like', root);
const missing = core.ensureRelationScope('xiaohongshu', 'like', {{ querySelectorAll: () => [] }});
const routeScoped = core.ensureRelationScope('reddit', 'saved', root);
console.log(JSON.stringify({{ selectedLike, missing, routeScoped, likeSelected: like.getAttribute('aria-selected') }}));
"""
    payload = _run_node(script)
    assert payload["selectedLike"] == {"confirmed": True, "reason": "TAB_SELECTED", "clicked": True}
    assert payload["likeSelected"] == "true"
    assert payload["missing"] == {"confirmed": False, "reason": "RELATION_TAB_NOT_FOUND", "clicked": False}
    assert payload["routeScoped"] == {"confirmed": True, "reason": "ROUTE_SCOPED", "clicked": False}


def test_xhs_collection_discovery_keeps_collection_scope_separate_from_note_links():
    script = f"""
const core = require({json.dumps(str(CORE))});
function link(text, href) {{
  return {{
    textContent: text,
    href,
    title: '',
    getAttribute: () => '',
  }};
}}
const root = {{
  querySelectorAll: () => [
    link('旅行收藏夹', 'https://www.xiaohongshu.com/user/profile/collection/travel'),
    link('收藏夹中的笔记', 'https://www.xiaohongshu.com/explore/note-1')
  ]
}};
console.log(JSON.stringify(core.discoverCollectionScopes('xiaohongshu', root)));
"""
    payload = _run_node(script)
    assert payload == [{
        "collectionKey": "xiaohongshu:/user/profile/collection/travel",
        "collectionName": "旅行收藏夹",
        "url": "https://www.xiaohongshu.com/user/profile/collection/travel",
    }]


def test_xhs_content_scan_returns_partial_without_a_confirmed_relation_tab():
    script = f"""
const fs = require('fs');
const vm = require('vm');
let listener = null;
globalThis.location = {{ hostname: 'www.xiaohongshu.com', href: 'https://www.xiaohongshu.com/user/profile' }};
globalThis.document = {{
  querySelectorAll: () => [],
  scrollingElement: {{ scrollHeight: 0, scrollTop: 0, scrollTo: () => {{}} }},
  documentElement: {{ scrollHeight: 0, scrollTop: 0, scrollTo: () => {{}} }}
}};
globalThis.chrome = {{
  runtime: {{
    connect: () => ({{ postMessage: () => {{}}, disconnect: () => {{}} }}),
    sendMessage: () => Promise.resolve(null),
    onMessage: {{ addListener: fn => {{ listener = fn; }} }}
  }}
}};
vm.runInThisContext(fs.readFileSync({json.dumps(str(CORE))}, 'utf8'), {{ filename: 'account-mirror-core.js' }});
vm.runInThisContext(fs.readFileSync({json.dumps(str(MIRROR))}, 'utf8'), {{ filename: 'account-mirror.js' }});
(async () => {{
  const result = await new Promise((resolve, reject) => {{
    const accepted = listener(
      {{ type: 'SA_MIRROR_SCAN_RELATION', syncRunId: 'run-1', relationType: 'like' }},
      {{}},
      resolve
    );
    if (accepted !== true) reject(new Error('listener did not keep the async channel open'));
  }});
  console.log(JSON.stringify(result));
}})().catch(error => {{ console.error(error); process.exit(1); }});
"""
    payload = _run_node(script)
    assert payload["ok"] is True
    assert payload["relationType"] == "like"
    assert payload["items"] == []
    assert payload["completeness"] == "partial"
    assert payload["failureCode"] == "RELATION_SCOPE_UNCONFIRMED"
    assert payload["cursor"]["relation_scope_reason"] == "RELATION_TAB_NOT_FOUND"


def test_completion_proof_never_treats_stable_scroll_as_complete_without_evidence():
    script = f"""
const core = require({json.dumps(str(CORE))});
function node(text, aria='') {{ return {{ textContent: text, getAttribute: (key) => key === 'aria-label' ? aria : '' }}; }}
const noProof = {{ querySelectorAll: () => [] }};
const explicit = {{ querySelectorAll: (selector) => selector.includes("role='status'") ? [node('没有更多内容')] : [] }};
const total = {{ querySelectorAll: (selector) => selector.includes("aria-label") ? [node('', '共 2 条收藏')] : [] }};
console.log(JSON.stringify({{
  noProof: core.completionProof('x', noProof, 200),
  explicit: core.completionProof('x', explicit, 1),
  totalMiss: core.completionProof('x', total, 1),
  totalMatch: core.completionProof('x', total, 2)
}}));
"""
    payload = _run_node(script)
    assert payload["noProof"] == {"complete": False, "reason": "TERMINAL_NOT_PROVEN", "totalHint": None}
    assert payload["explicit"]["complete"] is True
    assert payload["explicit"]["reason"] == "EXPLICIT_END_MARKER"
    assert payload["totalMiss"] == {"complete": False, "reason": "TERMINAL_NOT_PROVEN", "totalHint": 2}
    assert payload["totalMatch"] == {"complete": True, "reason": "TRUSTED_TOTAL_MATCH", "totalHint": 2}


def test_existing_platform_tab_preference_preserves_the_owner_selected_tab():
    script = f"""
const core = require({json.dumps(str(CORE))});
const tabs = [
  {{ id: 101, active: false, url: 'https://example.invalid/first' }},
  {{ id: 202, active: true, url: 'https://example.invalid/active' }},
  {{ id: 303, active: false, url: 'https://example.invalid/last' }}
];
console.log(JSON.stringify({{
  preferred: core.preferExistingPlatformTab(tabs, 303)?.id || null,
  active: core.preferExistingPlatformTab(tabs)?.id || null,
  empty: core.preferExistingPlatformTab([])
}}));
"""
    payload = _run_node(script)
    assert payload == {"preferred": 303, "active": 202, "empty": None}
