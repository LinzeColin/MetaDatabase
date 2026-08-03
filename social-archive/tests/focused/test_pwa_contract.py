from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def test_pwa_is_owner_approved_table_first_account_mirror_product():
    html = (ROOT / "apps/pwa/index.html").read_text(encoding="utf-8")
    js = (ROOT / "apps/pwa/app.js").read_text(encoding="utf-8")
    for text in (
        "多平台收藏库镜像", "资料库", "账号同步", "自动导出", "设置",
        "全部收藏内容", "按平台归类", "立即同步全部", "平台", "时间",
        "主题分类", "关键词", "内容", "链接",
    ):
        assert text in html
    for legacy in ("所有收藏，一个入口", "看到有用的，点一下就收好", "粘贴链接，立即保存"):
        assert legacy not in html
    assert "window.prompt" not in js and "alert(" not in js
    assert 'postToExtension("SA_SYNC_ACCOUNT"' in js
    assert 'postToExtension("SA_SYNC_ALL_ACCOUNTS"' in js


def test_pwa_table_supports_platform_grouping_default_time_sort_and_column_control():
    html = (ROOT / "apps/pwa/index.html").read_text(encoding="utf-8")
    js = (ROOT / "apps/pwa/app.js").read_text(encoding="utf-8")
    for element_id in (
        "platformTabs", "tableHead", "tableBody", "sortBtn", "columnsBtn",
        "groupBtn", "globalSearch", "filterPanel", "detailDrawer", "syncModalBackdrop",
    ):
        assert f'id="{element_id}"' in html
    assert 'sortKey: "savedAt"' in js
    assert 'sortDir: "desc"' in js
    assert 'group: true' in js
    for required in ('key: "platform"', 'key: "savedAt"', 'key: "topic"', 'key: "keywords"', 'key: "content"', 'key: "url"'):
        assert required in js
    assert 'label: "Chrome书签/网页"' in js


def test_pwa_zero_tech_copy_hides_internal_runtime_terms_from_primary_view():
    html = (ROOT / "apps/pwa/index.html").read_text(encoding="utf-8")
    primary = html.split('<div class="modal-backdrop" id="settingsModalBackdrop">', 1)[0]
    forbidden_terms = ("Docker", "Worker", "API Token", "Cookie 文件", "SQLite", "对象存储配置", "Sidecar")
    assert not any(term in primary for term in forbidden_terms)


def test_pwa_calls_the_endpoints_the_table_shell_depends_on():
    # Preserved in spirit from the pre-reconcile upstream copy: the table-first
    # contract above says nothing about which endpoints the shell actually
    # talks to.  The v0.0.0.5 list named /v1/extension/bootstrap and
    # /v1/storage/status, which the account-mirror shell no longer calls --
    # bootstrap is the extension's own endpoint, not the page's.
    js = (ROOT / "apps/pwa/app.js").read_text(encoding="utf-8")
    for endpoint in ("/v1/library", "/v1/accounts", "/v1/destinations", "/v1/library/classify"):
        assert endpoint in js
