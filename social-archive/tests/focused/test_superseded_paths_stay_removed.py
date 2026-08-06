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


#: 扩展里允许存在的输入控件，逐个写明**为什么它不构成门槛**。
#: 新增任何输入控件都必须先进这张表——进不来就说明它是个门槛。
_ALLOWED_INPUTS = {
    # 藏在 <details class="advanced"> 里的排障项，正常路径不碰。
    ("options.html", "endpoint"): "服务连接排障用，默认无需修改",
    # placeholder="可留空"，不填也能保存。是个便利项，不是必填。
    ("popup.html", "collectionKey"): "收藏夹名，可留空",
    # **复选框不是「输入字符」，是点一下。** 零输入那条禁的是让人打字
    # （粘 Cookie、填令牌、抄请求头），不是禁掉所有开关。
    # 而它存在的理由恰恰是零门槛的另一面：那颗浮动按钮此前**关不掉**——
    # showFloatingButton 默认 true 且全仓没人写它，「怎么让这个按钮消失」
    # 在界面上没有答案。见 evidence/T11/THE_LOCAL_OBSIDIAN_PATH_IS_BUILT_BUT_UNREACHABLE.json
    ("options.html", "showFloatingButton"): "复选框（点一下，不打字）；关掉页面上那颗浮动按钮",
}


def test_no_extension_surface_asks_for_typed_input() -> None:
    """T03 Acceptance 原文：「扩展可用且**全程**无需用户输入任何字符」。

    ⚠️ 这条先前只扫 options.html —— 而扩展有三个界面。
    popup.html 里就有一个 collectionKey 输入框（它是可选的，所以不违规），
    但只扫一个面意味着：将来谁在 popup 或 sidepanel 加一个**必填**输入，
    这条判据照样报绿。「只验了一个界面」这个错本会话已经犯过一次
    （T14 的文案只验了 PWA，扩展那侧压根没有词典）。
    """
    import re

    surfaces = sorted((ROOT / "apps/browser-extension").glob("*.html"))
    assert len(surfaces) >= 3, f"只扫到 {len(surfaces)} 个界面，扩展至少有三个"
    seen = 0
    for path in surfaces:
        html = path.read_text(encoding="utf-8")
        assert "one-time-code" not in html, f"{path.name} 里一次性码输入框又回来了"
        for tag in re.findall(r"<input[^>]*>", html):
            ident = re.search(r'id="([^"]+)"', tag)
            assert ident, f"{path.name} 有一个没有 id 的 input，无法登记：{tag[:80]}"
            seen += 1
            key = (path.name, ident.group(1))
            # **登记不等于随便什么控件都行。** 登记为「复选框」的必须真是复选框，
            # 否则今天登记一个 checkbox、明天改成 type="text"，判据照样绿。
            if "复选框" in _ALLOWED_INPUTS.get(key, ""):
                assert 'type="checkbox"' in tag, (
                    f"{path.name} 的 #{ident.group(1)} 登记时写的是复选框，"
                    f"现在却不是了：{tag[:90]}"
                )
            assert key in _ALLOWED_INPUTS, (
                f"{path.name} 出现了未登记的输入控件 #{ident.group(1)}。"
                "T03 要求全程零输入；确实必要的话请加进 _ALLOWED_INPUTS 并写明为什么它不是门槛。"
            )
    assert seen >= 2, "一个 input 都没扫到——正则大概没匹配上，这条守卫在空转"


def test_the_only_free_text_input_is_genuinely_optional() -> None:
    """登记在案不等于无害。popup 那个必须**确实可留空**。

    哪天有人给它加上 required，或者把 placeholder 改成「请输入」，
    它就从便利项变成门槛了，而登记表还写着「可留空」。
    """
    html = (ROOT / "apps/browser-extension/popup.html").read_text(encoding="utf-8")
    import re

    tag = re.search(r'<input[^>]*id="collectionKey"[^>]*>', html)
    assert tag, "popup.html 里找不到 collectionKey —— 登记表该更新了"
    assert "可留空" in tag.group(0), "collectionKey 不再标明可留空，它可能已变成必填"
    assert "required" not in tag.group(0), "collectionKey 被标成必填了 —— 那就是门槛"


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


