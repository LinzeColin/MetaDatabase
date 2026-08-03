"""防复活守卫（v0.0.0.7 / T03）。

这个文件取代了原先那 6 个**断言那三个 worker 存在**的测试。
它们不是被静默删掉的——是被反过来了：原来断言「xhs/ks/douk worker 已定义且
健康检查就位」，现在断言「它们不许再出现」。

为什么要反过来而不是直接删：`CONFLICT_ORDER.md` 把这条路列为 SUPERSEDED，
理由是**实测证伪**——那三个上游项目的 HTTP API 只有单篇详情，
`XHS-Downloader` 是 `/xhs/detail`，`DouK` 只有 detail/account/mix/live/comment/search，
**都没有任何收藏枚举接口**。按那个 compose 把它们起成 worker，
拿到的还是单篇详情，同步结果**依然是 0**。

删掉一个错误实现只解决今天；留一条守卫才防得住明天有人看着旧文档
"把它加回来"。这就是那条守卫。
"""

from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def test_domestic_http_worker_compose_is_gone() -> None:
    """compose.workers.yaml 整个文件都是那三个 worker，不留。"""
    assert not (ROOT / "compose.workers.yaml").exists(), (
        "compose.workers.yaml 又出现了。那三个 worker 的 HTTP API 没有收藏枚举接口，"
        "接上去结果依然是 0——见 CONFLICT_ORDER.md 的 SUPERSEDED 表。"
    )


def test_worker_start_stop_scripts_are_gone() -> None:
    for name in ("start_workers.sh", "stop_workers.sh"):
        assert not (ROOT / "scripts" / name).exists(), f"scripts/{name} 又出现了"


def test_no_main_py_api_worker_definitions_anywhere() -> None:
    """不只看那一个文件——换个文件名把同样的东西加回来也要被抓住。

    判据打在**内容**上（`python main.py api` 这个启动形态），不是文件名上。
    """
    offenders = []
    for path in ROOT.rglob("*.y*ml"):
        if any(part in {".venv", "node_modules", ".git", "evidence"} for part in path.parts):
            continue
        text = path.read_text(encoding="utf-8", errors="ignore")
        # compose 里 command 是 YAML 列表，逐行写；所以按"main.py 紧跟 api"判
        if "main.py" in text and "- api" in text:
            offenders.append(str(path.relative_to(ROOT)))
    assert not offenders, (
        f"这些文件里又出现了 `python main.py api` 形态的 worker 定义：{offenders}。"
        "实测证伪：该 API 只暴露单篇详情，没有收藏枚举。"
    )


def test_guard_actually_reads_something() -> None:
    """判据自己的自检：上面那条 rglob 必须真的扫到过文件。

    扫到 0 份和"没问题"长得一模一样——这条把两者分开。
    （本机吃过这个亏不止一次：非递归 glob 读到 0 份，门却报绿。）
    """
    scanned = [
        p for p in ROOT.rglob("*.y*ml")
        if not any(part in {".venv", "node_modules", ".git", "evidence"} for part in p.parts)
    ]
    assert len(scanned) >= 3, f"守卫只扫到 {len(scanned)} 份 YAML，它大概没在查"


# ── 一次性配对码（v0.0.0.7 / T03）──────────────────────────────────
#
# CONFLICT_ORDER 废止它的理由：真实使用中连续失败三次，
# 十分钟有效期与手抄验证码本身就是技术门槛，与 INV-ZERO-BARRIER 直接冲突。
# 替代品是扩展长期可撤销令牌（POST /v1/auth/extension-token）。


def test_pairing_endpoints_are_gone() -> None:
    """判据打在**端点响应**上，不是打在源码 grep 上——
    源码里留个同名函数但没挂路由，grep 会报红而实际是好的；
    反过来换个名字挂回同样的路由，grep 会报绿而实际复活了。"""
    import importlib
    import os
    import tempfile

    from fastapi.testclient import TestClient

    with tempfile.TemporaryDirectory() as tmp:
        os.environ["SOCIAL_ARCHIVE_DATA_ROOT"] = os.path.join(tmp, "data")
        import social_archive.api as api_module

        importlib.reload(api_module)
        client = TestClient(api_module.app)
        for path in ("/v1/pairing/status", "/v1/pair"):
            assert client.get(path).status_code == 404, f"{path} 又活了"
        assert client.post("/v1/pairing/exchange", json={"code": "X"}).status_code == 404


def test_pairing_helpers_are_gone_from_api_module() -> None:
    """上一条查端点，这条查实现——两者都要，单查一边都能被绕过。"""
    import social_archive.api as api_module

    for name in (
        "PairingRequest", "PairingRateLimiter", "require_pairing_edge",
        "_read_pairing_record", "_exchange_pairing_code", "_normalize_pairing_code",
        "PAIRING_PATHS", "PAIRING_STATE_FILENAME",
    ):
        assert not hasattr(api_module, name), f"api.{name} 还在——配对码链路没删干净"


