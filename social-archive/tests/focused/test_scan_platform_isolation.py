import json
import subprocess
from pathlib import Path

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


def test_kuaishou_complete_scan_never_changes_another_platform(service, store):
    kuaishou_item = service.capture(CaptureRequest(
        platform="kuaishou", url="https://www.kuaishou.com/short-video/100", relation_type="favorite",
        requested_levels=["L0", "L1"],
    ))
    x_item = service.capture(CaptureRequest(
        platform="x", url="https://x.com/example/status/101", relation_type="bookmark",
        requested_levels=["L0", "L1"],
    ))

    store.apply_complete_scan("kuaishou", set(), relation_type="favorite")
    store.apply_complete_scan("kuaishou", set(), relation_type="favorite")

    kuaishou_relation = store.get_content(kuaishou_item.content_id)["relations"][0]
    x_relation = store.get_content(x_item.content_id)["relations"][0]
    assert kuaishou_relation["status"] == "closed"
    assert kuaishou_relation["missing_complete_scan_count"] == 2
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