def test_revoked_extension_token_gets_401_with_a_chinese_message() -> None:
    """T03 Oracle 的最后一句：「撤销令牌后扩展上行得 401 **且界面显示中文提示**」。

    401 本身先前就验过；「中文提示」这一半一直没有判据——而它才是用户看得见的部分。
    英文错误码或 HTTP 状态数字直接甩给用户，等同于什么都没说。
    """
    import importlib
    import os
    import tempfile

    from fastapi.testclient import TestClient

    with tempfile.TemporaryDirectory() as tmp:
        token_file = os.path.join(tmp, "api-token")
        with open(token_file, "w", encoding="utf-8") as handle:
            handle.write("shared-token-for-this-test")
        os.chmod(token_file, 0o600)
        os.environ["SOCIAL_ARCHIVE_DATA_ROOT"] = os.path.join(tmp, "data")
        os.environ["SOCIAL_ARCHIVE_API_TOKEN_FILE"] = token_file
        # 必须打开总鉴权开关，否则 require_token 第一行就早退，
        # 这条判据会在"什么都没校验"的情况下报绿——本会话已经栽过一次。
        os.environ["SOCIAL_ARCHIVE_PAIRING_REQUIRED"] = "1"
        import social_archive.api as api_module

        importlib.reload(api_module)
        client = TestClient(api_module.app)

        user_id = api_module.store.upsert_oauth_identity(
            provider="github", subject="t03-revoke", display_name="Owner"
        )
        token = api_module.store.issue_extension_token(user_id=user_id)
        assert client.get(
            "/v1/extension/bootstrap", headers={"authorization": f"Bearer {token}"}
        ).status_code == 200, "有效令牌本该通过——判据的前提不成立"

        api_module.store.revoke_extension_tokens(user_id)
        response = client.get(
            "/v1/extension/bootstrap", headers={"authorization": f"Bearer {token}"}
        )
        assert response.status_code == 401
        detail = str(response.json().get("detail", ""))
        assert detail, "401 没有任何说明"
        assert any("一" <= ch <= "鿿" for ch in detail), (
            f"401 的提示不是中文：{detail!r}——用户看不懂就等于没提示"
        )
        for leak in ("Traceback", "Unauthorized", "401", "None"):
            assert leak not in detail, f"401 提示里漏出了 {leak}"

        os.environ.pop("SOCIAL_ARCHIVE_PAIRING_REQUIRED", None)
        os.environ.pop("SOCIAL_ARCHIVE_API_TOKEN_FILE", None)


def test_extension_surfaces_a_chinese_message_when_it_cannot_reach_the_archive() -> None:
    """服务端给了中文还不够——扩展得把它显示出来，而不是吞掉或换成 HTTP 数字。"""
    options = (ROOT / "apps/browser-extension/options.js").read_text(encoding="utf-8")
    assert "还没有连上私人档案馆" in options, "扩展在连不上时没有中文提示"
    assert "无需输入任何内容" in options, "提示里没有告诉用户下一步（且下一步必须是零输入）"
    # ⚠️ 这条判据自己被改过一次：原先断言源码里有字面量 `data.detail ||`，
    # 于是我把兜底逻辑改好（改成一个统一的中文兜底函数）之后，它反而红了。
    # **它盯的是实现细节，不是性质。** 现在改成盯性质：
    #   服务端给了中文就用中文；没给就仍然给一句中文，绝不出现 HTTP 状态码。
    shared = (ROOT / "apps/browser-extension/shared.js").read_text(encoding="utf-8")
    assert "SA_humanMessage" in shared, "扩展没有统一的中文兜底"
    code = "\n".join(
        line for line in shared.splitlines() if not line.lstrip().startswith(("//", "*"))
    )
    assert "`HTTP ${response.status}`" not in code, (
        "扩展仍会把 `HTTP 500` 这种英文状态码当成给人看的提示语"
    )


def test_only_scripts_the_container_never_runs_are_exempt_from_drift() -> None:
    """**「开发期脚本不同」这个豁免不许扩大到服务真跑的东西。**

    2026-08-07：我连着两次只改了一道判据和一个演练，而漂移检查报的是
    「服务执行的不是你以为的那一版，要重建镜像」——听起来像生产在跑旧代码，
    而他那边跑的东西一个字节没变。**指错原因的告警比不告警更费人。**

    所以判据和演练单独归一类。但那个豁免是有边界的：容器的 ENTRYPOINT 是
    `container-entrypoint.sh`，构建期只用 `build_extension_package.py`——
    **这两个一旦被豁免，生产就真的可能在跑旧代码而这道门还说 PASS**。
    """
    from pathlib import Path

    source = (Path(__file__).resolve().parents[2]
              / "scripts/check_production_matches_the_repo.py").read_text(encoding="utf-8")
    namespace: dict = {}
    body = source.split("def _dev_only(name: str) -> bool:", 1)[1]
    body = body.split("\n\n", 1)[0]
    exec("def _dev_only(name: str) -> bool:" + body, namespace)   # noqa: S102
    dev_only = namespace["_dev_only"]

    for exempt in ("scripts/check_brand.py", "scripts/list_shape_end_to_end_drill.py",
                   "scripts/run_all_drills.py", "scripts/final_verify.py"):
        assert dev_only(exempt), f"{exempt} 该被归成开发期脚本"
    for must_fail in ("src/social_archive/api.py", "apps/pwa/app.js",
                      "apps/browser-extension/background.js",
                      "scripts/container-entrypoint.sh",
                      "scripts/build_extension_package.py",
                      "scripts/deploy_to_production.sh"):
        assert not dev_only(must_fail), (
            f"**{must_fail} 被豁免了**——它要么是服务真在跑的，要么是构建/部署本身。"
            "豁免它等于生产在跑旧代码而这道门还说 PASS"
        )