# ── DOM 抓取器（v0.0.0.7 / T03(a)）─────────────────────────────────
#
# CONFLICT_ORDER 废止它的理由：靠 CSS 选择器和界面文案正则去凑列表，平台一改版就静默变空，
# 而"变空"和"这个人真的没有收藏"在数据上长得一模一样。生产上"永远是 0"就是这么来的
# （evidence/T00/CURRENT_TRUTH.json）。替代品是在 Owner 浏览器里拦平台自己的 API 响应（T08）。
#
# 下面这些守卫接替了原先 16 个"断言抓取器存在"的测试。仍然有效的那部分覆盖
# （书签展平、URL→关系/ID、标签页挑选）没有被删，搬到了 test_extension_shared_modules.py。


def test_dom_scraper_files_are_gone() -> None:
    for name in ("content/account-mirror-core.js", "content/account-mirror.js"):
        assert not (ROOT / "apps/browser-extension" / name).exists(), (
            f"{name} 又出现了。DOM 抓取已被实测证伪——平台改版即静默归零，"
            "且无法与'真的没有收藏'区分。见 CONFLICT_ORDER.md。"
        )


def test_no_dom_scraping_symbols_anywhere_in_the_extension() -> None:
    """判据打在**符号**上而不是文件名上——换个文件名把同一套东西加回来也要被抓住。"""
    ext = ROOT / "apps" / "browser-extension"
    banned = (
        "extractCandidates", "ensureRelationScope", "discoverCollectionScopes",
        "detectLoggedIn", "relationTabIsActive", "collectionFromElement",
        "completionProof", "PLATFORM_SPECS", "relationTabMatchers",
        "SAMirrorCore",
    )
    offenders = []
    scanned = 0
    for path in ext.rglob("*.js"):
        scanned += 1
        # 注释里提到这些名字是允许的（解释为什么删掉），代码里出现才算复活。
        code = "\n".join(
            line for line in path.read_text(encoding="utf-8", errors="ignore").splitlines()
            if not line.lstrip().startswith(("*", "//", "/*"))
        )
        for token in banned:
            if token in code:
                offenders.append(f"{path.relative_to(ext)}:{token}")
    assert scanned >= 5, f"守卫只扫到 {scanned} 个 js 文件，它大概没在查"
    assert not offenders, f"DOM 抓取符号在这些地方回流了：{offenders}"


def test_extension_never_autoscrolls_any_page() -> None:
    """自动滚动是抓取器专属动作——现在**任何**扩展脚本都不该再滚用户的页面。

    原测试 `test_autoscroll_is_isolated_to_explicit_account_mirror_sync` 断言的是
    "只有账号镜像才滚"。抓取器删掉之后判据收紧成"谁都不许滚"。
    """
    ext = ROOT / "apps" / "browser-extension"
    offenders = [
        str(path.relative_to(ext))
        for path in ext.rglob("*.js")
        if "scrollTo(" in path.read_text(encoding="utf-8", errors="ignore")
        or "scrollBy(" in path.read_text(encoding="utf-8", errors="ignore")
    ]
    assert not offenders, f"这些扩展脚本仍会自动滚动页面：{offenders}"


def test_manifest_no_longer_injects_scrapers_into_platform_pages() -> None:
    import json as _json

    manifest = _json.loads(
        (ROOT / "apps/browser-extension/manifest.json").read_text(encoding="utf-8")
    )
    scripts = [js for entry in manifest.get("content_scripts", []) for js in entry.get("js", [])]
    assert scripts, "content_scripts 被清空了——bridge.js 也该在这里"
    for name in ("content/account-mirror-core.js", "content/account-mirror.js"):
        assert name not in scripts, f"manifest 又把 {name} 注入平台页面了"
    # 抓取器删掉之后，扩展不该再对七个平台页面做常驻注入。
    matches = [m for entry in manifest.get("content_scripts", []) for m in entry.get("matches", [])]
    for host in ("xiaohongshu.com", "douyin.com", "kuaishou.com", "bilibili.com",
                 "x.com", "reddit.com", "instagram.com"):
        assert not any(host in m for m in matches), (
            f"manifest 仍在向 {host} 常驻注入 content script——抓取器已删，没有理由再注入"
        )


def test_acquisition_seam_fails_loudly_instead_of_returning_empty() -> None:
    """INV-NO-SILENT-ZERO 的守卫。

    取数通道拆掉之后最容易犯的错是让它返回 `{ ok: true, items: [] }`——
    那会在服务端留下一条 completeness=complete / item_count=0 的回执，
    界面显示"同步成功"、库里一条没有。**必须报错，不许报空。**
    """
    background = (ROOT / "apps/browser-extension/background.js").read_text(encoding="utf-8")
    assert "async function acquireRelationItems" in background, (
        "取数缝隙函数不见了——T08 要替换的就是这一个函数体"
    )
    assert "ACQUISITION_PATH_NOT_INSTALLED" in background
    assert 'failure_code: error?.failureCode || "BROWSER_SCAN_FAILED"' in background, (
        "具体失败原因被拍平成通用码了——用户会看不出该怎么办"
    )
    # 传输层必须还在调用链上：T08 只换取数，不该重造分块上传协议。
    assert "sendBrowserScopeBatches({ syncRunId, platform, relation, scopeResult: result" in background


