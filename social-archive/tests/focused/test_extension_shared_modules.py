"""扩展共享模块（v0.0.0.7 / T03(a) 三分拆的产物）。

这个文件接管了 `test_extension_account_mirror_core.py` 里**仍然有效**的那部分覆盖。

原文件有 7 个测试，打在 `content/account-mirror-core.js` 上。那个文件被拆成三份：
DOM 抓取（删）／平台元数据（`content/platform-catalog.js`）／通用工具
（`content/extension-utils.js`）。于是原来的 7 个测试也分成两类：

  · 3 个测的是通用工具（书签展平、URL→关系/ID、标签页挑选）——**照搬过来**，
    只把 require 指向新文件。它们是 T04 脊柱的覆盖，删了就没人守着
    `flattenBookmarksTree` 了。
  · 4 个测的是抓取器（`ensureRelationScope`/`discoverCollectionScopes`/
    `completionProof`/`SA_MIRROR_SCAN_RELATION`）——随实现一起废止，
    反转成守卫放在 `test_superseded_paths_stay_removed.py`。

**不是"删了 4 个测试"，是 4 个测试的被测对象已被实测证伪并移除，
守卫接替了它们的位置。**
"""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
EXT = ROOT / "apps/browser-extension"
UTILS = EXT / "content/extension-utils.js"
CATALOG = EXT / "content/platform-catalog.js"


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
    """T04 脊柱的第一个数据源。它出问题，Chrome 书签就进不来。"""
    script = f"""
const utils = require({json.dumps(str(UTILS))});
const result = utils.flattenBookmarksTree([{{
  id: 'root', title: '', children: [{{
    id: 'f1', title: '研究', children: [{{
      id: 'f2', title: 'AI', children: [
        {{ id: 'b1', parentId: 'f2', title: '示例', url: 'https://www.rfc-editor.org/rfc/rfc3986?utm_source=test&x=1#section-3', dateAdded: 1700000000000 }},
        {{ id: 'bad', parentId: 'f2', title: '危险', url: 'javascript:alert(1)', dateAdded: 1700000000000 }}
      ]
    }}]
  }}]
}}]);
console.log(JSON.stringify({{ result, chunks: utils.chunk([1,2,3,4,5], 2) }}));
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
const utils = require({json.dumps(str(UTILS))});
console.log(JSON.stringify({{
  xBookmark: utils.relationFromUrl('x', 'https://x.com/i/bookmarks'),
  redditUpvoted: utils.relationFromUrl('reddit', 'https://www.reddit.com/user/me/upvoted/'),
  biliWatchLater: utils.relationFromUrl('bilibili', 'https://www.bilibili.com/watchlater/list'),
  xId: utils.externalId('x', 'https://x.com/user/status/123456?utm_source=x'),
  xhsId: utils.externalId('xiaohongshu', 'https://www.xiaohongshu.com/explore/abc-123')
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


def test_existing_platform_tab_preference_preserves_the_owner_selected_tab():
    script = f"""
const utils = require({json.dumps(str(UTILS))});
const tabs = [
  {{ id: 101, active: false, url: 'https://example.invalid/first' }},
  {{ id: 202, active: true, url: 'https://example.invalid/active' }},
  {{ id: 303, active: false, url: 'https://example.invalid/last' }}
];
console.log(JSON.stringify({{
  preferred: utils.preferExistingPlatformTab(tabs, 303)?.id || null,
  active: utils.preferExistingPlatformTab(tabs)?.id || null,
  empty: utils.preferExistingPlatformTab([])
}}));
"""
    payload = _run_node(script)
    assert payload == {"preferred": 303, "active": 202, "empty": None}


def test_platform_catalog_keeps_the_four_fields_t08_needs():
    """拆分时最容易丢的就是这四个字段——它们看着像抓取器的一部分，其实不是。

    没有它们，T08 的拦截路得把"B站收藏夹在哪个 URL"重新造一遍。
    """
    script = f"""
const catalog = require({json.dumps(str(CATALOG))});
const out = {{}};
for (const [name, entry] of Object.entries(catalog.PLATFORMS)) {{
  out[name] = {{
    fields: Object.keys(entry).sort(),
    label: entry.label,
    relations: entry.relations,
    relationsCovered: entry.relations.every(r => typeof entry.relationUrls[r] === 'string' && entry.relationUrls[r].startsWith('https://')),
    homeIsHttps: String(entry.home || '').startsWith('https://')
  }};
}}
console.log(JSON.stringify(out));
"""
    payload = _run_node(script)
    # **这个集合是精确相等，加平台必须是个有意识的动作。**
    # 2026-08-05 由 7 变 8：Owner 裁定接上 youtube（它此前在服务端凭据表、
    # Cookie 导出白名单、manifest 权限三处都有，唯独用户点得到的那层没有）。
    # 目录里没有它的话，platformLabel 会把内部 id「youtube」直接甩给用户。
    assert set(payload) == {
        "xiaohongshu", "douyin", "kuaishou", "bilibili", "x", "reddit", "instagram",
        "youtube",
    }
    for name, entry in payload.items():
        # 只有这四个字段。多一个 selector 混进来，这条就会红——
        # 目录是元数据，不许再变回"什么都往里塞"的 PLATFORM_SPECS。
        assert entry["fields"] == ["home", "label", "relationUrls", "relations"], name
        assert entry["label"], name
        assert entry["relations"], name
        assert entry["homeIsHttps"], name
        # 每一种声明支持的关系都得有对应 URL，否则 runBrowserAccountSync
        # 会拿着一个没有落点的关系去发起同步。
        assert entry["relationsCovered"], name
    assert payload["bilibili"]["relations"] == ["favorite", "watch_later", "history", "like"]
    assert payload["instagram"]["label"] == "Instagram"


def test_catalog_and_utils_contain_no_dom_scraping():
    """判据打在**内容**上：这两个文件是"留下来的那一半"，
    抓取器不许借着它们回来。"""
    banned = (
        "querySelectorAll", "closest(", "getBoundingClientRect",
        "scrollTo(", "scrollBy(", "aria-selected", "data-e2e",
        "innerText", "textContent",
    )
    for path in (UTILS, CATALOG):
        text = path.read_text(encoding="utf-8")
        # 注释里提到这些词是允许的（解释为什么删），代码里不允许。
        code = "\n".join(
            line for line in text.splitlines()
            if not line.lstrip().startswith(("*", "//", "/*"))
        )
        for token in banned:
            assert token not in code, f"{path.name} 的代码里出现了 {token}——抓取器在回流"
