import json
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
CORE = ROOT / "apps/browser-extension/content/account-mirror-core.js"


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
