"""他被告知去打开哪一页，那一页就必须认得出来（v0.0.0.7 / T08）。

诊断按钮进门第一件事是判平台：

    if (!platform || !SA.patternsForPlatform(platform).length)
      throw new Error("这个页面不是可诊断的平台。请先打开…的收藏页…")

**认不出来，他那一按当场就废了**——而收藏夹并不在 www.bilibili.com 上，
是在 space.bilibili.com/<uid>/favlist。域名判定但凡写成「等于 bilibili.com」
或「等于 www.bilibili.com」，他打开的那一页就会被拒。

（写这条判据的起因是我自己量错了一次：拿 Node 的 vm 跑 shared.js 时
忘了把 URL 放进上下文，`new URL(...)` 抛异常被兜住、回落到最后一条规则，
于是所有地址都报 generic-web。**差点据此说产品坏了。** 判据用真的
Node 上下文跑，不再手搭沙箱。）
"""

import json
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
SHARED = ROOT / "apps/browser-extension/shared.js"

# 左边是 Owner 真会打开的地址，右边是必须认出来的平台。
PAGES_HE_MIGHT_OPEN = {
    "https://space.bilibili.com/12345/favlist": "bilibili",
    "https://space.bilibili.com/12345/favlist?fid=99&ftype=create": "bilibili",
    "https://www.bilibili.com/": "bilibili",
    "https://b23.tv/abcdef": "bilibili",
    "https://www.xiaohongshu.com/user/profile/abc": "xiaohongshu",
    "https://www.douyin.com/user/self?showTab=favorite_collection": "douyin",
    "https://www.kuaishou.com/profile": "kuaishou",
}


def _detect() -> dict[str, dict]:
    script = f"""
const fs = require("fs"), vm = require("vm");
// **把真的 URL / URLSearchParams 放进上下文。** 少了它们，shared.js 里
// `new URL(value)` 会抛，被 catch 兜住后回落到最后一条规则（generic-web），
// 于是每个地址都"认不出来"——那是沙箱的错，不是产品的错。
const sandbox = {{ chrome: {{ runtime: {{ getURL: () => "" }} }}, console, URL, URLSearchParams }};
sandbox.globalThis = sandbox; sandbox.self = sandbox; sandbox.window = sandbox;
const ctx = vm.createContext(sandbox);
vm.runInContext(fs.readFileSync({json.dumps(str(SHARED))}, "utf8"), ctx);
const SA = sandbox.SA;
const out = {{}};
for (const u of {json.dumps(list(PAGES_HE_MIGHT_OPEN))}) {{
  const rule = SA.platformFromUrl(u);
  const id = rule && rule.id;
  out[u] = {{ id, patterns: id ? SA.patternsForPlatform(id).length : 0 }};
}}
console.log(JSON.stringify(out));
"""
    done = subprocess.run(["node", "-e", script], cwd=ROOT, capture_output=True,
                          text=True, check=True)
    return json.loads(done.stdout)


@pytest.mark.parametrize("url,expected", sorted(PAGES_HE_MIGHT_OPEN.items()))
def test_the_url_is_mapped_to_the_right_platform(url: str, expected: str) -> None:
    got = _detect()[url]
    assert got["id"] == expected, (
        f"{url} 被认成了 {got['id']}——诊断按钮会当场拒绝，而这正是他被告知要打开的那一页"
    )


@pytest.mark.parametrize("url", sorted(PAGES_HE_MIGHT_OPEN))
def test_the_platform_has_permission_patterns_so_the_diagnostic_does_not_refuse(url: str) -> None:
    """光认出平台还不够：诊断还要求这个平台有权限模式，否则同样当场拒绝。"""
    got = _detect()[url]
    assert got["patterns"] > 0, (
        f"{url} 认出来了（{got['id']}）但没有权限模式——"
        "诊断的守卫会把它当成「不是可诊断的平台」直接拒掉"
    )


def test_every_domain_we_asked_permission_for_is_a_domain_we_recognise() -> None:
    """**两张名单必须一致。**

    权限模式里写着我们要读哪些域名——那是我们向用户张口要过的东西。
    认平台时却一个都不判，就成了「要了权限却不用」：实测有 8 个域名如此
    （xhslink.com / v.iesdouyin.com / gifshow.com / kuaishou.cn /
    b23.tv / redd.it 等），其中 xhslink.com 正是小红书的标准分享链接。

    对一个把「你的凭据只在你自己机器上」当卖点的产品，**要了权限却不用**
    尤其别扭；而两张名单对不上本身就是隐患。

    **一处登记在案的例外**：youtube 要 google.com 的 Cookie（登录态有一部分
    挂在 Google 账号域上），但不该把 google.com 认成 YouTube——Gmail、Drive
    都不是 YouTube。「要这个域的权限」与「按这个域认平台」是两件事。
    """
    script = f"""
const fs = require("fs"), vm = require("vm");
const sandbox = {{ chrome: {{ runtime: {{ getURL: () => "" }} }}, console, URL, URLSearchParams }};
sandbox.globalThis = sandbox; sandbox.self = sandbox; sandbox.window = sandbox;
vm.runInContext(fs.readFileSync({json.dumps(str(SHARED))}, "utf8"), vm.createContext(sandbox));
const SA = sandbox.SA;
const bad = [];
// **登记的例外**：一个平台可能需要某个域的权限，却不该按那个域去认平台。
// youtube 要 google.com 的 Cookie（登录态有一部分挂在 Google 账号域上），
// 但把 google.com 认成 YouTube 是错的——Gmail、Drive 都不是 YouTube。
const RECOGNITION_EXEMPT = new Set(["www.google.com"]);
for (const rule of SA.PLATFORM_RULES) {{
  for (const p of rule.patterns) {{
    const host = p.replace(/^https:\\/\\//, "").replace(/\\/\\*$/, "").replace(/^\\*\\./, "www.");
    const got = SA.platformFromUrl("https://" + host + "/x");
    if (RECOGNITION_EXEMPT.has(host)) continue;
    if (!got || got.id !== rule.id) bad.push(host + " → " + (got && got.id) + "（应为 " + rule.id + "）");
  }}
}}
console.log(JSON.stringify(bad));
"""
    done = subprocess.run(["node", "-e", script], cwd=ROOT, capture_output=True,
                          text=True, check=True)
    mismatched = json.loads(done.stdout)
    assert not mismatched, f"要了权限却认不出来的域名：{mismatched}"