def test_login_state_is_not_guessed_after_the_detector_was_removed() -> None:
    """detectLoggedIn 删掉之后，`verifyPendingPlatform` 绝不能退回"假定已登录"。

    猜错的代价是拿未登录会话发起首次全量同步 → 平台返回空 → 记一条"同步完成 0 条"，
    又是一个静默的零。
    """
    background = (ROOT / "apps/browser-extension/background.js").read_text(encoding="utf-8")
    assert "LOGIN_PROOF_UNAVAILABLE" in background
    assert "SA_MIRROR_DISCOVER_ACCOUNT" not in background


def test_pairing_code_generator_is_gone_but_token_provisioning_survived() -> None:
    """脚本干了两件事，只删第一件。

    `generate_pairing_code.py` 既生成一次性码（废止），也顺带幂等创建长期 API 令牌
    （**还要**）。整个删掉的话，install.sh / start.sh 就再没有任何地方创建令牌，
    Core 起来直接没有凭据——差点就这么删了。
    """
    assert not (ROOT / "scripts/generate_pairing_code.py").exists()
    assert (ROOT / "scripts/ensure_api_token.py").exists(), (
        "长期 API 令牌的创建者不见了——配对码脚本被整体删掉时把它一起带走了"
    )
    for script in ("scripts/install.sh", "scripts/start.sh"):
        text = (ROOT / script).read_text(encoding="utf-8")
        assert "generate_pairing_code" not in text, f"{script} 仍在调已删的配对码生成器"
        assert "ensure_api_token" in text, f"{script} 不再创建长期 API 令牌"


def test_no_pairing_code_client_path_anywhere() -> None:
    """服务端删干净了不等于删干净了。

    上一轮只删了 api.py 里的路由与助手，**客户端整条链路原封不动**：
    options.html 里那个输入框、options.js 的提交、background.js 的状态轮询、
    shared.js 与 runtime-config.json 里的 pairing_path 全都还在。
    结果是扩展去调一个已经 404 的端点，拿不到响应就把"请输入配对码"的框显示出来——
    比删之前更糟。这条守着别再退回那个状态。
    """
    banned = ("pairing_path", "pairingPath", "pairing/exchange", "pairing/status",
              "pairingCode", "pairing_required === true", "one_time_code_available",
              "一次性配对码")
    surfaces = [
        "apps/browser-extension/background.js", "apps/browser-extension/shared.js",
        "apps/browser-extension/options.js", "apps/browser-extension/options.html",
        "apps/browser-extension/bridge.js", "apps/browser-extension/runtime-config.json",
        "apps/pwa/app.js",
    ]
    offenders = []
    for relative in surfaces:
        path = ROOT / relative
        assert path.exists(), f"{relative} 不见了——守卫扫不到东西和没问题长得一样"
        code = "\n".join(
            line for line in path.read_text(encoding="utf-8").splitlines()
            if not line.lstrip().startswith(("*", "//", "/*", "#"))
        )
        offenders += [f"{relative}:{token}" for token in banned if token in code]
    assert not offenders, f"配对码客户端链路回流了：{offenders}"


def test_extension_setup_page_asks_for_no_typed_input() -> None:
    """T03 Acceptance 原文：「扩展可用且全程无需用户输入任何字符」。

    判据打在**设置页有没有输入控件**上。除了"服务地址"那个高级排障项
    （藏在 <details> 里，正常路径不碰），不该再有任何要用户敲字的地方。
    """
    html = (ROOT / "apps/browser-extension/options.html").read_text(encoding="utf-8")
    import re

    inputs = re.findall(r'<input[^>]*id="([^"]+)"[^>]*>', html)
    assert inputs, "一个 input 都没扫到——正则大概没匹配上，这条守卫在空转"
    assert set(inputs) <= {"endpoint"}, (
        f"设置页出现了要用户输入的控件：{sorted(set(inputs) - {'endpoint'})}。"
        "T03 要求全程零输入；服务地址是排障用的高级项，例外仅此一个。"
    )
    assert "one-time-code" not in html, "一次性码输入框又回来了"


def test_auth_switch_survived_the_deletion() -> None:
    """`settings.pairing_required` 名字里带 pairing，但它是**总鉴权开关**：
    require_token 第一行据此早退，什么都不校验。删配对码时把它一起删掉
    会静默关掉全站鉴权。这条守着它别被顺手删了。"""
    from social_archive.config import Settings

    assert hasattr(Settings, "__dataclass_fields__")
    assert "pairing_required" in Settings.__dataclass_fields__, (
        "pairing_required 被删了——它不是配对码开关，是总鉴权开关，"
        "删掉等于 require_token 永远早退，全站不再鉴权"
    )
